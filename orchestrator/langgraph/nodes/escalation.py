"""Escalation node for human-in-the-loop.

Pauses the workflow and waits for human intervention when
automated resolution fails.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from ..state import WorkflowState, PhaseStatus

logger = logging.getLogger(__name__)


async def human_escalation_node(state: WorkflowState) -> dict[str, Any]:
    """Escalate to human for intervention.

    Uses LangGraph's interrupt() to pause execution and wait
    for human input to resolve the issue.

    Args:
        state: Current workflow state

    Returns:
        State updates after human intervention
    """
    logger.warning(f"Escalating to human: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    errors = state.get("errors", [])
    current_phase = state.get("current_phase", 0)

    # Build escalation context
    escalation = {
        "project": state["project_name"],
        "current_phase": current_phase,
        "phase_status": {
            k: v.to_dict() if hasattr(v, "to_dict") else str(v)
            for k, v in state.get("phase_status", {}).items()
        },
        "recent_errors": errors[-5:] if errors else [],
        "timestamp": datetime.now().isoformat(),
    }

    # Determine the issue type
    issue_summary = "Unknown issue"
    suggested_actions = []

    if errors:
        last_error = errors[-1]
        error_type = last_error.get("type", "unknown")

        if error_type == "planning_error":
            issue_summary = "Planning phase failed repeatedly"
            suggested_actions = [
                "Review PRODUCT.md for clarity",
                "Simplify the feature requirements",
                "Manually create a plan and retry validation",
            ]
        elif error_type == "validation_failed":
            issue_summary = "Plan validation failed after max attempts"
            suggested_actions = [
                "Review blocking issues from agents",
                "Modify the plan manually",
                "Reduce scope of the feature",
            ]
        elif error_type == "implementation_error":
            # Check if this is a clarification request
            clarifications = last_error.get("clarifications", [])
            if clarifications:
                issue_summary = f"Worker needs clarification: {clarifications[0].get('question', 'Unknown')}"
                suggested_actions = [
                    "Answer the clarification question below",
                    "Update the plan with more specific requirements",
                    "Provide guidance in PRODUCT.md and retry",
                ]
                # Add clarification details to escalation
                escalation["clarifications"] = clarifications
            else:
                issue_summary = "Implementation phase failed"
                suggested_actions = [
                    "Check for dependency issues",
                    "Review the plan for feasibility",
                    "Implement manually and skip to verification",
                ]
        elif error_type == "verification_failed":
            issue_summary = "Code verification failed after max attempts"
            suggested_actions = [
                "Review blocking issues from reviewers",
                "Fix issues manually",
                "Accept with known issues",
            ]

    escalation["issue_summary"] = issue_summary
    escalation["suggested_actions"] = suggested_actions

    # Save escalation details
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    escalation_file = workflow_dir / "escalation.json"
    escalation_file.write_text(json.dumps(escalation, indent=2))

    # Log to blockers.md
    blockers_file = workflow_dir / "blockers.md"
    blocker_entry = f"""
## Escalation - {datetime.now().isoformat()}

**Phase:** {current_phase}
**Issue:** {issue_summary}

### Recent Errors
```json
{json.dumps(errors[-3:] if errors else [], indent=2)}
```

### Suggested Actions
{chr(10).join(f'- {action}' for action in suggested_actions)}

---
"""
    with open(blockers_file, "a") as f:
        f.write(blocker_entry)

    logger.info(f"Escalation saved to: {escalation_file}")

    # Use LangGraph interrupt to pause for human input
    # The human can:
    # 1. Modify state and resume
    # 2. Skip to a specific phase
    # 3. Abort the workflow
    human_response = interrupt({
        "type": "escalation",
        "project": state["project_name"],
        "phase": current_phase,
        "issue": issue_summary,
        "suggested_actions": suggested_actions,
        "message": (
            f"Workflow paused at phase {current_phase}: {issue_summary}. "
            f"Please resolve the issue and resume."
        ),
    })

    # Process human response
    if human_response is None:
        # Timeout or no response - abort
        return {
            "next_decision": "abort",
            "errors": [{
                "type": "escalation_timeout",
                "message": "Human escalation timed out",
                "timestamp": datetime.now().isoformat(),
            }],
        }

    action = human_response.get("action", "abort")

    if action == "retry":
        # Retry the current phase
        return {
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "skip":
        # Skip to specified phase
        target_phase = human_response.get("target_phase", current_phase + 1)
        phase_status = state.get("phase_status", {}).copy()

        # Mark current phase as skipped
        if str(current_phase) in phase_status:
            ps = phase_status[str(current_phase)]
            ps.status = PhaseStatus.SKIPPED
            phase_status[str(current_phase)] = ps

        return {
            "phase_status": phase_status,
            "current_phase": target_phase,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "continue":
        # Human fixed the issue, continue
        return {
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    elif action == "answer_clarification":
        # Human answered clarification question - save and retry implementation
        answers = human_response.get("answers", {})
        if answers:
            # Save answers to workflow directory for implementation to read
            clarification_file = workflow_dir / "clarification_answers.json"
            existing = {}
            if clarification_file.exists():
                try:
                    existing = json.loads(clarification_file.read_text())
                except json.JSONDecodeError:
                    pass
            existing.update(answers)
            existing["timestamp"] = datetime.now().isoformat()
            clarification_file.write_text(json.dumps(existing, indent=2))

            logger.info(f"Saved clarification answers: {list(answers.keys())}")

        return {
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Abort
        return {
            "next_decision": "abort",
            "errors": [{
                "type": "user_abort",
                "message": "Workflow aborted by user",
                "timestamp": datetime.now().isoformat(),
            }],
        }
