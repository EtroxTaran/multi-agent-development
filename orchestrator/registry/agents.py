"""
Agent registry with full metadata for all specialist agents.

This module defines the complete registry of all available agents in the
multi-agent orchestration system. Each agent has defined capabilities,
tool restrictions, reviewers, and file access boundaries.

Usage:
    from orchestrator.registry import AGENT_REGISTRY, get_agent

    agent = get_agent("A04")
    print(agent.name)  # "Implementer"
    print(agent.reviewers)  # ["A07", "A08"]
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration for a specialist agent."""

    id: str
    name: str
    description: str
    primary_cli: str  # "claude" | "cursor" | "gemini"
    backup_cli: Optional[str] = None
    context_file: Optional[str] = None  # Path to CLAUDE.md, GEMINI.md, etc.
    tools_file: Optional[str] = None  # Path to TOOLS.json
    reviewers: list[str] = field(default_factory=list)  # Agent IDs that review this agent
    fallback_reviewer: Optional[str] = None  # Fallback if primary reviewers unavailable
    can_write_files: bool = False
    can_read_files: bool = True
    allowed_paths: list[str] = field(default_factory=list)  # Glob patterns for writable paths
    forbidden_paths: list[str] = field(default_factory=list)  # Glob patterns never writable
    output_schema: Optional[str] = None  # JSON schema for output validation
    max_iterations: int = 3
    timeout_seconds: int = 600  # 10 minutes default
    is_reviewer: bool = False  # Whether this agent can review others
    review_specialization: Optional[str] = None  # "security" | "code_quality" | "architecture"
    weight_in_conflicts: float = 0.5  # Weight when resolving review conflicts
    # Loop execution metadata (for unified loop pattern)
    supports_loop: bool = True  # Whether agent can be used in iterative loops
    completion_patterns: list[str] = field(default_factory=list)  # Patterns that signal completion
    available_models: list[str] = field(default_factory=list)  # Available model options
    default_model: Optional[str] = None  # Default model to use
    # Prompt template metadata
    prompt_template_type: str = "writer"  # "planner" | "writer" | "reviewer"


