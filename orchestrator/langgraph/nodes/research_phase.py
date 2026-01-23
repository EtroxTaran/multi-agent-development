"""Research phase node.

Spawns parallel research agents before planning to investigate:
- Technical stack and existing patterns
- Potential pitfalls and gotchas
- Related code in the codebase
- External dependencies and versions

Based on GSD pattern for informed planning.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...agents.prompts import format_prompt, load_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)

# Configuration
RESEARCH_TIMEOUT = 120  # 2 minutes per agent
MAX_RESEARCH_AGENTS = 2  # Number of parallel research agents


@dataclass
class ResearchAgent:
    """Definition of a research agent."""

    id: str
    name: str
    prompt: str
    output_file: str
    priority: int = 1  # Lower = higher priority
    requires_web: bool = False  # Whether this agent needs web search tools


# Research agent definitions
RESEARCH_AGENTS = [
    ResearchAgent(
        id="tech_stack",
        name="Technical Stack Analyzer",
        prompt="""Analyze the project's technical stack and provide findings in JSON format.

Examine:
1. All programming languages used (check file extensions)
2. Frameworks and their versions (check package.json, pyproject.toml, Cargo.toml, go.mod)
3. Major libraries and their purposes
4. Version constraints or compatibility concerns
5. Development tools (linters, formatters, test frameworks)

Output a JSON object with this structure:
{
    "languages": ["python", "typescript"],
    "frameworks": [{"name": "fastapi", "version": "0.100.0"}],
    "libraries": [{"name": "pydantic", "version": "2.0", "purpose": "validation"}],
    "dev_tools": ["pytest", "ruff", "mypy"],
    "constraints": ["requires Python 3.10+", "node 18+"],
    "compatibility_notes": []
}

Focus on facts found in configuration files. Be concise.""",
        output_file="tech_stack.json",
        priority=1,
    ),
    ResearchAgent(
        id="existing_patterns",
        name="Codebase Pattern Analyzer",
        prompt="""Analyze existing code patterns in this codebase and provide findings in JSON format.

Examine:
1. Architectural patterns (MVC, Clean Architecture, DDD, etc.)
2. Naming conventions (files, functions, classes, variables)
3. Testing patterns (unit tests structure, integration tests, mocking approach)
4. Error handling patterns
5. Logging patterns
6. API/endpoint patterns if applicable

Output a JSON object with this structure:
{
    "architecture": "Clean architecture with domain layer",
    "folder_structure": "feature-based",
    "naming": {
        "files": "snake_case",
        "classes": "PascalCase",
        "functions": "snake_case"
    },
    "testing": {
        "framework": "pytest",
        "structure": "mirrors src structure",
        "mocking": "uses pytest-mock"
    },
    "error_handling": "custom exception classes with error codes",
    "logging": "structured logging with context",
    "api_patterns": "REST with Pydantic models"
}

