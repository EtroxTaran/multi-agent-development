"""Completion node for Phase 5.

Generates summary and documentation for the completed workflow.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...cleanup import CleanupManager
from ..state import PhaseState, PhaseStatus, WorkflowState

logger = logging.getLogger(__name__)


async def completion_node(state: WorkflowState) -> dict[str, Any]:
    """Generate completion summary and documentation.

    Creates a COMPLETION.md file with:
    - Summary of what was built
    - Files created/modified
    - Test results
    - Review feedback summary
    - Any remaining issues

    Args:
        state: Current workflow state

    Returns:
        State updates with completion status
    """
    logger.info(f"Completing workflow for: {state['project_name']}")

    project_dir = Path(state["project_dir"])

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_5 = phase_status.get("5", PhaseState())
    phase_5.status = PhaseStatus.IN_PROGRESS
    phase_5.started_at = datetime.now().isoformat()
    phase_5.attempts += 1
    phase_status["5"] = phase_5

    # Gather data for summary
    plan = state.get("plan", {})
    impl_result = state.get("implementation_result", {})
    validation_feedback = state.get("validation_feedback", {})
    verification_feedback = state.get("verification_feedback", {})
    errors = state.get("errors", [])
    git_commits = state.get("git_commits", [])

    # Build summary
    summary_lines = [
        "# Workflow Completion Summary",
        "",
        f"**Project:** {state['project_name']}",
        f"**Completed:** {datetime.now().isoformat()}",
        "",
        "## Plan Summary",
        "",
        f"**Name:** {plan.get('plan_name', 'Unknown')}",
        "",
        f"{plan.get('summary', 'No summary available.')}",
        "",
    ]

    # Implementation results
    if impl_result:
        summary_lines.extend(
            [
                "## Implementation Results",
                "",
                f"- **Files Created:** {impl_result.get('total_files_created', 0)}",
                f"- **Files Modified:** {impl_result.get('total_files_modified', 0)}",
                f"- **Tests:** {json.dumps(impl_result.get('test_results', {}))}",
                "",
            ]
        )

    # Validation summary
    if validation_feedback:
        summary_lines.extend(
            [
                "## Validation Summary",
                "",
            ]
        )
        for agent, feedback in validation_feedback.items():
            if hasattr(feedback, "to_dict"):
                fb_dict = feedback.to_dict()
            else:
                fb_dict = feedback if isinstance(feedback, dict) else {"summary": str(feedback)}

            summary_lines.extend(
                [
                    f"### {agent.title()}",
                    f"- **Score:** {fb_dict.get('score', 'N/A')}",
                    f"- **Assessment:** {fb_dict.get('assessment', 'N/A')}",
                    f"- **Summary:** {fb_dict.get('summary', 'N/A')}",
                    "",
                ]
            )

    # Verification summary
    if verification_feedback:
        summary_lines.extend(
            [
                "## Verification Summary",
                "",
            ]
        )
        for agent, feedback in verification_feedback.items():
            if hasattr(feedback, "to_dict"):
                fb_dict = feedback.to_dict()
            else:
                fb_dict = feedback if isinstance(feedback, dict) else {"summary": str(feedback)}

            summary_lines.extend(
                [
                    f"### {agent.title()}",
                    f"- **Approved:** {fb_dict.get('approved', 'N/A')}",
                    f"- **Score:** {fb_dict.get('score', 'N/A')}",
                    f"- **Summary:** {fb_dict.get('summary', 'N/A')}",
                    "",
                ]
            )

    # Git commits
    if git_commits:
        summary_lines.extend(
            [
                "## Git Commits",
                "",
            ]
        )
        for commit in git_commits:
            summary_lines.append(
                f"- `{commit.get('hash', 'unknown')[:8]}` - {commit.get('message', 'No message')}"
            )
        summary_lines.append("")

    # Errors
    if errors:
        summary_lines.extend(
            [
                "## Errors Encountered",
                "",
            ]
        )
        for error in errors:
            summary_lines.append(
                f"- **{error.get('type', 'Unknown')}:** {error.get('message', 'No message')}"
            )
        summary_lines.append("")

    # Phase status summary
    summary_lines.extend(
        [
            "## Phase Status",
            "",
            "| Phase | Status | Attempts |",
            "|-------|--------|----------|",
        ]
    )

    phase_names = {
        "1": "Planning",
        "2": "Validation",
        "3": "Implementation",
        "4": "Verification",
        "5": "Completion",
    }

    for phase_num, phase_name in phase_names.items():
        ps = phase_status.get(phase_num, PhaseState())
        status_emoji = {
            PhaseStatus.COMPLETED: "✅",
            PhaseStatus.FAILED: "❌",
            PhaseStatus.IN_PROGRESS: "🔄",
            PhaseStatus.PENDING: "⏳",
            PhaseStatus.SKIPPED: "⏭️",
        }.get(ps.status, "❓")
        summary_lines.append(f"| {phase_name} | {status_emoji} {ps.status.value} | {ps.attempts} |")

    summary_lines.extend(
        [
            "",
            "---",
            "",
            "*Generated by Multi-Agent Orchestration System*",
        ]
    )

    # Build JSON summary
    summary_json = {
        "project": state["project_name"],
        "completed_at": datetime.now().isoformat(),
        "plan": plan.get("plan_name"),
        "implementation": impl_result,
        "phase_status": {
            k: v.to_dict() if hasattr(v, "to_dict") else str(v) for k, v in phase_status.items()
        },
        "total_errors": len(errors),
        "total_commits": len(git_commits),
        "markdown_summary": "\n".join(summary_lines),
    }

    # Save completion summary to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save_summary(summary_json))

    # Update phase status
    phase_5.status = PhaseStatus.COMPLETED
    phase_5.completed_at = datetime.now().isoformat()
    phase_5.output = {"summary_saved": True}
    phase_status["5"] = phase_5

    logger.info("Completion summary saved to database")

    # Run scheduled cleanup to remove old persistent artifacts
    try:
        cleanup_manager = CleanupManager(project_dir)
        cleanup_result = cleanup_manager.scheduled_cleanup()
        if cleanup_result.total_deleted > 0:
            logger.info(
                f"Scheduled cleanup: {cleanup_result.total_deleted} items, "
                f"{cleanup_result.bytes_freed} bytes freed"
            )
    except Exception as e:
        logger.warning(f"Scheduled cleanup failed: {e}")

    return {
        "phase_status": phase_status,
        "current_phase": 5,
        "next_decision": "continue",
        "updated_at": datetime.now().isoformat(),
    }