# Complete Agent Registry
AGENT_REGISTRY: dict[str, AgentConfig] = {
    # =========================================================================
    # PLANNING AGENTS
    # =========================================================================
    "A01": AgentConfig(
        id="A01",
        name="Planner",
        description="Breaks down features into tasks with dependencies and acceptance criteria",
        primary_cli="claude",
        backup_cli="gemini",
        context_file="agents/A01-planner/CLAUDE.md",
        tools_file="agents/A01-planner/TOOLS.json",
        reviewers=["A08", "A02"],
        fallback_reviewer="A07",
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[],
        forbidden_paths=["src/**/*", "tests/**/*", "*.py", "*.ts", "*.js"],
        output_schema="schemas/planner_output.json",
        max_iterations=3,
        timeout_seconds=600,
        prompt_template_type="planner",
    ),
    "A02": AgentConfig(
        id="A02",
        name="Architect",
        description="Reviews architectural decisions and system design",
        primary_cli="gemini",
        backup_cli="claude",
        context_file="agents/A02-architect/GEMINI.md",
        tools_file="agents/A02-architect/TOOLS.json",
        reviewers=["A08", "A07"],
        fallback_reviewer="A01",
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[],
        forbidden_paths=["src/**/*", "tests/**/*"],
        output_schema="schemas/architect_output.json",
        max_iterations=2,
        timeout_seconds=480,
        is_reviewer=True,
        review_specialization="architecture",
        weight_in_conflicts=0.7,
        prompt_template_type="reviewer",
    ),
    # =========================================================================
    # TESTING AGENTS
    # =========================================================================
    "A03": AgentConfig(
        id="A03",
        name="Test Writer",
        description="Writes failing tests first following TDD principles",
        primary_cli="claude",
        backup_cli="cursor",
        context_file="agents/A03-test-writer/CLAUDE.md",
        tools_file="agents/A03-test-writer/TOOLS.json",
        reviewers=["A08", "A07"],
        fallback_reviewer="A04",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=["tests/**/*", "test/**/*", "spec/**/*", "*.test.*", "*.spec.*"],
        forbidden_paths=["src/**/*", "lib/**/*", "app/**/*"],
        output_schema="schemas/test_writer_output.json",
        max_iterations=3,
        timeout_seconds=600,
    ),
    "A10": AgentConfig(
        id="A10",
        name="Integration Tester",
        description="Writes integration, BDD/Gherkin, and E2E Playwright tests",
        primary_cli="claude",
        backup_cli="cursor",
        context_file="agents/A10-integration-tester/CLAUDE.md",
        tools_file="agents/A10-integration-tester/TOOLS.json",
        reviewers=["A07", "A08"],
        fallback_reviewer="A04",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=[
            "tests/**/*",
            "test/**/*",
            "e2e/**/*",
            "features/**/*",
            "*.feature",
        ],
        forbidden_paths=["src/**/*", "lib/**/*", "app/**/*"],
        output_schema="schemas/integration_tester_output.json",
        max_iterations=3,
        timeout_seconds=900,  # 15 minutes for E2E
    ),
    # =========================================================================
    # IMPLEMENTATION AGENTS
    # =========================================================================
    "A04": AgentConfig(
        id="A04",
        name="Implementer",
        description="Writes minimal code to make tests pass",
        primary_cli="claude",
        backup_cli="cursor",
        context_file="agents/A04-implementer/CLAUDE.md",
        tools_file="agents/A04-implementer/TOOLS.json",
        reviewers=["A07", "A08"],
        fallback_reviewer="A05",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=["src/**/*", "lib/**/*", "app/**/*", "*.py", "*.ts", "*.js"],
        forbidden_paths=["tests/**/*", "test/**/*", "*.md", ".workflow/**/*"],
        output_schema="schemas/implementer_output.json",
        max_iterations=3,
        timeout_seconds=600,
        # Loop execution metadata
        supports_loop=True,
        completion_patterns=["<promise>DONE</promise>", '"status": "completed"'],
        available_models=["sonnet", "opus", "haiku"],
        default_model="sonnet",
    ),
    "A05": AgentConfig(
        id="A05",
        name="Bug Fixer",
        description="Diagnoses and fixes bugs with root cause analysis",
        primary_cli="cursor",
        backup_cli="claude",
        context_file="agents/A05-bug-fixer/CURSOR-RULES.md",
        tools_file="agents/A05-bug-fixer/TOOLS.json",
        reviewers=["A10", "A08"],
        fallback_reviewer="A07",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=["src/**/*", "lib/**/*", "tests/**/*"],
        forbidden_paths=["*.md", ".workflow/**/*"],
        output_schema="schemas/bug_fixer_output.json",
        max_iterations=5,  # More iterations for complex bugs
        timeout_seconds=720,
        # Loop execution metadata
        supports_loop=True,
        completion_patterns=['"status": "done"', '"status": "completed"'],
        available_models=["codex-5.2", "composer"],
        default_model="codex-5.2",
    ),
    "A06": AgentConfig(
        id="A06",
        name="Refactorer",
        description="Refactors code while keeping tests green",
        primary_cli="gemini",
        backup_cli="cursor",
        context_file="agents/A06-refactorer/GEMINI.md",
        tools_file="agents/A06-refactorer/TOOLS.json",
        reviewers=["A08", "A07"],
        fallback_reviewer="A04",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=["src/**/*", "lib/**/*", "app/**/*"],
        forbidden_paths=["tests/**/*", "*.md", ".workflow/**/*"],
        output_schema="schemas/refactorer_output.json",
        max_iterations=3,
        timeout_seconds=600,
        # Loop execution metadata
        supports_loop=True,
        completion_patterns=["DONE", "COMPLETE", '"status": "done"'],
        available_models=["gemini-2.0-flash", "gemini-2.0-pro"],
        default_model="gemini-2.0-flash",
    ),
    # =========================================================================
    # REVIEW AGENTS
    # =========================================================================
    "A07": AgentConfig(
        id="A07",
        name="Security Reviewer",
        description="Reviews code for OWASP Top 10 and security vulnerabilities",
        primary_cli="cursor",
        backup_cli="claude",
        context_file="agents/A07-security-reviewer/CURSOR-RULES.md",
        tools_file="agents/A07-security-reviewer/TOOLS.json",
        reviewers=[],  # Reviewers don't get reviewed
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[],
        forbidden_paths=["**/*"],  # Read only
        output_schema="schemas/reviewer_output.json",
        max_iterations=2,
        timeout_seconds=300,
        is_reviewer=True,
        review_specialization="security",
        weight_in_conflicts=0.8,  # High weight for security
        prompt_template_type="reviewer",
    ),
    "A08": AgentConfig(
        id="A08",
        name="Code Reviewer",
        description="Reviews code quality, patterns, and best practices",
        primary_cli="gemini",
        backup_cli="cursor",
        context_file="agents/A08-code-reviewer/GEMINI.md",
        tools_file="agents/A08-code-reviewer/TOOLS.json",
        reviewers=[],  # Reviewers don't get reviewed
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[],
        forbidden_paths=["**/*"],  # Read only
        output_schema="schemas/reviewer_output.json",
        max_iterations=2,
        timeout_seconds=300,
        is_reviewer=True,
        review_specialization="code_quality",
        weight_in_conflicts=0.6,
        prompt_template_type="reviewer",
    ),
    # =========================================================================
    # DOCUMENTATION AGENTS
    # =========================================================================
    "A09": AgentConfig(
        id="A09",
        name="Documentation Writer",
        description="Writes and updates documentation",
        primary_cli="claude",
        backup_cli="gemini",
        context_file="agents/A09-documentation/CLAUDE.md",
        tools_file="agents/A09-documentation/TOOLS.json",
        reviewers=["A08", "A01"],
        fallback_reviewer="A02",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=["docs/**/*", "*.md", "README*"],
        forbidden_paths=["src/**/*", "tests/**/*", "*.py", "*.ts"],
        output_schema="schemas/documentation_output.json",
        max_iterations=2,
        timeout_seconds=480,
    ),
    # =========================================================================
    # DEVOPS AGENTS
    # =========================================================================
    "A11": AgentConfig(
        id="A11",
        name="DevOps Engineer",
        description="Manages CI/CD, deployment, and infrastructure",
        primary_cli="cursor",
        backup_cli="claude",
        context_file="agents/A11-devops/CURSOR-RULES.md",
        tools_file="agents/A11-devops/TOOLS.json",
        reviewers=["A07", "A08"],
        fallback_reviewer="A05",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=[
            ".github/**/*",
            "Dockerfile*",
            "docker-compose*",
            "*.yaml",
            "*.yml",
            "Makefile",
            "scripts/**/*",
        ],
        forbidden_paths=["src/**/*", "tests/**/*"],
        output_schema="schemas/devops_output.json",
        max_iterations=3,
        timeout_seconds=600,
    ),
    # =========================================================================
    # UI/DESIGN AGENTS
    # =========================================================================
    "A12": AgentConfig(
        id="A12",
        name="UI Designer",
        description="Creates and refines UI components and styling",
        primary_cli="claude",
        backup_cli="cursor",
        context_file="agents/A12-ui-designer/CLAUDE.md",
        tools_file="agents/A12-ui-designer/TOOLS.json",
        reviewers=["A08", "A07"],
        fallback_reviewer="A04",
        can_write_files=True,
        can_read_files=True,
        allowed_paths=[
            "src/components/**/*",
            "src/ui/**/*",
            "src/styles/**/*",
            "*.css",
            "*.scss",
            "*.tsx",
        ],
        forbidden_paths=["tests/**/*", "*.md", ".workflow/**/*"],
        output_schema="schemas/ui_designer_output.json",
        max_iterations=3,
        timeout_seconds=600,
    ),
    # =========================================================================
    # QUALITY INFRASTRUCTURE AGENTS
    # =========================================================================
    "A13": AgentConfig(
        id="A13",
        name="Quality Gate",
        description="TypeScript strict mode, ESLint, naming conventions, code structure checks",
        primary_cli="cursor",
        backup_cli="claude",
        context_file="agents/A13-quality-gate/CURSOR-RULES.md",
        tools_file="agents/A13-quality-gate/TOOLS.json",
        reviewers=[],  # Top-level automated reviewer (like A07/A08)
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[],
        forbidden_paths=["**/*"],  # Read only
        output_schema="schemas/quality_gate_output.json",
        max_iterations=2,
        timeout_seconds=300,
        is_reviewer=True,
        review_specialization="code_quality",
        weight_in_conflicts=0.7,  # High weight for quality enforcement
        prompt_template_type="reviewer",
    ),
    "A14": AgentConfig(
        id="A14",
        name="Dependency Checker",
        description="Outdated dependencies, Docker security, version compatibility analysis",
        primary_cli="claude",
        backup_cli="cursor",
        context_file="agents/A14-dependency-checker/CLAUDE.md",
        tools_file="agents/A14-dependency-checker/TOOLS.json",
        reviewers=["A07", "A08"],  # Security and Code reviewers check dependency changes
        fallback_reviewer="A11",  # DevOps as fallback
        can_write_files=True,
        can_read_files=True,
        allowed_paths=[
            "package.json",
            "package-lock.json",
            "Dockerfile*",
            "docker-compose*",
            "CHANGELOG.md",
            "README.md",
            ".github/dependabot.yml",
            ".github/renovate.json",
        ],
        forbidden_paths=["src/**/*", "tests/**/*", "lib/**/*", "app/**/*"],
        output_schema="schemas/dependency_checker_output.json",
        max_iterations=3,
        timeout_seconds=480,
    ),
    "A15": AgentConfig(
        id="A15",
        name="Watchdog Agent",
        description="Proactive runtime error monitoring and self-healing",
        primary_cli="python",
        backup_cli=None,
        context_file=None,
        tools_file=None,
        reviewers=["A08", "A07"],
        fallback_reviewer=None,
        can_write_files=False,
        can_read_files=True,
        allowed_paths=[
            ".workflow/errors/**/*",
            "logs/**/*",
        ],
        forbidden_paths=[],
        output_schema=None,
        max_iterations=0,
        timeout_seconds=0,
    ),
}


