"""Model configuration and constants.

Central source of truth for AI model versions across the system.
Updated for January 2026 standards.
"""


# --- Claude Models ---
CLAUDE_OPUS = "claude-4-5-opus"
CLAUDE_SONNET = "claude-4-5-sonnet"
CLAUDE_HAIKU = "claude-4-5-haiku"

CLAUDE_MODELS: list[str] = [
    CLAUDE_SONNET,
    CLAUDE_OPUS,
    CLAUDE_HAIKU,
    # Backward compatibility / specific versions
    "claude-3-5-sonnet",
    "claude-3-opus",
]

DEFAULT_CLAUDE_MODEL = CLAUDE_SONNET


# --- Gemini Models ---
GEMINI_FLASH = "gemini-3-flash"
GEMINI_PRO = "gemini-3-pro"

GEMINI_MODELS: list[str] = [
    GEMINI_FLASH,
    GEMINI_PRO,
    # Backward compatibility
    "gemini-2.0-flash",
    "gemini-2.0-pro",
]

DEFAULT_GEMINI_MODEL = GEMINI_PRO
DEFAULT_ARCHITECT_MODEL = GEMINI_PRO


# --- Cursor Models ---
CURSOR_CODEX = "gpt-5.2-codex"
CURSOR_COMPOSER = "composer-v2"
CURSOR_GPT4O = "gpt-4o"

CURSOR_MODELS: list[str] = [
    CURSOR_CODEX,
    CURSOR_COMPOSER,
    CURSOR_GPT4O,
    # Backward compatibility
    "codex-5.2",
    "composer",
    "auto",
]

DEFAULT_CURSOR_MODEL = CURSOR_CODEX


def get_model_list(agent_type: str) -> list[str]:
    """Get available models for a specific agent type."""
    if agent_type.lower() == "claude":
        return CLAUDE_MODELS
    elif agent_type.lower() == "gemini":
        return GEMINI_MODELS
    elif agent_type.lower() == "cursor":
        return CURSOR_MODELS
    return []


def get_default_model(agent_type: str) -> str:
    """Get default model for a specific agent type."""
    if agent_type.lower() == "claude":
        return DEFAULT_CLAUDE_MODEL
    elif agent_type.lower() == "gemini":
        return DEFAULT_GEMINI_MODEL
    elif agent_type.lower() == "cursor":
        return DEFAULT_CURSOR_MODEL
    return ""


# --- Dynamic Role Dispatch ---

from dataclasses import dataclass
from enum import Enum


class TaskType(str, Enum):
    """Inferred task type for role dispatch."""

    ARCHITECTURE = "architecture"
    SECURITY = "security"
    OPTIMIZATION = "optimization"
    GENERAL = "general"


@dataclass
class RoleAssignment:
    """Agent and model assignment for a task type."""

    primary_agent: str  # "cursor" | "gemini" | "claude"
    model: str
    cursor_weight: float = 0.6  # For ConflictResolver
    gemini_weight: float = 0.4


# Role dispatch rules mapping task types to optimal agents/weights
ROLE_DISPATCH_RULES: dict[TaskType, RoleAssignment] = {
    TaskType.ARCHITECTURE: RoleAssignment(
        "gemini", GEMINI_PRO, cursor_weight=0.3, gemini_weight=0.7
    ),
    TaskType.SECURITY: RoleAssignment("cursor", CURSOR_CODEX, cursor_weight=0.8, gemini_weight=0.2),
    TaskType.OPTIMIZATION: RoleAssignment(
        "claude", CLAUDE_OPUS, cursor_weight=0.5, gemini_weight=0.5
    ),
    TaskType.GENERAL: RoleAssignment("cursor", CURSOR_CODEX, cursor_weight=0.6, gemini_weight=0.4),
}


# Patterns for inferring task type from task properties
TASK_TYPE_PATTERNS: dict[TaskType, dict[str, list[str]]] = {
    TaskType.SECURITY: {
        "file_patterns": ["security", "auth", "crypto", "permission"],
        "keywords": ["vulnerability", "owasp", "xss", "csrf", "injection", "authentication"],
    },
    TaskType.ARCHITECTURE: {
        "file_patterns": ["config", "core", "interface", "abstract"],
        "keywords": ["architecture", "scalab", "design pattern", "refactor", "migration"],
    },
    TaskType.OPTIMIZATION: {
        "file_patterns": ["cache", "pool", "batch", "async"],
        "keywords": ["performance", "optimiz", "latency", "throughput", "memory"],
    },
}


def infer_task_type(task: dict) -> TaskType:
    """Infer task type from task properties.

    Analyzes task title, user story, acceptance criteria, and file paths
    to determine the most appropriate task type for role dispatch.

    Args:
        task: Task dictionary with title, user_story, acceptance_criteria, files_to_create, files_to_modify

    Returns:
        Inferred TaskType enum value
    """
    # Build searchable text from task properties
    text = " ".join(
        [
            task.get("title", ""),
            task.get("user_story", ""),
            " ".join(task.get("acceptance_criteria", [])),
        ]
    ).lower()

    files = task.get("files_to_create", []) + task.get("files_to_modify", [])
    files_str = " ".join(files).lower()

    # Score each task type
    scores: dict[TaskType, int] = {tt: 0 for tt in TaskType if tt != TaskType.GENERAL}

    for task_type, patterns in TASK_TYPE_PATTERNS.items():
        # File pattern matches (weighted higher)
        for fp in patterns["file_patterns"]:
            if fp in files_str:
                scores[task_type] += 2
        # Keyword matches
        for kw in patterns["keywords"]:
            if kw in text:
                scores[task_type] += 1

    # Boost architecture score for high complexity tasks
    if task.get("estimated_complexity") == "high":
        scores[TaskType.ARCHITECTURE] += 1

    # Return highest scoring type, or GENERAL if no matches
    max_score = max(scores.values())
    if max_score > 0:
        for tt, score in scores.items():
            if score == max_score:
                return tt

    return TaskType.GENERAL


def get_role_assignment(task: dict) -> RoleAssignment:
    """Get best agent/model assignment for a task.

    Args:
        task: Task dictionary

    Returns:
        RoleAssignment with primary_agent, model, and weights
    """
    task_type = infer_task_type(task)
    return ROLE_DISPATCH_RULES[task_type]
