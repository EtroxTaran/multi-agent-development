"""LangGraph workflow routers.

Routers determine the next node based on state conditions.
Used for conditional edges in the workflow graph.
"""

from .validation import validation_router
from .verification import verification_router
from .general import (
    prerequisites_router,
    planning_router,
    implementation_router,
    completion_router,
    human_escalation_router,
    # Risk mitigation routers
    product_validation_router,
    pre_implementation_router,
    build_verification_router,
    coverage_check_router,
    security_scan_router,
    approval_gate_router,
    # Discussion and Research routers (GSD pattern)
    discuss_router,
    research_router,
)
from .task import (
    task_breakdown_router,
    select_task_router,
    implement_task_router,
    implement_tasks_parallel_router,
    verify_task_router,
    verify_tasks_parallel_router,
)
from .write_tests import write_tests_router
from .fix_bug import fix_bug_router
from .fixer import (
    fixer_triage_router,
    fixer_diagnose_router,
    fixer_validate_router,
    fixer_apply_router,
    fixer_verify_router,
    should_use_fixer_router,
)
from ..nodes.error_dispatch import error_dispatch_router
from .evaluation import (
    evaluate_agent_router,
    analyze_output_router,
    optimize_prompts_router,
    should_evaluate_router,
)

__all__ = [
    "validation_router",
    "verification_router",
    "prerequisites_router",
    "planning_router",
    "implementation_router",
    "completion_router",
    "human_escalation_router",
    # Risk mitigation routers
    "product_validation_router",
    "pre_implementation_router",
    "build_verification_router",
    "coverage_check_router",
    "security_scan_router",
    "approval_gate_router",
    # Discussion and Research routers (GSD pattern)
    "discuss_router",
    "research_router",
    # Task loop routers
    "task_breakdown_router",
    "select_task_router",
    "implement_task_router",
    "implement_tasks_parallel_router",
    "verify_task_router",
    "verify_tasks_parallel_router",
    "write_tests_router",
    "fix_bug_router",
    # Fixer routers (self-healing)
    "fixer_triage_router",
    "fixer_diagnose_router",
    "fixer_validate_router",
    "fixer_apply_router",
    "fixer_verify_router",
    "should_use_fixer_router",
    # Error dispatch
    "error_dispatch_router",
    # Auto-improvement routers (evaluation and optimization)
    "evaluate_agent_router",
    "analyze_output_router",
    "optimize_prompts_router",
    "should_evaluate_router",
]