def get_agent(agent_id: str) -> AgentConfig:
    """Get agent configuration by ID.

    Args:
        agent_id: The agent identifier (e.g., "A01", "A04")

    Returns:
        AgentConfig for the specified agent

    Raises:
        KeyError: If agent_id is not found in registry
    """
    if agent_id not in AGENT_REGISTRY:
        raise KeyError(
            f"Agent '{agent_id}' not found in registry. "
            f"Available agents: {list(AGENT_REGISTRY.keys())}"
        )
    return AGENT_REGISTRY[agent_id]


def get_agent_reviewers(agent_id: str) -> list[AgentConfig]:
    """Get the reviewer agents for a given agent.

    Args:
        agent_id: The agent identifier

    Returns:
        List of AgentConfig for reviewers
    """
    agent = get_agent(agent_id)
    reviewers = []
    for reviewer_id in agent.reviewers:
        try:
            reviewers.append(get_agent(reviewer_id))
        except KeyError:
            pass  # Skip missing reviewers
    return reviewers


def get_all_agents() -> list[AgentConfig]:
    """Get all registered agents.

    Returns:
        List of all AgentConfig in registry
    """
    return list(AGENT_REGISTRY.values())


def get_agents_by_cli(cli: str) -> list[AgentConfig]:
    """Get agents that use a specific CLI as primary.

    Args:
        cli: CLI name ("claude", "cursor", "gemini")

    Returns:
        List of AgentConfig using that CLI
    """
    return [agent for agent in AGENT_REGISTRY.values() if agent.primary_cli == cli]


