"""Post-agent evaluation node for auto-improvement.

Evaluates agent outputs after execution and triggers
optimization when scores are low.

Now supports ALL 9 template types with template-specific evaluation criteria:
- planning: Task breakdown, completeness, clarity
- validation: Score accuracy, issue detection, recommendations
- code_review: Security findings, code quality, coverage
- architecture_review: Scalability, patterns, integration
- task_implementation: TDD adherence, acceptance criteria
- test_writing: Test coverage, edge cases, assertions
- bug_fix: Root cause analysis, fix completeness
- fixer_diagnose: Error analysis, suggested actions
- fixer_apply: Fix effectiveness, safety checks
"""

import logging
from datetime import datetime
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


# Template-specific evaluation criteria weights
# Each template has different priorities for what makes a good output
TEMPLATE_CRITERIA = {
    "planning": {
        "completeness": 0.25,
        "task_clarity": 0.25,
        "granularity": 0.20,
        "dependency_handling": 0.15,
        "format_adherence": 0.15,
    },
    "validation": {
        "score_accuracy": 0.20,
        "issue_detection": 0.25,
        "constructive_feedback": 0.20,
        "format_adherence": 0.15,
        "actionable_recommendations": 0.20,
    },
    "code_review": {
        "security_findings": 0.30,
        "code_quality": 0.25,
        "completeness": 0.20,
        "actionable_feedback": 0.15,
        "format_adherence": 0.10,
    },
    "architecture_review": {
        "scalability_assessment": 0.25,
        "pattern_identification": 0.20,
        "integration_analysis": 0.20,
        "alternative_approaches": 0.20,
        "format_adherence": 0.15,
    },
    "task_implementation": {
        "tdd_adherence": 0.25,
        "acceptance_criteria_coverage": 0.30,
        "code_quality": 0.20,
        "documentation": 0.10,
        "completion_signal": 0.15,
    },
    "test_writing": {
        "coverage": 0.30,
        "edge_cases": 0.25,
        "assertion_quality": 0.20,
        "test_isolation": 0.15,
        "readability": 0.10,
    },
    "bug_fix": {
        "root_cause_identification": 0.30,
        "fix_completeness": 0.25,
        "regression_prevention": 0.20,
        "test_coverage": 0.15,
        "documentation": 0.10,
    },
    "fixer_diagnose": {
        "error_analysis": 0.30,
        "root_cause_identification": 0.25,
        "suggested_actions": 0.25,
        "context_utilization": 0.10,
        "format_adherence": 0.10,
    },
    "fixer_apply": {
        "fix_effectiveness": 0.35,
        "safety_checks": 0.25,
        "minimal_changes": 0.15,
        "test_verification": 0.15,
        "documentation": 0.10,
    },
    # Default criteria for unknown templates
    "default": {
        "relevance": 0.25,
        "completeness": 0.25,
        "format_adherence": 0.25,
        "actionable_output": 0.25,
    },
}


def get_template_criteria(template_name: str) -> dict[str, float]:
    """Get evaluation criteria for a template.

    Args:
        template_name: Name of the prompt template

    Returns:
        Dict of criteria with weights
    """
    return TEMPLATE_CRITERIA.get(template_name, TEMPLATE_CRITERIA["default"])


