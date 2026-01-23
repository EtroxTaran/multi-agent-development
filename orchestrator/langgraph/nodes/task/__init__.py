"""Task implementation package.

Provides modular components for implementing tasks:
- nodes: Main entry points (implement_task_node, implement_tasks_parallel_node)
- modes: Execution strategies (Ralph loop, unified loop, standard)
- prompts: Prompt building and formatting
- context: Context loading (preferences, research findings)
- output: Output parsing and validation
- storage: Data persistence

Usage:
    from orchestrator.langgraph.nodes.task import (
        implement_task_node,
        implement_tasks_parallel_node,
        build_task_prompt,
        build_scoped_prompt,
    )
"""

# Re-export main node functions
from .nodes import (
    implement_task_node,
    implement_tasks_parallel_node,
)

# Re-export prompt building functions
from .prompts import (
    build_scoped_prompt,
    build_full_prompt,
    build_task_prompt,
)

# Re-export commonly used utilities
from .modes import (
    TASK_TIMEOUT,
    RALPH_TIMEOUT,
    USE_RALPH_LOOP,
)

from .output import (
    parse_task_output,
    validate_implementer_output,
)

from .storage import (
    save_clarification_request,
    save_task_result,
    update_task_trackers,
)

__all__ = [
    # Main nodes
    "implement_task_node",
    "implement_tasks_parallel_node",
    # Prompts
    "build_scoped_prompt",
    "build_full_prompt",
    "build_task_prompt",
    # Constants
    "TASK_TIMEOUT",
    "RALPH_TIMEOUT",
    "USE_RALPH_LOOP",
    # Output
    "parse_task_output",
    "validate_implementer_output",
    # Storage
    "save_clarification_request",
    "save_task_result",
    "update_task_trackers",
]
