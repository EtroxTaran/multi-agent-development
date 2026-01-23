"""Fixer Subgraph.

Encapsulates the self-healing fixer loop:
Triage -> Diagnose -> Validate -> Apply -> Verify
"""

import logging
from typing import Optional, Any

from langgraph.graph import StateGraph, START, END

from ..state import WorkflowState
from ..nodes import (
    fixer_triage_node,
    fixer_diagnose_node,
    fixer_validate_node,
    fixer_apply_node,
    fixer_verify_node,
    fixer_research_node,
)
from ..routers import (
    fixer_triage_router,
    fixer_diagnose_router,
    fixer_validate_router,
    fixer_apply_router,
    fixer_verify_router,
    fixer_research_router,
)

logger = logging.getLogger(__name__)


def create_fixer_subgraph() -> StateGraph:
    """Create the fixer subgraph.

    This subgraph handles error recovery:
    1. Triage: Analyze the error and decide on strategy
    2. Diagnose: Determine root cause and create fix plan
    3. Validate: Optional validation of the fix plan (e.g. security check)
    4. Apply: Apply the fix (edit code, run command)
    5. Verify: Verify the fix resolved the error

    Returns:
        Compiled StateGraph for the fixer
    """
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("fixer_triage", fixer_triage_node)
    graph.add_node("fixer_diagnose", fixer_diagnose_node)
    graph.add_node("fixer_validate", fixer_validate_node)
    graph.add_node("fixer_apply", fixer_apply_node)
    graph.add_node("fixer_verify", fixer_verify_node)
    graph.add_node("fixer_research", fixer_research_node)

    # Define edges
    
    # Start -> Triage
    graph.add_edge(START, "fixer_triage")

    # Triage -> Diagnose or Escalate
    # Note: "human_escalation" routes out of the subgraph
    graph.add_conditional_edges(
        "fixer_triage",
        fixer_triage_router,
        {
            "fixer_diagnose": "fixer_diagnose",
            "human_escalation": END, # Exit to parent graph
            "skip_fixer": END,       # Exit to parent graph
        },
    )

    # Diagnose -> Validate, Apply, Research, or Escalate
    graph.add_conditional_edges(
        "fixer_diagnose",
        fixer_diagnose_router,
        {
            "fixer_validate": "fixer_validate",
            "fixer_apply": "fixer_apply",
            "fixer_research": "fixer_research",
            "human_escalation": END,
        },
    )

    # Research -> Validate or Escalate
    graph.add_conditional_edges(
        "fixer_research",
        fixer_research_router,
        {
            "fixer_validate": "fixer_validate",
            "human_escalation": END,
        },
    )

    # Validate -> Apply or Escalate
    graph.add_conditional_edges(
        "fixer_validate",
        fixer_validate_router,
        {
            "fixer_apply": "fixer_apply",
            "human_escalation": END,
        },
    )

    # Apply -> Verify or Escalate
    graph.add_conditional_edges(
        "fixer_apply",
        fixer_apply_router,
        {
            "fixer_verify": "fixer_verify",
            "human_escalation": END,
        },
    )

    # Verify -> Resume or Escalate
    # "resume_workflow" is the success case exiting the subgraph
    graph.add_conditional_edges(
        "fixer_verify",
        fixer_verify_router,
        {
            "resume_workflow": END, # Exit to parent graph (mapped to evaluate_agent)
            "human_escalation": END,
        },
    )

    return graph.compile()