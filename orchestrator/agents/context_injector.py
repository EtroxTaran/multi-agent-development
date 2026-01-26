"""Context injection for agent prompts.

Loads context from collection/rules/ and injects into prompts at invocation time.
This allows agent .md files to be minimal while prompts get task-specific rules.

Usage:
    from orchestrator.agents.context_injector import get_context_for_prompt

    context = get_context_for_prompt("cursor", "validation")
    prompt = format_prompt(template, plan=plan_json, context=context)
"""

import logging
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

AgentType = Literal["claude", "cursor", "gemini"]
TaskType = Literal["planning", "implementation", "validation", "review", "security", "research"]

# Collection directory relative to this module
COLLECTION_DIR = Path(__file__).parent.parent.parent / "collection"


def get_context_for_prompt(agent: AgentType, task_type: TaskType) -> str:
    """Get context to inject into a prompt for a specific agent and task.

    Args:
        agent: The agent being called (claude, cursor, gemini)
        task_type: What kind of task this is

    Returns:
        Formatted context section to inject into prompt
    """
    sections = []

    # 1. Core rules everyone needs
    core = _load_rule_file("guardrails", "core.md")
    if core:
        sections.append(core)

    # 2. Task-specific rules
    if task_type in ("implementation", "review"):
        # Use existing code-quality.md file
        quality = _load_rule_file("guardrails", "code-quality.md")
        if quality:
            sections.append(quality)

    if task_type in ("validation", "review", "security"):
        # Use existing security-guardrails.md file
        security = _load_rule_file("guardrails", "security-guardrails.md")
        if security:
            sections.append(security)

    # 3. Agent-specific rules
    if agent == "claude":
        if task_type in ("implementation", "planning"):
            # Use existing tdd-workflow.md file
            tdd = _load_rule_file("workflows", "tdd-workflow.md")
            if tdd:
                sections.append(tdd)

    elif agent == "cursor":
        # Cursor focuses on security - already added above
        pass

    elif agent == "gemini":
        arch = _load_rule_file("guardrails", "architecture.md")
        if arch:
            sections.append(arch)

    if not sections:
        logger.warning(f"No context loaded for agent={agent}, task_type={task_type}")
        return ""

    return "\n\n".join(sections)


def _load_rule_file(category: str, filename: str) -> Optional[str]:
    """Load a rule file from the collection.

    Args:
        category: Subdirectory under rules/ (guardrails, coding-standards, workflows)
        filename: The markdown file to load

    Returns:
        File contents or None if not found
    """
    path = COLLECTION_DIR / "rules" / category / filename
    if not path.exists():
        logger.debug(f"Rule file not found: {path}")
        return None

    try:
        content = path.read_text().strip()
        return content
    except Exception as e:
        logger.warning(f"Failed to load rule file {path}: {e}")
        return None


def get_agent_identity(agent: AgentType) -> str:
    """Get minimal identity context for an agent.

    This is the core identity that should always be included,
    regardless of task type.

    Args:
        agent: The agent type

    Returns:
        Identity section for the agent
    """
    identities = {
        "claude": """## Your Role
You are implementing code following TDD principles. Write tests first, then implementation.""",
        "cursor": """## Your Role
You are a Senior Code Reviewer focusing on code quality and security.
Check for OWASP Top 10 vulnerabilities and maintainability issues.""",
        "gemini": """## Your Role
You are a Senior Software Architect focusing on architecture and scalability.
Evaluate design patterns, modularity, and long-term maintainability.""",
    }
    return identities.get(agent, "")
