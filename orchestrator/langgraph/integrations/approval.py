"""LangGraph adapter for ApprovalEngine.

Wraps the existing ApprovalEngine for use in LangGraph workflow nodes,
converting between LangGraph state and approval engine formats.
"""

import logging
from typing import Any, Optional

from ...utils.approval import ApprovalConfig, ApprovalEngine, ApprovalResult, ApprovalStatus
from ..state import AgentFeedback, WorkflowDecision, WorkflowState

logger = logging.getLogger(__name__)


class LangGraphApprovalAdapter:
    """Adapter for using ApprovalEngine with LangGraph state.

    Converts between LangGraph's AgentFeedback format and the
    ApprovalEngine's expected format, and translates results
    back to LangGraph state updates.
    """

    def __init__(self, custom_configs: Optional[dict[int, ApprovalConfig]] = None):
        """Initialize the adapter.

        Args:
            custom_configs: Optional custom approval configs per phase
        """
        self.engine = ApprovalEngine(custom_configs=custom_configs)

    def evaluate_validation(
        self,
        state: WorkflowState,
        config: Optional[ApprovalConfig] = None,
    ) -> dict[str, Any]:
        """Evaluate Phase 2 validation approval from LangGraph state.

        Args:
            state: Current LangGraph workflow state
            config: Optional custom approval config

        Returns:
            State updates dict for LangGraph
        """
        validation_feedback = state.get("validation_feedback", {})

        cursor_fb = validation_feedback.get("cursor")
        gemini_fb = validation_feedback.get("gemini")

        # Convert AgentFeedback to dict format
        cursor_dict = self._agent_feedback_to_dict(cursor_fb)
        gemini_dict = self._agent_feedback_to_dict(gemini_fb)

        # Use the approval engine
        result = self.engine.evaluate_for_validation(
            cursor_feedback=cursor_dict,
            gemini_feedback=gemini_dict,
            config=config,
        )

        return self._result_to_state_update(result, phase=2)

    def evaluate_verification(
        self,
        state: WorkflowState,
        config: Optional[ApprovalConfig] = None,
    ) -> dict[str, Any]:
        """Evaluate Phase 4 verification approval from LangGraph state.

        Args:
            state: Current LangGraph workflow state
            config: Optional custom approval config

        Returns:
            State updates dict for LangGraph
        """
        verification_feedback = state.get("verification_feedback", {})

        cursor_review = verification_feedback.get("cursor")
        gemini_review = verification_feedback.get("gemini")

        # Convert to dict format
        cursor_dict = self._agent_feedback_to_dict(cursor_review)
        gemini_dict = self._agent_feedback_to_dict(gemini_review)

        # Use the approval engine
        result = self.engine.evaluate_for_verification(
            cursor_review=cursor_dict,
            gemini_review=gemini_dict,
            config=config,
        )

        return self._result_to_state_update(result, phase=4)

    def _agent_feedback_to_dict(
        self,
        feedback: Optional[AgentFeedback | dict],
    ) -> Optional[dict]:
        """Convert AgentFeedback to dict format.

        Args:
            feedback: AgentFeedback object or dict

        Returns:
            Dictionary format expected by ApprovalEngine
        """
        if feedback is None:
            return None

        if isinstance(feedback, dict):
            return feedback

        if hasattr(feedback, "to_dict"):
            return feedback.to_dict()

        # Convert AgentFeedback dataclass
        return {
            "agent": feedback.agent if hasattr(feedback, "agent") else "unknown",
            "overall_assessment": feedback.assessment
            if hasattr(feedback, "assessment")
            else "unknown",
            "score": feedback.score if hasattr(feedback, "score") else 0,
            "approved": feedback.approved if hasattr(feedback, "approved") else False,
            "blocking_issues": feedback.blocking_issues
            if hasattr(feedback, "blocking_issues")
            else [],
            "concerns": feedback.concerns if hasattr(feedback, "concerns") else [],
            "summary": feedback.summary if hasattr(feedback, "summary") else "",
            "error": None,
        }

    def _result_to_state_update(
        self,
        result: ApprovalResult,
        phase: int,
    ) -> dict[str, Any]:
        """Convert ApprovalResult to LangGraph state update.

        Args:
            result: ApprovalResult from the engine
            phase: Current phase number

        Returns:
            State update dictionary for LangGraph
        """
        # Determine next decision
        if result.approved:
            next_decision = WorkflowDecision.CONTINUE
        elif result.status == ApprovalStatus.REJECTED:
            next_decision = WorkflowDecision.ESCALATE
        else:
            next_decision = WorkflowDecision.RETRY

        update = {
            "next_decision": next_decision,
            "approval_result": result.to_dict(),
        }

        # Log the decision
        logger.info(
            f"Phase {phase} approval: status={result.status.value}, "
            f"approved={result.approved}, score={result.combined_score:.1f}, "
            f"blocking={len(result.blocking_issues)}"
        )

        return update

    def get_config_for_phase(self, phase: int) -> ApprovalConfig:
        """Get the approval configuration for a specific phase.

        Args:
            phase: Phase number

        Returns:
            ApprovalConfig for the phase
        """
        return self.engine.get_config(phase)

    def set_custom_config(self, phase: int, config: ApprovalConfig) -> None:
        """Set a custom configuration for a phase.

        Args:
            phase: Phase number
            config: Custom ApprovalConfig
        """
        self.engine.configs[phase] = config


# Default adapter instance
default_approval_adapter = LangGraphApprovalAdapter()


def evaluate_validation_approval(
    state: WorkflowState,
    config: Optional[ApprovalConfig] = None,
) -> dict[str, Any]:
    """Convenience function to evaluate validation approval.

    Args:
        state: LangGraph workflow state
        config: Optional custom config

    Returns:
        State update dictionary
    """
    return default_approval_adapter.evaluate_validation(state, config)


def evaluate_verification_approval(
    state: WorkflowState,
    config: Optional[ApprovalConfig] = None,
) -> dict[str, Any]:
    """Convenience function to evaluate verification approval.

    Args:
        state: LangGraph workflow state
        config: Optional custom config

    Returns:
        State update dictionary
    """
    return default_approval_adapter.evaluate_verification(state, config)