Base findings on actual code, not assumptions. Be concise.""",
        output_file="existing_patterns.json",
        priority=2,
    ),
    ResearchAgent(
        id="web_research",
        name="Web Research Agent",
        prompt="Search the web for documentation, security advisories, best practices, and common pitfalls for the project's tech stack.",
        output_file="web_research.json",
        priority=3,
        requires_web=True,
    ),
]


@dataclass
class ResearchFindings:
    """Aggregated research findings from all agents."""

    tech_stack: Optional[dict] = None
    existing_patterns: Optional[dict] = None
    web_research: Optional[dict] = None
    errors: list[dict] = field(default_factory=list)
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tech_stack": self.tech_stack,
            "existing_patterns": self.existing_patterns,
            "web_research": self.web_research,
            "errors": self.errors,
            "completed_at": self.completed_at,
        }


async def research_phase_node(state: WorkflowState) -> dict[str, Any]:
    """Spawn parallel research agents before planning.

    Runs 2 research agents concurrently:
    1. Tech stack analyzer - examines dependencies and tools
    2. Pattern analyzer - examines code patterns and conventions

    Results are saved to database and used during planning to make
    informed decisions.

    Args:
        state: Current workflow state

    Returns:
        State updates with research findings
    """
    project_dir = Path(state["project_dir"])
    project_name = state["project_name"]

    logger.info("Starting research phase with parallel agents")

    # Check if research already exists and is recent (from DB)
    existing_findings = _load_existing_research_from_db(project_name)
    if existing_findings and _is_research_fresh_from_db(project_name):
        logger.info("Using existing research findings (less than 1 hour old)")
        return {
            "research_complete": True,
            "research_findings": existing_findings.to_dict(),
            "updated_at": datetime.now().isoformat(),
        }

    # Load research configuration
    from ...config.thresholds import load_project_config

    project_config = load_project_config(project_dir)
    research_config = project_config.research

    # Run research agents in parallel
    findings = ResearchFindings()

    try:
        # Spawn agents concurrently
        tasks = [
            _run_research_agent(project_dir, agent, project_name, research_config)
            for agent in RESEARCH_AGENTS
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for agent, result in zip(RESEARCH_AGENTS, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(f"Research agent {agent.id} failed: {result}")
                findings.errors.append(
                    {
                        "agent": agent.id,
                        "error": str(result),
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            else:
                # Store result
                if agent.id == "tech_stack":
                    findings.tech_stack = result
                elif agent.id == "existing_patterns":
                    findings.existing_patterns = result
                elif agent.id == "web_research":
                    findings.web_research = result

        findings.completed_at = datetime.now().isoformat()

        # Save aggregated findings to database
        _save_aggregated_findings(findings, project_name)

        logger.info(
            f"Research phase complete. "
            f"Agents completed: {len([r for r in results if not isinstance(r, Exception)])}/{len(RESEARCH_AGENTS)}"
        )

        return {
            "research_complete": True,
            "research_findings": findings.to_dict(),
            "research_errors": findings.errors if findings.errors else None,
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Research phase failed: {e}")
        return {
            "research_complete": False,
            "errors": [
                {
                    "type": "research_phase_error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "updated_at": datetime.now().isoformat(),
        }


async def _run_research_agent(
    project_dir: Path,
    agent: ResearchAgent,
    project_name: str,
    config: Optional["ResearchConfig"] = None,
) -> dict:
    """Run a single research agent.

    Args:
        project_dir: Project directory to analyze
        agent: Research agent definition
        project_name: Project name for DB storage
        config: Research configuration (optional, uses defaults if not provided)

    Returns:
        Parsed research findings as dict

    Raises:
        Exception: If agent fails or times out
    """
    from ...config.thresholds import ResearchConfig

    if config is None:
        config = ResearchConfig()

    logger.info(f"Running research agent: {agent.name}")

    # Determine tools based on agent type and config
    if agent.requires_web:
        if not config.web_research_enabled:
            logger.info(f"Web research disabled, skipping agent: {agent.id}")
            return {"skipped": True, "reason": "web_research_disabled"}

        # Basic web tools (WebSearch, WebFetch) - always included when web enabled
        tools = list(config.basic_web_tools)

        # Add Perplexity tools if enabled (premium feature)
        if config.perplexity_enabled:
            tools.extend(config.perplexity_tools)

        # Also include codebase tools for context
        tools.extend(["Read", "Glob", "Grep"])
        allowed_tools = ",".join(tools)
    else:
        # Codebase-only agents
        allowed_tools = "Read,Glob,Grep"

    # Get prompt from template or fallback
    prompt = _get_research_prompt(agent, project_dir)

    # Use configured timeout for web research
    timeout = config.web_research_timeout if agent.requires_web else RESEARCH_TIMEOUT

    try:
        # Run Claude with research prompt
        result = await asyncio.wait_for(
            _spawn_claude_agent(project_dir, prompt, allowed_tools),
            timeout=timeout,
        )

        # Parse JSON output
        parsed = _parse_research_output(result)

        # Save to database
        from ...db.repositories.logs import get_logs_repository
        from ...storage.async_utils import run_async

        repo = get_logs_repository(project_name)
        run_async(
            repo.create_log(log_type="research", content={"agent_id": agent.id, "findings": parsed})
        )
        logger.info(f"Research agent {agent.id} saved results to database")

        return parsed

    except asyncio.TimeoutError:
        raise Exception(f"Research agent {agent.id} timed out after {RESEARCH_TIMEOUT}s")
    except Exception as e:
        raise Exception(f"Research agent {agent.id} failed: {e}")


async def _spawn_claude_agent(
    project_dir: Path,
    prompt: str,
    allowed_tools: str = "Read,Glob,Grep",
) -> str:
    """Spawn a Claude agent for research.

    Uses read-only tools to analyze the codebase without modification.

    Args:
        project_dir: Project directory
        prompt: Research prompt
        allowed_tools: Comma-separated list of allowed tools (default: codebase-only)

    Returns:
        Raw agent output
    """
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--allowedTools",
        allowed_tools,
        "--max-turns",
        "10",  # Limit turns for research
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "TERM": "dumb"},
    )

    stdout, stderr = await process.communicate()
    output = stdout.decode() if stdout else ""

    if process.returncode != 0:
        error = stderr.decode() if stderr else "Unknown error"
        raise Exception(f"Claude agent failed: {error}")

    return output


def _parse_research_output(output: str) -> dict:
    """Parse research agent output into dict.

    Args:
        output: Raw agent output

    Returns:
        Parsed dict
    """
    if not output:
        return {}

    # Try direct JSON parse
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    # Look for JSON block in output
    import re

    json_match = re.search(r"\{[\s\S]*\}", output)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Return as raw output
    return {"raw_output": output}


# Map agent IDs to template method names
AGENT_TEMPLATE_MAP = {
    "tech_stack": "tech_stack_research",
    "existing_patterns": "codebase_patterns_research",
    "web_research": "web_research",
}


def _get_research_prompt(agent: ResearchAgent, project_dir: Path) -> str:
    """Get research prompt from template or fallback to inline.

    Args:
        agent: Research agent definition
        project_dir: Project directory

    Returns:
        Formatted prompt string
    """
    template_method = AGENT_TEMPLATE_MAP.get(agent.id)

    if template_method:
        try:
            template = load_prompt("claude", template_method)
            return format_prompt(template, project_dir=str(project_dir))
        except FileNotFoundError:
            logger.debug(f"Template for {agent.id} not found, using inline prompt")

    # Special fallback for web_research agent
    if agent.id == "web_research":
        return _get_web_research_fallback_prompt(project_dir)

    # Fallback to inline prompt with wrapper
    return f"""You are a research agent analyzing a codebase before implementation planning.

