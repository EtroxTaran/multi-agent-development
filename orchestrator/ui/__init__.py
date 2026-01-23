"""UI module for workflow monitoring and progress display."""

import os
import sys
from typing import Optional

from orchestrator.ui.callbacks import NullCallback, ProgressCallback, UICallbackHandler
from orchestrator.ui.display import PlaintextDisplay, UIState, WorkflowDisplay
from orchestrator.ui.input_manager import UserInputManager
from orchestrator.ui.interrupt_display import InterruptDisplay
from orchestrator.ui.prompt_helpers import (
    display_error,
    display_info_box,
    display_success,
    display_warning,
    prompt_confirm,
    prompt_menu,
    prompt_multiline,
    prompt_text_block,
)
from orchestrator.ui.state_adapter import EventLogEntry, TaskUIInfo, UIStateSnapshot


def is_interactive() -> bool:
    """
    Check if the current environment supports interactive display.

    Returns:
        True if interactive mode is supported, False otherwise
    """
    # Check CI environment variables
    ci_vars = [
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CIRCLECI",
        "JENKINS_URL",
        "BUILDKITE",
        "TRAVIS",
        "TF_BUILD",
    ]
    for var in ci_vars:
        if os.environ.get(var):
            return False

    # Check explicit flags
    if os.environ.get("ORCHESTRATOR_PLAIN_OUTPUT"):
        return False

    if os.environ.get("NO_COLOR"):
        return False

    # Check if stdout is a TTY
    if not sys.stdout.isatty():
        return False

    return True


def create_display(
    project_name: str,
    interactive: Optional[bool] = None,
) -> "PlaintextDisplay | WorkflowDisplay":
    """
    Create appropriate display based on environment.

    Args:
        project_name: Name of the project
        interactive: Force interactive mode (auto-detect if None)

    Returns:
        Display instance
    """
    if interactive is None:
        interactive = is_interactive()

    if interactive:
        return WorkflowDisplay(project_name)
    else:
        return PlaintextDisplay(project_name)


__all__ = [
    # Display creation
    "create_display",
    "is_interactive",
    # Display classes
    "PlaintextDisplay",
    "WorkflowDisplay",
    "UIState",
    # Callbacks
    "UICallbackHandler",
    "ProgressCallback",
    "NullCallback",
    # State adapters
    "TaskUIInfo",
    "EventLogEntry",
    "UIStateSnapshot",
    # HITL input handling
    "UserInputManager",
    "InterruptDisplay",
    # Prompt helpers
    "prompt_menu",
    "prompt_multiline",
    "prompt_confirm",
    "prompt_text_block",
    "display_info_box",
    "display_warning",
    "display_error",
    "display_success",
]
