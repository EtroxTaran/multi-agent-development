"""Task Execution Subgraph.

Encapsulates the task breakdown and execution loop:
Breakdown -> Select -> Write Tests -> Implement -> Verify -> Loop
"""

import logging
from typing import Optional, Any

from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from ..state import WorkflowState
from ..nodes import (
    task_breakdown_node,
    select_next_task_node,
    write_tests_node,
    implement_task_node,
    implement_tasks_parallel_node,
    verify_task_node,
    verify_tasks_parallel_node,
    fix_bug_node,
    # Auto-improvement nodes
    evaluate_agent_node,
    analyze_output_node,
    optimize_prompts_node,
)
from ..routers import (
    task_breakdown_router,
    select_task_router,
    write_tests_router,
    implement_task_router,
    implement_tasks_parallel_router,
    verify_task_router,
    verify_tasks_parallel_router,
    fix_bug_router,
    evaluate_agent_router,
    analyze_output_router,
    optimize_prompts_router,
)

logger = logging.getLogger(__name__)


def create_task_subgraph(
    enable_retry_policy: bool = False,
) -> StateGraph:
    """Create the task execution subgraph.

    Handles:
    1. Breaking down plan into tasks
    2. Selecting next task(s)
    3. Writing tests (TDD)
    4. Implementing tasks (sequential or parallel)
    5. Verifying tasks
    6. Fixing bugs
    7. Auto-improving agent prompts based on performance

    Args:
        enable_retry_policy: Enable retry policies for implementation nodes

    Returns:
        Compiled StateGraph for task execution
    """
    graph = StateGraph(WorkflowState)

    # Retry policy
    implementation_retry_policy = RetryPolicy(
        max_attempts=2,
        initial_interval=5.0,
        backoff_factor=2.0,
        jitter=True,
    ) if enable_retry_policy else None

    # Add nodes
    graph.add_node("task_breakdown", task_breakdown_node)
    graph.add_node("select_task", select_next_task_node)
    graph.add_node("write_tests", write_tests_node)
    graph.add_node("implement_task", implement_task_node, retry=implementation_retry_policy)
    graph.add_node("implement_tasks_parallel", implement_tasks_parallel_node, retry=implementation_retry_policy)
    graph.add_node("fix_bug", fix_bug_node)
    graph.add_node("verify_task", verify_task_node)
    graph.add_node("verify_tasks_parallel", verify_tasks_parallel_node)
    
    # Auto-improvement nodes
    graph.add_node("evaluate_agent", evaluate_agent_node)
    graph.add_node("analyze_output", analyze_output_node)
    graph.add_node("optimize_prompts", optimize_prompts_node)

    # Define edges
    
    # Start -> Task Breakdown
    graph.add_edge(START, "task_breakdown")

    # Task Breakdown -> Select Task or Escalate
    graph.add_conditional_edges(
        "task_breakdown",
        task_breakdown_router,
        {
            "select_task": "select_task",
            "human_escalation": END, # Exit to parent
            "__end__": END,
        },
    )

    # Select Task -> Implement/Write Tests or Done (Build Verification)
    graph.add_conditional_edges(
        "select_task",
        select_task_router,
        {
            "implement_task": "write_tests", # Go to write_tests first
            "implement_tasks_parallel": "implement_tasks_parallel",
            "build_verification": END,  # Exit to parent (success)
            "human_escalation": END,    # Exit to parent
        },
    )

    # Write Tests -> Implement Task
    graph.add_conditional_edges(
        "write_tests",
        write_tests_router,
        {
            "implement_task": "implement_task",
            "human_escalation": END,
        },
    )

    # Implement Task -> Verify Task
    graph.add_conditional_edges(
        "implement_task",
        implement_task_router,
        {
            "verify_task": "verify_task",
            "implement_task": "implement_task",  # Retry
            "human_escalation": END,
        },
    )

    # Verify Task -> Evaluate Agent (Success) or Fix Bug (Failure)
    graph.add_conditional_edges(
        "verify_task",
        verify_task_router,
        {
            "select_task": "evaluate_agent",  # Evaluate before loop back
            "implement_task": "fix_bug",      # Retry via Bug Fixer
            "human_escalation": END,
        },
    )

    # Fix Bug -> Verify Task
    graph.add_conditional_edges(
        "fix_bug",
        fix_bug_router,
        {
            "verify_task": "verify_task",
            "human_escalation": END,
        },
    )

    # Parallel Implementation -> Parallel Verification
    graph.add_conditional_edges(
        "implement_tasks_parallel",
        implement_tasks_parallel_router,
        {
            "verify_tasks_parallel": "verify_tasks_parallel",
            "implement_tasks_parallel": "implement_tasks_parallel", # Retry
            "human_escalation": END,
        },
    )

    # Parallel Verification -> Select Task (Loop)
    graph.add_conditional_edges(
        "verify_tasks_parallel",
        verify_tasks_parallel_router,
        {
            "select_task": "select_task",  # Loop back
            "implement_tasks_parallel": "implement_tasks_parallel", # Retry batch
            "human_escalation": END,
        },
    )

    # Evaluate Agent -> Analyze Output or Loop Back
    graph.add_conditional_edges(
        "evaluate_agent",
        evaluate_agent_router,
        {
            "analyze_output": "analyze_output",
            "continue_workflow": "select_task", # Loop back
        },
    )

    # Analyze Output -> Optimize Prompts or Loop Back
    graph.add_conditional_edges(
        "analyze_output",
        analyze_output_router,
        {
            "optimize_prompts": "optimize_prompts",
            "continue_workflow": "select_task", # Loop back
        },
    )

    # Optimize Prompts -> Loop Back
    graph.add_edge("optimize_prompts", "select_task")

    return graph.compile()