async def evaluate_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Evaluate the most recent agent execution.

    This node runs after ANY agent node to assess output quality
    using G-Eval with template-specific criteria. Results are stored
    in the database and used to trigger optimization when needed.

    Handles all 9 template types:
    - planning: Claude generating implementation plan
    - validation: Cursor/Gemini validating plan
    - code_review: Cursor reviewing code quality
    - architecture_review: Gemini reviewing architecture
    - task_implementation: Claude implementing tasks
    - test_writing: Claude writing tests
    - bug_fix: Claude fixing bugs
    - fixer_diagnose: Claude analyzing errors
    - fixer_apply: Claude applying fixes

    Args:
        state: Current workflow state

    Returns:
        State updates with evaluation results
    """
    from ...evaluation import AgentEvaluator

    # Check for last agent execution
    last_execution = state.get("last_agent_execution")
    if not last_execution:
        logger.debug("No agent execution to evaluate")
        return {}

    # Skip evaluation for failed executions
    if not last_execution.get("success", True):
        logger.debug("Skipping evaluation for failed execution")
        return {}

    project_name = state.get("project_name", "unknown")
    project_dir = state.get("project_dir", ".")

    # Get template-specific criteria
    template_name = last_execution.get("template_name", "default")
    criteria = get_template_criteria(template_name)

    # Initialize evaluator (criteria passed via metadata in evaluate() call)
    evaluator = AgentEvaluator(
        project_dir=project_dir,
        evaluator_model="haiku",  # Fast/cheap for high volume
        enable_storage=True,
    )

    try:
        # Get template-specific requirements
        requirements = _get_template_requirements(state, template_name)

        # Run evaluation
        evaluation = await evaluator.evaluate(
            agent=last_execution.get("agent", "unknown"),
            node=last_execution.get("node", "unknown"),
            prompt=last_execution.get("prompt", ""),
            output=last_execution.get("output", ""),
            task_id=state.get("current_task_id"),
            session_id=last_execution.get("session_id"),
            requirements=requirements,
            prompt_version=last_execution.get("prompt_version"),
            metadata={
                "phase": state.get("current_phase"),
                "iteration": state.get("iteration_count", 0),
                "template_name": template_name,
                "criteria": criteria,
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
                logger.debug("Notified scheduler of optimization need")
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
            "errors": [
                {
                    "type": "evaluation_error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ]
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


def _get_template_requirements(state: WorkflowState, template_name: str) -> list[str]:
    """Get template-specific requirements for evaluation.

    Different templates have different expectations:
    - planning: Should produce structured tasks with clear dependencies
    - validation: Should provide score and actionable feedback
    - code_review: Should identify security issues and code quality concerns
    - architecture_review: Should assess patterns and scalability
    - task_implementation: Should meet acceptance criteria and follow TDD
    - test_writing: Should cover edge cases and use proper assertions
    - bug_fix: Should identify root cause and prevent regressions
    - fixer_diagnose: Should analyze error context thoroughly
    - fixer_apply: Should apply minimal, safe fixes

    Args:
        state: Workflow state
        template_name: Name of the prompt template

    Returns:
        List of requirements for this template type
    """
    # Start with generic requirements
    requirements = _get_requirements(state)

    # Add template-specific requirements
    template_requirements = {
        "planning": [
            "Output must be valid JSON with 'tasks' array",
            "Each task must have id, title, and acceptance_criteria",
            "Tasks should be small and focused (max 5 files per task)",
            "Dependencies between tasks must be explicitly specified",
            "Task ordering should respect dependencies",
        ],
        "validation": [
            "Output must include 'score' (1-10) and 'overall_assessment'",
            "Must list specific concerns with severity levels",
            "Recommendations should be actionable and specific",
            "Security and maintainability must be evaluated",
        ],
        "code_review": [
            "Must check for OWASP Top 10 security vulnerabilities",
            "Code quality issues must include file and line references",
            "Severity levels must be HIGH, MEDIUM, or LOW",
            "Output must include 'approved' boolean and 'score'",
        ],
        "architecture_review": [
            "Must assess scalability and maintainability",
            "Design patterns should be identified",
            "Integration considerations must be listed",
            "Alternative approaches should be suggested when relevant",
        ],
        "task_implementation": [
            "Must follow TDD (write/update tests first)",
            "All acceptance criteria must be addressed",
            "Code must be minimal and focused on the task",
            "Must signal completion with completion marker",
        ],
        "test_writing": [
            "Tests must cover happy path and error cases",
            "Edge cases must be considered",
            "Tests should be isolated and independent",
            "Assertions should be clear and specific",
        ],
        "bug_fix": [
            "Root cause must be identified clearly",
            "Fix must be minimal and targeted",
            "Regression tests should be added or updated",
            "Fix should not introduce new issues",
        ],
        "fixer_diagnose": [
            "Must analyze full error context including stack trace",
            "Root cause hypothesis should be stated",
            "Multiple fix strategies should be suggested",
            "Recoverability assessment must be provided",
        ],
        "fixer_apply": [
            "Fix must address the diagnosed issue",
            "Changes should be minimal and safe",
            "Fix must be verified with tests when possible",
            "Documentation should explain the fix",
        ],
    }

    # Add template-specific requirements
    if template_name in template_requirements:
        requirements.extend(template_requirements[template_name])

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
                        deploy_result = await deployer.start_shadow_testing(result.source_version)
                        deployment_results.append(deploy_result.to_dict())
                        logger.info(
                            f"Started shadow testing for {result.source_version}: "
                            f"{deploy_result.to_status}"
                        )
                    except Exception as de:
                        logger.warning(f"Deployment start failed: {de}")
                        deployment_results.append(
                            {
                                "success": False,
                                "version_id": result.source_version,
                                "error": str(de),
                            }
                        )

        except Exception as e:
            logger.error(f"Optimization failed for {item.get('agent')}: {e}")
            optimization_results.append(
                {
                    "agent": item.get("agent"),
                    "template": item.get("template_name"),
                    "success": False,
                    "error": str(e),
                }
            )

    return {
        "optimization_queue": [],  # Clear processed items
        "optimization_results": optimization_results,
        "deployment_results": deployment_results,
    }
