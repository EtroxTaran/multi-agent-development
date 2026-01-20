"""LangGraph adapter for ConflictResolver.

Wraps the existing ConflictResolver for use in LangGraph workflow nodes,
detecting and resolving conflicts between Cursor and Gemini feedback.
"""

import logging
from typing import Optional, Any

from ...utils.conflict_resolution import (
    ConflictResolver,
    ResolutionStrategy,
    ConflictResult,
    Conflict,
    ConflictResolution,
)
from ..state import WorkflowState, AgentFeedback, WorkflowDecision

logger = logging.getLogger(__name__)


class LangGraphConflictAdapter:
    """Adapter for using ConflictResolver with LangGraph state.

    Detects conflicts between agent feedback and resolves them
    according to configured strategies.
    """

    def __init__(
        self,
        default_strategy: ResolutionStrategy = ResolutionStrategy.WEIGHTED,
        custom_weights: Optional[dict[str, dict[str, float]]] = None,
    ):
        """Initialize the adapter.

        Args:
            default_strategy: Default resolution strategy
            custom_weights: Optional custom expertise weights
        """
        self.resolver = ConflictResolver(
            default_strategy=default_strategy,
            custom_weights=custom_weights,
        )

    def detect_and_resolve(
        self,
        state: WorkflowState,
        feedback_key: str = "validation_feedback",
        strategy: Optional[ResolutionStrategy] = None,
    ) -> dict[str, Any]:
        """Detect conflicts in feedback and resolve them.

        Args:
            state: Current LangGraph workflow state
            feedback_key: Key to get feedback from state
            strategy: Resolution strategy (uses default if not specified)

        Returns:
            State updates dict with conflict resolution details
        """
        feedback = state.get(feedback_key, {})

        cursor_fb = feedback.get("cursor")
        gemini_fb = feedback.get("gemini")

        # Convert to dict format
        cursor_dict = self._feedback_to_dict(cursor_fb)
        gemini_dict = self._feedback_to_dict(gemini_fb)

        # Resolve all conflicts
        result = self.resolver.resolve_all(
            cursor_feedback=cursor_dict,
            gemini_feedback=gemini_dict,
            strategy=strategy,
        )

        return self._result_to_state_update(result)

    def get_consensus(
        self,
        state: WorkflowState,
        feedback_key: str = "validation_feedback",
    ) -> dict[str, Any]:
        """Get consensus recommendation from both agents.

        Args:
            state: Current LangGraph workflow state
            feedback_key: Key to get feedback from state

        Returns:
            Consensus recommendation with state updates
        """
        feedback = state.get(feedback_key, {})

        cursor_fb = feedback.get("cursor")
        gemini_fb = feedback.get("gemini")

        cursor_dict = self._feedback_to_dict(cursor_fb)
        gemini_dict = self._feedback_to_dict(gemini_fb)

        consensus = self.resolver.get_consensus_recommendation(
            cursor_feedback=cursor_dict,
            gemini_feedback=gemini_dict,
        )

        # Determine next decision based on recommendation
        rec = consensus.get("recommendation", "")
        if rec == "proceed":
            next_decision = WorkflowDecision.CONTINUE
        elif rec == "proceed_with_caution":
            next_decision = WorkflowDecision.CONTINUE
        elif rec == "escalate":
            next_decision = WorkflowDecision.ESCALATE
        else:
            next_decision = WorkflowDecision.RETRY

        return {
            "consensus": consensus,
            "next_decision": next_decision,
            "has_conflicts": consensus.get("has_conflicts", False),
            "requires_escalation": consensus.get("requires_escalation", False),
        }

    def resolve_single_conflict(
        self,
        conflict_area: str,
        cursor_position: str,
        gemini_position: str,
        strategy: Optional[ResolutionStrategy] = None,
    ) -> ConflictResolution:
        """Resolve a single conflict manually.

        Args:
            conflict_area: Area of the conflict (e.g., "security")
            cursor_position: Cursor's position
            gemini_position: Gemini's position
            strategy: Resolution strategy

        Returns:
            ConflictResolution with the decision
        """
        from ...utils.conflict_resolution import Conflict, ConflictType

        conflict = Conflict(
            conflict_type=ConflictType.RECOMMENDATION_CONFLICT,
            area=conflict_area,
            cursor_position=cursor_position,
            gemini_position=gemini_position,
        )

        return self.resolver.resolve(conflict, strategy)

    def _feedback_to_dict(
        self,
        feedback: Optional[AgentFeedback | dict],
    ) -> Optional[dict]:
        """Convert AgentFeedback to dict format.

        Args:
            feedback: AgentFeedback object or dict

        Returns:
            Dictionary format expected by ConflictResolver
        """
        if feedback is None:
            return None

        if isinstance(feedback, dict):
            return feedback

        if hasattr(feedback, "to_dict"):
            return feedback.to_dict()

        # Convert AgentFeedback dataclass
        return {
            "overall_assessment": feedback.assessment if hasattr(feedback, "assessment") else "unknown",
            "score": feedback.score if hasattr(feedback, "score") else 0,
            "concerns": feedback.concerns if hasattr(feedback, "concerns") else [],
            "blocking_issues": feedback.blocking_issues if hasattr(feedback, "blocking_issues") else [],
        }

    def _result_to_state_update(
        self,
        result: ConflictResult,
    ) -> dict[str, Any]:
        """Convert ConflictResult to LangGraph state update.

        Args:
            result: ConflictResult from the resolver

        Returns:
            State update dictionary for LangGraph
        """
        # Determine next decision based on conflicts
        if result.requires_escalation:
            next_decision = WorkflowDecision.ESCALATE
        elif not result.has_conflicts or result.unresolved_count == 0:
            next_decision = WorkflowDecision.CONTINUE
        else:
            next_decision = WorkflowDecision.RETRY

        update = {
            "conflict_result": result.to_dict(),
            "has_conflicts": result.has_conflicts,
            "unresolved_conflicts": result.unresolved_count,
            "requires_escalation": result.requires_escalation,
        }

        if result.requires_escalation:
            update["next_decision"] = next_decision

        logger.info(
            f"Conflict resolution: has_conflicts={result.has_conflicts}, "
            f"unresolved={result.unresolved_count}, "
            f"escalation_required={result.requires_escalation}"
        )

        return update