PROJECT DIRECTORY: {project_dir}

{agent.prompt}

IMPORTANT:
- Only report what you actually find in the codebase
- If you can't find something, report it as null/empty
- Be concise and factual
- Output ONLY the JSON object, no other text
"""


def _get_web_research_fallback_prompt(project_dir: Path) -> str:
    """Get fallback prompt for web research agent.

    Args:
        project_dir: Project directory

    Returns:
        Web research prompt string
    """
    return f"""You are a web research agent gathering up-to-date information for a software project.

PROJECT DIRECTORY: {project_dir}

Your task is to search the web for relevant information about the technologies detected in this project.

SEARCH FOR:
1. Official documentation links for detected frameworks and libraries
2. Recent security advisories (CVEs) for the tech stack
3. Best practices and recommended patterns for detected frameworks
4. Common pitfalls and gotchas to avoid
5. Version compatibility notes between detected dependencies

WORKFLOW:
1. First, use Read/Glob to examine package.json, pyproject.toml, go.mod, or Cargo.toml to identify the tech stack
2. Then use WebSearch to find relevant documentation and security advisories
3. Use WebFetch to read specific documentation pages if needed

Output a JSON object with this structure:
{{
    "documentation_links": [
        {{"name": "React Docs", "url": "https://react.dev", "relevance": "core framework"}}
    ],
    "security_advisories": [
        {{"package": "lodash", "cve": "CVE-2021-23337", "severity": "high", "fixed_in": "4.17.21"}}
    ],
    "best_practices": [
        {{"topic": "React hooks", "recommendation": "Use useCallback for memoization", "source": "React docs"}}
    ],
    "pitfalls": [
        {{"issue": "Stale closures in useEffect", "solution": "Add all dependencies to dependency array"}}
    ],
    "version_notes": [
        {{"note": "React 18 requires Node 14+", "affects": ["react", "node"]}}
    ]
}}

