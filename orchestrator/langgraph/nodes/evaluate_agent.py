"""Post-agent evaluation node for auto-improvement.

Evaluates agent outputs after execution and triggers
optimization when scores are low.
"""

import logging
from datetime import datetime
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def evaluate_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Evaluate the most recent agent execution.

    This node runs after any agent node to assess output quality
    using G-Eval. Results are stored in the database and used
    to trigger optimization when needed.

    Args:
        state: Current workflow state

    Returns:
        State updates with evaluation results
    """
    from ...evaluation import AgentEvaluator, EvaluationResult
    from ...db.repositories import (
        get_evaluation_repository,
        get_golden_example_repository,
    )

    # Check for last agent execution
    last_execution = state.get("last_agent_execution")
    if not last_execution:
        logger.debug("No agent execution to evaluate")
        return {}

    project_name = state.get("project_name", "unknown")
    project_dir = state.get("project_dir", ".")

    # Initialize evaluator
    evaluator = AgentEvaluator(
        project_dir=project_dir,
        evaluator_model="haiku",  # Fast/cheap for high volume
        enable_storage=True,
    )

    try:
        # Run evaluation
        evaluation = await evaluator.evaluate(
            agent=last_execution.get("agent", "unknown"),
            node=last_execution.get("node", "unknown"),
            prompt=last_execution.get("prompt", ""),
            output=last_execution.get("output", ""),
            task_id=state.get("current_task_id"),
            session_id=last_execution.get("session_id"),
            requirements=_get_requirements(state),
            prompt_version=last_execution.get("prompt_version"),
            metadata={
                "phase": state.get("current_phase"),
                "iteration": state.get("iteration_count", 0),
            },
        )

        # Build state updates
        updates: dict[str, Any] = {
            "last_evaluation": evaluation.to_dict(),
        }

        # Check if needs optimization
        if evaluation.needs_optimization():
            template_name = last_execution.get("template_name", "default")
            agent = last_execution.get("agent", "unknown")

            updates["optimization_queue"] = [
                {
                    "agent": agent,
                    "template_name": template_name,
                    "reason": f"Score {evaluation.overall_score:.2f} below threshold",
                    "triggered_at": datetime.now().isoformat(),
                }
            ]
            logger.info(
                f"Queued optimization for {agent}/{template_name} "
                f"(score: {evaluation.overall_score:.2f})"
            )

            # Also notify the scheduler for background processing
            try:
                from ...optimization.scheduler import OptimizationScheduler

                scheduler = OptimizationScheduler(
                    project_dir=project_dir,
                    project_name=project_name,
                )
                scheduler.queue_optimization(
                    agent=agent,
                    template_name=template_name,
                    reason=f"Score {evaluation.overall_score:.2f} below threshold",
                    priority=int(10 - evaluation.overall_score),  # Lower score = higher priority
                )
                logger.debug(f"Notified scheduler of optimization need")
            except Exception as se:
                logger.debug(f"Scheduler notification failed (non-fatal): {se}")

        # Check if golden example
        if evaluation.is_golden_example():
            await _save_golden_example(
                project_name=project_name,
                last_execution=last_execution,
                evaluation=evaluation,
            )
            logger.info(
                f"Saved golden example for {last_execution.get('agent')} "
                f"(score: {evaluation.overall_score:.2f})"
            )

        return updates

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {
            "errors": [{
                "type": "evaluation_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }]
        }


def _get_requirements(state: WorkflowState) -> list[str]:
    """Extract requirements from state for evaluation context.

    Args:
        state: Workflow state

    Returns:
        List of requirements/acceptance criteria
    """
    requirements = []

    # Get current task's acceptance criteria
    current_task_id = state.get("current_task_id")
    if current_task_id:
        for task in state.get("tasks", []):
            if task.get("id") == current_task_id:
                requirements.extend(task.get("acceptance_criteria", []))
                break

    # Add plan requirements if available
    plan = state.get("plan")
    if plan:
        key_features = plan.get("key_features", [])
        if isinstance(key_features, list):
            requirements.extend(key_features[:5])

    return requirements


async def _save_golden_example(
    project_name: str,
    last_execution: dict,
    evaluation,
) -> None:
    """Save a high-scoring output as a golden example.

    Args:
        project_name: Project name
        last_execution: Execution details
        evaluation: Evaluation result
    """
    from ...db.repositories import get_golden_example_repository

    golden_repo = get_golden_example_repository(project_name)

    await golden_repo.save_example(
        agent=last_execution.get("agent", "unknown"),
        template_name=last_execution.get("template_name", "default"),
        input_prompt=last_execution.get("prompt", ""),
        output=last_execution.get("output", ""),
        score=evaluation.overall_score,
        evaluation_id=evaluation.evaluation_id,
        metadata={
            "node": last_execution.get("node"),
            "task_id": last_execution.get("task_id"),
        },
    )


async def analyze_output_node(state: WorkflowState) -> dict[str, Any]:
    """Deep analysis of agent output for improvement insights.

    This is an optional node that performs more detailed analysis
    beyond G-Eval scoring, including pattern detection and
    structural analysis.

    Args:
        state: Current workflow state

    Returns:
        State updates with analysis results
    """
    from ...evaluation import OutputAnalyzer

    last_execution = state.get("last_agent_execution")
    if not last_execution:
        return {}

    analyzer = OutputAnalyzer()

    try:
        analysis = analyzer.analyze(
            output=last_execution.get("output", ""),
            requirements=_get_requirements(state),
            expected_format=last_execution.get("expected_format"),
        )

        # Store analysis for debugging
        return {
            "last_analysis": analysis.to_dict(),
        }

    except Exception as e:
        logger.error(f"Output analysis failed: {e}")
        return {}


async def optimize_prompts_node(state: WorkflowState) -> dict[str, Any]:
    """Process optimization queue and run optimizations.

    After successful optimization, triggers the deployment pipeline
    to start shadow testing of the new prompt version.

    Args:
        state: Current workflow state

    Returns:
        State updates with optimization and deployment results
    """
    from ...optimization import PromptOptimizer
    from ...optimization.deployer import DeploymentController

    optimization_queue = state.get("optimization_queue", [])
    if not optimization_queue:
        return {}

    project_dir = state.get("project_dir", ".")
    project_name = state.get("project_name", "unknown")

    optimizer = PromptOptimizer(
        project_dir=project_dir,
        project_name=project_name,
    )

    deployer = DeploymentController(project_name=project_name)

    optimization_results = []
    deployment_results = []

    for item in optimization_queue[:3]:  # Limit to 3 per run
        try:
            result = await optimizer.optimize(
                agent=item.get("agent"),
                template_name=item.get("template_name"),
            )

            opt_result = {
                "agent": item.get("agent"),
                "template": item.get("template_name"),
                "success": result.success,
                "method": result.method,
                "improvement": result.expected_improvement,
                "version_id": result.source_version,
                "error": result.error,
            }
            optimization_results.append(opt_result)

            if result.success:
                logger.info(
                    f"Optimization succeeded for {item.get('agent')}/{item.get('template_name')}"
                )

                # Start deployment pipeline for new version
                if result.source_version:
                    try:
                        deploy_result = await deployer.start_shadow_testing(
                            result.source_version
                        )
                        deployment_results.append(deploy_result.to_dict())
                        logger.info(
                            f"Started shadow testing for {result.source_version}: "
                            f"{deploy_result.to_status}"
                        )
                    except Exception as de:
                        logger.warning(f"Deployment start failed: {de}")
                        deployment_results.append({
                            "success": False,
                            "version_id": result.source_version,
                            "error": str(de),
                        })

        except Exception as e:
            logger.error(f"Optimization failed for {item.get('agent')}: {e}")
            optimization_results.append({
                "agent": item.get("agent"),
                "template": item.get("template_name"),
                "success": False,
                "error": str(e),
            })

    return {
        "optimization_queue": [],  # Clear processed items
        "optimization_results": optimization_results,
        "deployment_results": deployment_results,
    }
