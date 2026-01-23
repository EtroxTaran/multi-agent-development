"""Router for evaluation and optimization nodes.

Routes evaluation results to analysis or back to workflow,
and routes analysis to optimization when needed.
"""

import logging
from typing import Literal

from ..state import WorkflowState

logger = logging.getLogger(__name__)


def evaluate_agent_router(
    state: WorkflowState,
) -> Literal["analyze_output", "continue_workflow"]:
    """Route based on evaluation results.

    Routes to analyze_output if score is low enough to warrant
    deeper analysis. Otherwise continues the main workflow.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    last_eval = state.get("last_evaluation")

    if not last_eval:
        return "continue_workflow"

    # Get overall score from evaluation
    overall_score = last_eval.get("overall_score", 10.0)

    # If score is below analysis threshold, perform deeper analysis
    # Analysis threshold is lower than optimization threshold (7.0)
    # to only analyze truly problematic outputs
    if overall_score < 6.0:
        logger.info(
            f"Evaluation score {overall_score:.2f} below analysis threshold, "
            "routing to analyze_output"
        )
        return "analyze_output"

    return "continue_workflow"


def analyze_output_router(
    state: WorkflowState,
) -> Literal["optimize_prompts", "continue_workflow"]:
    """Route based on analysis results.

    Routes to optimization if there are items in the optimization queue.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    optimization_queue = state.get("optimization_queue", [])

    if optimization_queue:
        logger.info(
            f"Optimization queue has {len(optimization_queue)} items, "
            "routing to optimize_prompts"
        )
        return "optimize_prompts"

    return "continue_workflow"


def optimize_prompts_router(
    state: WorkflowState,
) -> Literal["continue_workflow"]:
    """Route after optimization.

    Always returns to continue_workflow after optimization
    since optimization runs asynchronously.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    optimization_results = state.get("optimization_results", [])

    if optimization_results:
        successes = sum(1 for r in optimization_results if r.get("success"))
        logger.info(
            f"Optimization completed: {successes}/{len(optimization_results)} succeeded"
        )

    return "continue_workflow"


def should_evaluate_router(
    state: WorkflowState,
) -> Literal["evaluate_agent", "skip_evaluation"]:
    """Determine if evaluation should run.

    Checks if:
    - Auto-improvement is enabled
    - There's an agent execution to evaluate
    - Sampling rate allows evaluation

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    # Check if auto-improvement is enabled
    config = state.get("auto_improvement_config", {})
    if not config.get("evaluation", {}).get("enabled", True):
        return "skip_evaluation"

    # Check if there's an execution to evaluate
    last_execution = state.get("last_agent_execution")
    if not last_execution:
        return "skip_evaluation"

    # Check sampling rate
    import random
    sampling_rate = config.get("evaluation", {}).get("sampling_rate", 1.0)
    if sampling_rate < 1.0 and random.random() > sampling_rate:
        logger.debug("Skipping evaluation due to sampling")
        return "skip_evaluation"

    return "evaluate_agent"