# Default adapter instance
default_conflict_adapter = LangGraphConflictAdapter()


def resolve_validation_conflicts(
    state: WorkflowState,
    strategy: Optional[ResolutionStrategy] = None,
) -> dict[str, Any]:
    """Convenience function to resolve validation conflicts.

    Args:
        state: LangGraph workflow state
        strategy: Resolution strategy

    Returns:
        State update dictionary
    """
    return default_conflict_adapter.detect_and_resolve(
        state,
        feedback_key="validation_feedback",
        strategy=strategy,
    )


def resolve_verification_conflicts(
    state: WorkflowState,
    strategy: Optional[ResolutionStrategy] = None,
) -> dict[str, Any]:
    """Convenience function to resolve verification conflicts.

    Args:
        state: LangGraph workflow state
        strategy: Resolution strategy

    Returns:
        State update dictionary
    """
    return default_conflict_adapter.detect_and_resolve(
        state,
        feedback_key="verification_feedback",
        strategy=strategy,
    )


def get_validation_consensus(state: WorkflowState) -> dict[str, Any]:
    """Get consensus recommendation for validation feedback.

    Args:
        state: LangGraph workflow state

    Returns:
        Consensus recommendation
    """
    return default_conflict_adapter.get_consensus(
        state,
        feedback_key="validation_feedback",
    )


def get_verification_consensus(state: WorkflowState) -> dict[str, Any]:
    """Get consensus recommendation for verification feedback.

    Args:
        state: LangGraph workflow state

    Returns:
        Consensus recommendation
    """
    return default_conflict_adapter.get_consensus(
        state,
        feedback_key="verification_feedback",
    )