IMPORTANT:
- Focus on the ACTUAL tech stack found in the project
- Only include relevant, recent information (last 2 years)
- Verify security advisories are real CVEs
- Be concise and factual
- Output ONLY the JSON object, no other text
"""


def _load_existing_research_from_db(project_name: str) -> Optional[ResearchFindings]:
    """Load existing research findings from database if available.

    Args:
        project_name: Project name for DB lookup

    Returns:
        ResearchFindings or None
    """
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    try:
        repo = get_logs_repository(project_name)
        logs = run_async(repo.get_by_type("research_aggregated"))

        if not logs:
            return None

        # Get most recent research
        latest = logs[0]  # Sorted by created_at desc
        data = latest.get("content", {})

        return ResearchFindings(
            tech_stack=data.get("tech_stack"),
            existing_patterns=data.get("existing_patterns"),
            web_research=data.get("web_research"),
            errors=data.get("errors", []),
            completed_at=data.get("completed_at"),
        )
    except Exception:
        return None


def _is_research_fresh_from_db(project_name: str, max_age_hours: int = 1) -> bool:
    """Check if research is recent enough to reuse.

    Args:
        project_name: Project name for DB lookup
        max_age_hours: Maximum age in hours

    Returns:
        True if research is fresh
    """
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    try:
        repo = get_logs_repository(project_name)
        logs = run_async(repo.get_by_type("research_aggregated"))

        if not logs:
            return False

        # Get most recent research
        latest = logs[0]
        created_at = latest.get("created_at")

        if not created_at:
            return False

        # Parse ISO timestamp
        if isinstance(created_at, str):
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_dt = created_at

        age_hours = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds() / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


def _save_aggregated_findings(findings: ResearchFindings, project_name: str) -> None:
    """Save aggregated findings to database.

    Args:
        findings: Aggregated findings
        project_name: Project name for DB storage
    """
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    repo = get_logs_repository(project_name)
    run_async(repo.create_log(log_type="research_aggregated", content=findings.to_dict()))


async def quick_research(project_dir: Path) -> ResearchFindings:
    """Run quick research synchronously for testing.

    A simplified version that doesn't spawn agents but directly
    analyzes files for quick results.

    Args:
        project_dir: Project directory

    Returns:
        Research findings
    """
    findings = ResearchFindings()

    # Quick tech stack analysis
    findings.tech_stack = _quick_tech_stack_analysis(project_dir)

    # Quick pattern analysis
    findings.existing_patterns = _quick_pattern_analysis(project_dir)

    findings.completed_at = datetime.now().isoformat()

    return findings


def _quick_tech_stack_analysis(project_dir: Path) -> dict:
    """Quick analysis of tech stack from config files.

    Args:
        project_dir: Project directory

    Returns:
        Tech stack info
    """
    result = {
        "languages": [],
        "frameworks": [],
        "libraries": [],
        "dev_tools": [],
        "constraints": [],
    }

    # Check package.json
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text())
            result["languages"].append(
                "javascript" if "typescript" not in str(pkg) else "typescript"
            )

            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Detect frameworks
            if "react" in deps:
                result["frameworks"].append({"name": "react", "version": deps.get("react", "")})
            if "vue" in deps:
                result["frameworks"].append({"name": "vue", "version": deps.get("vue", "")})
            if "next" in deps:
                result["frameworks"].append({"name": "next", "version": deps.get("next", "")})
            if "express" in deps:
                result["frameworks"].append({"name": "express", "version": deps.get("express", "")})

            # Detect dev tools
            if "jest" in deps:
                result["dev_tools"].append("jest")
            if "vitest" in deps:
                result["dev_tools"].append("vitest")
            if "eslint" in deps:
                result["dev_tools"].append("eslint")
            if "prettier" in deps:
                result["dev_tools"].append("prettier")

        except json.JSONDecodeError:
            pass

    # Check pyproject.toml
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            result["languages"].append("python")

            if "fastapi" in content:
                result["frameworks"].append({"name": "fastapi", "version": ""})
            if "django" in content:
                result["frameworks"].append({"name": "django", "version": ""})
            if "flask" in content:
                result["frameworks"].append({"name": "flask", "version": ""})

            if "pytest" in content:
                result["dev_tools"].append("pytest")
            if "ruff" in content:
                result["dev_tools"].append("ruff")
            if "black" in content:
                result["dev_tools"].append("black")
            if "mypy" in content:
                result["dev_tools"].append("mypy")

        except Exception:
            pass

    # Check go.mod
    go_mod = project_dir / "go.mod"
    if go_mod.exists():
        result["languages"].append("go")

    # Check Cargo.toml
    cargo_toml = project_dir / "Cargo.toml"
    if cargo_toml.exists():
        result["languages"].append("rust")

    # Deduplicate
    result["languages"] = list(set(result["languages"]))
    result["dev_tools"] = list(set(result["dev_tools"]))

    return result


def _quick_pattern_analysis(project_dir: Path) -> dict:
    """Quick analysis of code patterns.

    Args:
        project_dir: Project directory

    Returns:
        Pattern info
    """
    result = {
        "architecture": "unknown",
        "folder_structure": "unknown",
        "naming": {},
        "testing": {},
        "error_handling": "unknown",
    }

    src_dir = project_dir / "src"
    if not src_dir.exists():
        src_dir = project_dir

    # Detect folder structure
    common_dirs = ["services", "repositories", "controllers", "api", "domain", "models", "utils"]
    found_dirs = [d for d in common_dirs if (src_dir / d).exists()]

    if found_dirs:
        if "domain" in found_dirs or "repositories" in found_dirs:
            result["architecture"] = "Clean architecture / DDD"
        elif "controllers" in found_dirs:
            result["architecture"] = "MVC pattern"
        elif "services" in found_dirs:
            result["architecture"] = "Service-oriented"

        result["folder_structure"] = (
            "feature-based" if (src_dir / "features").exists() else "layer-based"
        )

    # Detect testing structure
    tests_dir = project_dir / "tests"
    if not tests_dir.exists():
        tests_dir = project_dir / "test"

    if tests_dir.exists():
        result["testing"]["structure"] = "dedicated tests directory"
        if (tests_dir / "unit").exists():
            result["testing"]["types"] = ["unit", "integration"]
        else:
            result["testing"]["types"] = ["mixed"]

    # Check for naming patterns from a sample file
    for pattern in ["**/*.py", "**/*.ts", "**/*.js"]:
        files = list(src_dir.glob(pattern))[:5]
        if files:
            # Check file naming
            names = [f.stem for f in files]
            if all("_" in n or n.islower() for n in names):
                result["naming"]["files"] = "snake_case"
            elif all(n[0].isupper() for n in names if n):
                result["naming"]["files"] = "PascalCase"
            else:
                result["naming"]["files"] = "mixed"
            break

    return result