def get_reviewer_agents() -> list[AgentConfig]:
    """Get all agents that can act as reviewers.

    Returns:
        List of AgentConfig where is_reviewer=True
    """
    return [agent for agent in AGENT_REGISTRY.values() if agent.is_reviewer]


def validate_agent_can_write(agent_id: str, file_path: str) -> bool:
    """Check if an agent is allowed to write to a specific path.

    Args:
        agent_id: The agent identifier
        file_path: Path to validate (relative to project root)

    Returns:
        True if agent can write to path, False otherwise
    """
    import fnmatch

    agent = get_agent(agent_id)

    if not agent.can_write_files:
        return False

    # Check forbidden paths first
    for pattern in agent.forbidden_paths:
        if fnmatch.fnmatch(file_path, pattern):
            return False

    # Check allowed paths
    if not agent.allowed_paths:
        return True  # No restrictions beyond forbidden

    for pattern in agent.allowed_paths:
        if fnmatch.fnmatch(file_path, pattern):
            return True

    return False


def get_review_pairings() -> dict[str, dict[str, str]]:
    """Get the review pairings for all working agents.

    Returns:
        Dict mapping agent_id to their reviewers and weights
    """
    pairings = {}
    for agent_id, agent in AGENT_REGISTRY.items():
        if not agent.is_reviewer and agent.reviewers:
            reviewers = get_agent_reviewers(agent_id)
            pairings[agent_id] = {
                "reviewers": [r.id for r in reviewers],
                "reviewer_clis": [r.primary_cli for r in reviewers],
                "fallback": agent.fallback_reviewer,
                "weights": {r.id: r.weight_in_conflicts for r in reviewers},
            }
    return pairings
