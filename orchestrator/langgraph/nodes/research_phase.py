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
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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
]


@dataclass
class ResearchFindings:
    """Aggregated research findings from all agents."""

    tech_stack: Optional[dict] = None
    existing_patterns: Optional[dict] = None
    errors: list[dict] = field(default_factory=list)
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tech_stack": self.tech_stack,
            "existing_patterns": self.existing_patterns,
            "errors": self.errors,
            "completed_at": self.completed_at,
        }


async def research_phase_node(state: WorkflowState) -> dict[str, Any]:
    """Spawn parallel research agents before planning.

    Runs 2 research agents concurrently:
    1. Tech stack analyzer - examines dependencies and tools
    2. Pattern analyzer - examines code patterns and conventions

    Results are saved to .workflow/phases/research/ and used
    during planning to make informed decisions.

    Args:
        state: Current workflow state

    Returns:
        State updates with research findings
    """
    project_dir = Path(state["project_dir"])
    research_dir = project_dir / ".workflow" / "phases" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting research phase with parallel agents")

    # Check if research already exists and is recent
    existing_findings = _load_existing_research(research_dir)
    if existing_findings and _is_research_fresh(research_dir):
        logger.info("Using existing research findings (less than 1 hour old)")
        return {
            "research_complete": True,
            "research_findings": existing_findings.to_dict(),
            "updated_at": datetime.now().isoformat(),
        }

    # Run research agents in parallel
    findings = ResearchFindings()
    project_name = state["project_name"]

    try:
        # Spawn agents concurrently
        tasks = [
            _run_research_agent(project_dir, agent, research_dir, project_name)
            for agent in RESEARCH_AGENTS
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for agent, result in zip(RESEARCH_AGENTS, results):
            if isinstance(result, Exception):
                logger.warning(f"Research agent {agent.id} failed: {result}")
                findings.errors.append({
                    "agent": agent.id,
                    "error": str(result),
                    "timestamp": datetime.now().isoformat(),
                })
            else:
                # Store result
                if agent.id == "tech_stack":
                    findings.tech_stack = result
                elif agent.id == "existing_patterns":
                    findings.existing_patterns = result

        findings.completed_at = datetime.now().isoformat()

        # Save aggregated findings to database
        _save_aggregated_findings(research_dir, findings, project_name)

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
            "errors": [{
                "type": "research_phase_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
            "updated_at": datetime.now().isoformat(),
        }


async def _run_research_agent(
    project_dir: Path,
    agent: ResearchAgent,
    output_dir: Path,
    project_name: str,
) -> dict:
    """Run a single research agent.

    Args:
        project_dir: Project directory to analyze
        agent: Research agent definition
        output_dir: Directory to save results (unused - DB storage)
        project_name: Project name for DB storage

    Returns:
        Parsed research findings as dict

    Raises:
        Exception: If agent fails or times out
    """
    logger.info(f"Running research agent: {agent.name}")

    # Build prompt for agent
    prompt = f"""You are a research agent analyzing a codebase before implementation planning.

PROJECT DIRECTORY: {project_dir}

{agent.prompt}

IMPORTANT:
- Only report what you actually find in the codebase
- If you can't find something, report it as null/empty
- Be concise and factual
- Output ONLY the JSON object, no other text
"""

    try:
        # Run Claude with research prompt
        result = await asyncio.wait_for(
            _spawn_claude_agent(project_dir, prompt),
            timeout=RESEARCH_TIMEOUT,
        )

        # Parse JSON output
        parsed = _parse_research_output(result)

        # Save to database
        from ...db.repositories.logs import get_logs_repository
        from ...storage.async_utils import run_async

        repo = get_logs_repository(project_name)
        run_async(repo.save(log_type="research", content={"agent_id": agent.id, "findings": parsed}))
        logger.info(f"Research agent {agent.id} saved results to database")

        return parsed

    except asyncio.TimeoutError:
        raise Exception(f"Research agent {agent.id} timed out after {RESEARCH_TIMEOUT}s")
    except Exception as e:
        raise Exception(f"Research agent {agent.id} failed: {e}")


async def _spawn_claude_agent(project_dir: Path, prompt: str) -> str:
    """Spawn a Claude agent for research.

    Uses read-only tools to analyze the codebase without modification.

    Args:
        project_dir: Project directory
        prompt: Research prompt

    Returns:
        Raw agent output
    """
    # Use limited tools for research (read-only)
    allowed_tools = "Read,Glob,Grep"

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


def _load_existing_research(research_dir: Path) -> Optional[ResearchFindings]:
    """Load existing research findings if available.

    Args:
        research_dir: Research output directory

    Returns:
        ResearchFindings or None
    """
    aggregated_file = research_dir / "findings.json"
    if not aggregated_file.exists():
        return None

    try:
        data = json.loads(aggregated_file.read_text())
        return ResearchFindings(
            tech_stack=data.get("tech_stack"),
            existing_patterns=data.get("existing_patterns"),
            errors=data.get("errors", []),
            completed_at=data.get("completed_at"),
        )
    except Exception:
        return None


def _is_research_fresh(research_dir: Path, max_age_hours: int = 1) -> bool:
    """Check if research is recent enough to reuse.

    Args:
        research_dir: Research output directory
        max_age_hours: Maximum age in hours

    Returns:
        True if research is fresh
    """
    aggregated_file = research_dir / "findings.json"
    if not aggregated_file.exists():
        return False

    try:
        mtime = aggregated_file.stat().st_mtime
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


def _save_aggregated_findings(research_dir: Path, findings: ResearchFindings, project_name: str) -> None:
    """Save aggregated findings to database.

    Args:
        research_dir: Research output directory (unused - DB storage)
        findings: Aggregated findings
        project_name: Project name for DB storage
    """
    from ...db.repositories.logs import get_logs_repository
    from ...storage.async_utils import run_async

    repo = get_logs_repository(project_name)
    run_async(repo.save(log_type="research_aggregated", content=findings.to_dict()))


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
            result["languages"].append("javascript" if "typescript" not in str(pkg) else "typescript")

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

        result["folder_structure"] = "feature-based" if (src_dir / "features").exists() else "layer-based"

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
