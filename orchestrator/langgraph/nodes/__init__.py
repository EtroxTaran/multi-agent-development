"""LangGraph workflow nodes.

Each node represents a step in the workflow graph. Nodes receive
the current state and return updates to the state.
"""

from .prerequisites import prerequisites_node
from .planning import planning_node
from .validation import cursor_validate_node, gemini_validate_node, validation_fan_in_node
from .implementation import implementation_node
from .verification import cursor_review_node, gemini_review_node, verification_fan_in_node, review_gate_node
from .completion import completion_node
from .escalation import human_escalation_node

# Risk mitigation nodes
from .product_validation import product_validation_node
from .pre_implementation import pre_implementation_node
from .build_verification import build_verification_node
from .coverage_check import coverage_check_node
from .security_scan import security_scan_node
from .approval_gate import approval_gate_node

# Task loop nodes (incremental execution)
from .task_breakdown import task_breakdown_node
from .select_task import select_next_task_node
from .implement_task import implement_task_node, implement_tasks_parallel_node
from .verify_task import verify_task_node, verify_tasks_parallel_node
from .write_tests import write_tests_node
from .fix_bug import fix_bug_node

# Discussion and Research nodes (GSD pattern)
from .discuss_phase import discuss_phase_node
from .research_phase import research_phase_node

# Handoff node (GSD pattern)
from .generate_handoff import generate_handoff_node

# Fixer nodes (self-healing)
from .fixer_triage import fixer_triage_node
from .fixer_diagnose import fixer_diagnose_node
from .fixer_validate import fixer_validate_node
from .fixer_apply import fixer_apply_node
from .fixer_verify import fixer_verify_node
from .error_dispatch import error_dispatch_node

__all__ = [
    "prerequisites_node",
    "planning_node",
    "cursor_validate_node",
    "gemini_validate_node",
    "validation_fan_in_node",
    "implementation_node",
    "cursor_review_node",
    "gemini_review_node",
    "review_gate_node",
    "verification_fan_in_node",
    "completion_node",
    "human_escalation_node",
    # Risk mitigation nodes
    "product_validation_node",
    "pre_implementation_node",
    "build_verification_node",
    "coverage_check_node",
    "security_scan_node",
    "approval_gate_node",
    # Task loop nodes
    "task_breakdown_node",
    "select_next_task_node",
    "implement_task_node",
    "implement_tasks_parallel_node",
    "verify_task_node",
    "verify_tasks_parallel_node",
    "write_tests_node",
    "fix_bug_node",
    # Discussion and Research nodes (GSD pattern)
    "discuss_phase_node",
    "research_phase_node",
    # Handoff node (GSD pattern)
    "generate_handoff_node",
    # Fixer nodes (self-healing)
    "fixer_triage_node",
    "fixer_diagnose_node",
    "fixer_validate_node",
    "fixer_apply_node",
    "fixer_verify_node",
    # Error dispatch node
    "error_dispatch_node",
]
