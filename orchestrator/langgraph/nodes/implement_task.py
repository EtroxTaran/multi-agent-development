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
from .task import (
    # Main nodes
    implement_task_node,
    implement_tasks_parallel_node,
    # Prompts
    build_scoped_prompt,
    build_full_prompt,
    build_task_prompt,
    # Constants
    TASK_TIMEOUT,
    RALPH_TIMEOUT,
    USE_RALPH_LOOP,
    # Output
    parse_task_output,
    validate_implementer_output,
    # Storage
    save_clarification_request,
    save_task_result,
    update_task_trackers,
)

# Also export the internal functions that may be used elsewhere
from .task.modes import (
    should_use_ralph_loop as _should_use_ralph_loop,
    should_use_unified_loop as _should_use_unified_loop,
    implement_with_ralph_loop as _implement_with_ralph_loop,
    implement_with_unified_loop as _implement_with_unified_loop,
    implement_standard as _implement_standard,
    FALLBACK_MODEL,
)

from .task.context import (
    load_context_preferences as _load_context_preferences,
    load_research_findings as _load_research_findings,
    build_completed_context as _build_completed_context,
    build_diff_context as _build_diff_context,
    load_task_clarification_answers as _load_task_clarification_answers,
)

from .task.output import (
    get_task_output_schema as _get_task_output_schema,
)

from .task.storage import (
    handle_task_error as _handle_task_error,
)

from .task.prompts import (
    format_criteria as _format_criteria,
    format_files as _format_files,
    SCOPED_TASK_PROMPT,
)

from .task.nodes import (
    ESTIMATED_TASK_COST_USD,
    FALLBACK_COST_RATIO,
    ESTIMATED_FALLBACK_COST_USD,
)

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
