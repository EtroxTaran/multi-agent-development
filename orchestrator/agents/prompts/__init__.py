"""Prompt templates for CLI agent wrappers.

This module provides optimized prompts for each agent method with:
- Clear role/identity
- Structured input/output specifications
- Error handling guidance
- Few-shot examples
- Anti-patterns to avoid

Usage:
    from orchestrator.agents.prompts import load_prompt, format_prompt

    template = load_prompt("claude", "planning")
    prompt = format_prompt(template, product_spec=spec)
"""

import json
from pathlib import Path
from typing import Any, Optional

PROMPTS_DIR = Path(__file__).parent


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


def format_prompt(template: str, **kwargs: Any) -> str:
    """Format a prompt template with variables.

    Uses {{variable}} syntax for substitution.

    Args:
        template: The template string
        **kwargs: Variables to substitute

    Returns:
        Formatted prompt string
    """
    result = template
    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"
        if isinstance(value, dict):
            value = json.dumps(value, indent=2)
        elif isinstance(value, list):
            if all(isinstance(item, str) for item in value):
                value = "\n".join(f"- {item}" for item in value)
            else:
                value = json.dumps(value, indent=2)
        result = result.replace(placeholder, str(value))
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
