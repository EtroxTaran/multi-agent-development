"""Security Specialist node for Phase 2 validation enhancement.

This node reviews HIGH severity security concerns from Cursor/Gemini
and determines if they are actual vulnerabilities or specification gaps.
Only escalates to human when genuinely ambiguous.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...agents import get_security_specialist
from ..integrations.action_logging import get_node_logger
from ..state import WorkflowState

logger = logging.getLogger(__name__)


def _extract_high_severity_concerns(validation_feedback: dict) -> list[dict]:
    """Extract HIGH severity concerns from validation feedback.

    Args:
        validation_feedback: Dict of agent -> AgentFeedback

    Returns:
        List of HIGH severity concerns with agent source
    """
    concerns = []

    for agent_name, feedback in validation_feedback.items():
        if not feedback:
            continue

        # Get concerns from feedback
        agent_concerns: list[dict[str, Any]] = []
        if hasattr(feedback, "concerns"):
            agent_concerns = feedback.concerns or []
        elif isinstance(feedback, dict):
            agent_concerns = feedback.get("concerns", [])

        # Filter to HIGH severity only
        for concern in agent_concerns:
            severity = concern.get("severity", "").lower() if isinstance(concern, dict) else ""
            if severity == "high":
                concerns.append(
                    {
                        **concern,
                        "source_agent": agent_name,
                    }
                )

    return concerns


def _load_security_docs(project_dir: Path) -> str:
    """Load security documentation if available.

    Args:
        project_dir: Project directory path

    Returns:
        Security documentation content or empty string
    """
    # Check common locations for security docs
    doc_paths = [
        project_dir / "docs" / "security-requirements.md",
        project_dir / "Docs" / "security-requirements.md",
        project_dir / "docs" / "security.md",
        project_dir / "SECURITY.md",
    ]

    for path in doc_paths:
        if path.exists():
            try:
                content = path.read_text()
                logger.debug(f"Loaded security docs from {path}")
                return content
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")

    return ""


async def security_specialist_node(state: WorkflowState) -> dict[str, Any]:
    """Security Specialist reviews HIGH severity concerns.

    This node:
    1. Extracts HIGH severity concerns from validation feedback
    2. Uses heuristic-based classification (fast path) for common patterns
    3. Falls back to agent-based analysis for complex cases
    4. Reclassifies spec gaps as MEDIUM severity
    5. Only escalates to human when genuinely ambiguous

    Args:
        state: Current workflow state with validation feedback

    Returns:
        State updates with reclassified concerns and updated feedback
    """
    logger.info("Security Specialist reviewing concerns...")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)

    action_logger.log_agent_invoke(
        "security_specialist", "Reviewing HIGH severity concerns", phase=2
    )

    # Get validation feedback
    validation_feedback = state.get("validation_feedback", {})

    if not validation_feedback:
        logger.debug("No validation feedback to review")
        return {}

    # Extract HIGH severity concerns
    high_severity_concerns = _extract_high_severity_concerns(validation_feedback)

    if not high_severity_concerns:
        logger.info("No HIGH severity concerns to review")
        action_logger.log_info("No HIGH severity concerns found", phase=2)
        return {
            "security_specialist_result": {
                "reviewed": True,
                "concerns_reviewed": 0,
                "reclassifications": [],
                "escalation_required": False,
            }
        }

    logger.info(f"Reviewing {len(high_severity_concerns)} HIGH severity concerns")

    # Check if security docs exist
    security_docs = _load_security_docs(project_dir)
    has_security_docs = bool(security_docs)

    # Initialize security specialist
    specialist = get_security_specialist(project_dir)

    # First pass: use heuristic-based classification (fast path)
    reclassifications = []
    confirmed_vulnerabilities = []
    needs_agent_review = []

    for concern in high_severity_concerns:
        result = specialist.reclassify_concern(concern, has_security_docs)

        if result.get("classification") == "specification_gap":
            reclassifications.append(result)
            logger.debug(f"Reclassified as spec gap: {concern.get('description', '')[:50]}")
        elif result.get("classification") == "implementation_flaw":
            confirmed_vulnerabilities.append(result)
            logger.debug(f"Confirmed vulnerability: {concern.get('description', '')[:50]}")
        else:
            # Needs deeper review
            needs_agent_review.append(concern)

    # If we have concerns that need agent review, run the full analysis
    escalation_required = False
    escalation_questions = []

    if needs_agent_review:
        logger.info(f"Running agent analysis on {len(needs_agent_review)} complex concerns")

        # Build project context
        plan = state.get("plan", {})
        project_context = f"Plan: {plan.get('plan_name', 'Unknown')}\n"
        project_context += f"Tasks: {len(plan.get('tasks', []))}"

        # Run agent-based analysis
        analysis_result = specialist.analyze_concerns(
            concerns=needs_agent_review,
            project_context=project_context,
            security_docs=security_docs[:10000] if security_docs else None,
        )

        if analysis_result.success:
            reclassifications.extend(analysis_result.reclassifications)
            confirmed_vulnerabilities.extend(analysis_result.confirmed_vulnerabilities)
            escalation_required = analysis_result.human_escalation_required
            escalation_questions = analysis_result.escalation_questions

    # Update the validation feedback with reclassified concerns
    updated_feedback = {}
    for agent_name, feedback in validation_feedback.items():
        if feedback is None:
            continue

        # Get blocking issues from feedback
        blocking_issues = []
        if hasattr(feedback, "blocking_issues"):
            blocking_issues = list(feedback.blocking_issues or [])
        elif isinstance(feedback, dict):
            blocking_issues = list(feedback.get("blocking_issues", []))

        # Remove reclassified concerns from blocking issues
        reclassified_descriptions = {
            r.get("original_concern") or r.get("description", "") for r in reclassifications
        }

        new_blocking_issues = [
            issue for issue in blocking_issues if issue not in reclassified_descriptions
        ]

        # Only add confirmed vulnerabilities
        for vuln in confirmed_vulnerabilities:
            if vuln.get("source_agent") == agent_name:
                desc = vuln.get("description", "")
                if desc and desc not in new_blocking_issues:
                    new_blocking_issues.append(desc)

        # Update feedback
        if hasattr(feedback, "blocking_issues"):
            feedback.blocking_issues = new_blocking_issues
            updated_feedback[agent_name] = feedback
        elif isinstance(feedback, dict):
            feedback["blocking_issues"] = new_blocking_issues
            updated_feedback[agent_name] = feedback

    # Build result
    result = {
        "reviewed": True,
        "concerns_reviewed": len(high_severity_concerns),
        "reclassifications": [
            {
                "description": r.get("description", ""),
                "original_severity": r.get("original_severity", "high"),
                "new_severity": r.get("severity", "medium"),
                "classification": r.get("classification", "specification_gap"),
                "best_practice": r.get("best_practice", {}),
            }
            for r in reclassifications
        ],
        "confirmed_vulnerabilities": [
            {
                "description": v.get("description", ""),
                "severity": "high",
                "classification": "implementation_flaw",
            }
            for v in confirmed_vulnerabilities
        ],
        "escalation_required": escalation_required,
        "escalation_questions": escalation_questions,
        "security_docs_available": has_security_docs,
        "timestamp": datetime.now().isoformat(),
    }

    # Log summary
    action_logger.log_info(
        f"Security review complete: {len(reclassifications)} reclassified, "
        f"{len(confirmed_vulnerabilities)} confirmed, "
        f"escalation={escalation_required}",
        phase=2,
    )

    logger.info(
        f"Security Specialist: {len(reclassifications)} spec gaps reclassified, "
        f"{len(confirmed_vulnerabilities)} vulnerabilities confirmed"
    )

    # Build state updates
    state_updates: dict[str, Any] = {
        "security_specialist_result": result,
        "updated_at": datetime.now().isoformat(),
    }

    # Only update validation_feedback if we made changes
    if updated_feedback:
        state_updates["validation_feedback"] = updated_feedback

    # Determine if we should change the routing decision
    current_decision = state.get("next_decision")

    if escalation_required:
        # Security specialist needs human input
        state_updates["next_decision"] = "escalate"
        state_updates["escalation_reason"] = "security_ambiguity"
        state_updates["escalation_questions"] = escalation_questions
        logger.info("Security specialist requesting human escalation")

    elif current_decision == "retry" and not confirmed_vulnerabilities:
        # All blocking issues were reclassified as spec gaps
        # Check if we should change decision to continue
        total_remaining_blockers = sum(
            len(fb.blocking_issues)
            if hasattr(fb, "blocking_issues")
            else len(fb.get("blocking_issues", []))
            for fb in updated_feedback.values()
            if fb is not None
        )

        if total_remaining_blockers == 0:
            logger.info(
                f"Security specialist reclassified all {len(reclassifications)} blocking issues as spec gaps - "
                f"changing decision from 'retry' to 'continue'"
            )
            state_updates["next_decision"] = "continue"

            # Update phase status to completed
            phase_status = state.get("phase_status", {}).copy()
            phase_2 = phase_status.get("2")
            if phase_2:
                from ..state import PhaseStatus

                phase_2.status = PhaseStatus.COMPLETED
                phase_2.completed_at = datetime.now().isoformat()
                phase_status["2"] = phase_2
                state_updates["phase_status"] = phase_status
                state_updates["current_phase"] = 3

            action_logger.log_info(
                f"Validation approved after security review (reclassified {len(reclassifications)} spec gaps)",
                phase=2,
            )

    elif confirmed_vulnerabilities:
        # Real vulnerabilities found - keep the current decision (retry or escalate)
        logger.info(
            f"Security specialist confirmed {len(confirmed_vulnerabilities)} real vulnerabilities - "
            f"keeping decision '{current_decision}'"
        )

    return state_updates
