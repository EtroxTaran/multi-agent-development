"""Backward compatibility redirect for implement_task module.

This module has been refactored into the task/ package for better
maintainability. All imports from this module will continue to work.

New imports should use:
    from orchestrator.langgraph.nodes.task import (
        implement_task_node,
        implement_tasks_parallel_node,
        build_task_prompt,
        ...
    )
"""

# Re-export everything from the task package for backward compatibility
from .task import (  # Main nodes; Prompts; Constants; Output; Storage
    RALPH_TIMEOUT,
    TASK_TIMEOUT,
    USE_RALPH_LOOP,
    build_full_prompt,
    build_scoped_prompt,
    build_task_prompt,
    implement_task_node,
    implement_tasks_parallel_node,
    parse_task_output,
    save_clarification_request,
    save_task_result,
    update_task_trackers,
    validate_implementer_output,
)

# Also export the internal functions that may be used elsewhere
from .task.modes import FALLBACK_MODEL
from .task.nodes import ESTIMATED_FALLBACK_COST_USD, ESTIMATED_TASK_COST_USD, FALLBACK_COST_RATIO
from .task.prompts import SCOPED_TASK_PROMPT

__all__ = [
    # Main nodes
    "implement_task_node",
    "implement_tasks_parallel_node",
    # Prompts
    "build_scoped_prompt",
    "build_full_prompt",
    "build_task_prompt",
    "SCOPED_TASK_PROMPT",
    # Constants
    "TASK_TIMEOUT",
    "RALPH_TIMEOUT",
    "USE_RALPH_LOOP",
    "FALLBACK_MODEL",
    "ESTIMATED_TASK_COST_USD",
    "FALLBACK_COST_RATIO",
    "ESTIMATED_FALLBACK_COST_USD",
    # Output
    "parse_task_output",
    "validate_implementer_output",
    # Storage
    "save_clarification_request",
    "save_task_result",
    "update_task_trackers",
]
