"""Model configuration and constants.

Central source of truth for AI model versions across the system.
Updated for January 2026 standards.
"""

from typing import List

# --- Claude Models ---
CLAUDE_OPUS = "claude-4-5-opus"
CLAUDE_SONNET = "claude-4-5-sonnet"
CLAUDE_HAIKU = "claude-4-5-haiku"

CLAUDE_MODELS: List[str] = [
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

GEMINI_MODELS: List[str] = [
    GEMINI_FLASH,
    GEMINI_PRO,
    # Backward compatibility
    "gemini-2.0-flash",
    "gemini-2.0-pro",
]

DEFAULT_GEMINI_MODEL = GEMINI_FLASH


# --- Cursor Models ---
CURSOR_CODEX = "gpt-5.2-codex"
CURSOR_COMPOSER = "composer-v2"
CURSOR_GPT4O = "gpt-4o"

CURSOR_MODELS: List[str] = [
    CURSOR_CODEX,
    CURSOR_COMPOSER,
    CURSOR_GPT4O,
    # Backward compatibility
    "codex-5.2",
    "composer",
]

DEFAULT_CURSOR_MODEL = CURSOR_CODEX


def get_model_list(agent_type: str) -> List[str]:
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
