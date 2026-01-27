"""Prompt templates for CLI agent wrappers.

This module provides optimized prompts for each agent method with:
- Clear role/identity
- Structured input/output specifications
- Error handling guidance
- Few-shot examples
- Anti-patterns to avoid
- Prompt injection protection

Usage:
    from orchestrator.agents.prompts import load_prompt, format_prompt

    template = load_prompt("claude", "planning")
    prompt = format_prompt(template, product_spec=spec, validate_injection=True)
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ...security import detect_prompt_injection

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent

# Default maximum content length to prevent context overflow
DEFAULT_MAX_LENGTH = 50000


def load_prompt(agent: str, method: str) -> str:
    """Load a prompt template for an agent method.

    Args:
        agent: Agent name (claude, cursor, gemini)
        method: Method name (planning, implementation, validation, etc.)

    Returns:
        Prompt template string

    Raises:
        FileNotFoundError: If template doesn't exist
    """
    template_path = PROMPTS_DIR / f"{agent}_{method}.md"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    return template_path.read_text()


def format_prompt(
    template: str,
    *,
    validate_injection: bool = True,
    max_length: int = DEFAULT_MAX_LENGTH,
    add_boundaries: bool = True,
    **kwargs: Any,
) -> str:
    """Format a prompt template with variables and injection protection.

    Uses {{variable}} syntax for substitution. Provides protection against
    prompt injection attacks through pattern detection and boundary markers.

    Args:
        template: The template string
        validate_injection: If True, check for injection patterns (default: True)
        max_length: Maximum length for any single value (default: 50000)
        add_boundaries: If True, wrap suspicious content with markers (default: True)
        **kwargs: Variables to substitute

    Returns:
        Formatted prompt string
    """
    result = template

    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"

        # Convert value to string
        if isinstance(value, dict):
            value_str = json.dumps(value, indent=2)
        elif isinstance(value, list):
            if all(isinstance(item, str) for item in value):
                value_str = "\n".join(f"- {item}" for item in value)
            else:
                value_str = json.dumps(value, indent=2)
        else:
            value_str = str(value)

        # Truncate if too long
        if len(value_str) > max_length:
            value_str = value_str[:max_length] + "\n[CONTENT TRUNCATED]"
            logger.warning(
                f"Prompt variable '{key}' truncated from {len(str(value))} to {max_length} chars"
            )

        # Check for injection patterns
        if validate_injection:
            suspicious = detect_prompt_injection(value_str)
            if suspicious:
                logger.warning(f"Potential prompt injection in '{key}': {suspicious[:3]}")
                # Wrap with boundary markers to isolate user content
                if add_boundaries:
                    value_str = f"[USER_CONTENT_START]\n{value_str}\n[USER_CONTENT_END]"

        result = result.replace(placeholder, value_str)

    return result


def get_available_prompts(agent: Optional[str] = None) -> list[str]:
    """List available prompt templates.

    Args:
        agent: Optional filter by agent name

    Returns:
        List of available prompt names (agent_method format)
    """
    pattern = f"{agent}_*.md" if agent else "*.md"
    return [p.stem for p in PROMPTS_DIR.glob(pattern)]
