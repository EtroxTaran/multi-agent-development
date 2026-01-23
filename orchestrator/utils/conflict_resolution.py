"""Conflict resolution policies for multi-agent disagreements.

Provides strategies for resolving conflicts when Cursor and Gemini
provide conflicting feedback or recommendations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ResolutionStrategy(str, Enum):
    """Strategy for resolving agent conflicts."""

    UNANIMOUS = "unanimous"  # Both must agree
    WEIGHTED = "weighted"  # Based on expertise area
    ESCALATE = "escalate"  # Require human decision
    DEFER_TO_LEAD = "defer_to_lead"  # Claude decides as lead orchestrator
    CONSERVATIVE = "conservative"  # Take the more cautious position
    OPTIMISTIC = "optimistic"  # Take the more permissive position


class ConflictType(str, Enum):
    """Types of conflicts between agents."""

    APPROVAL_MISMATCH = "approval_mismatch"  # One approves, one rejects
    SEVERITY_DISAGREEMENT = "severity_disagreement"  # Different severity for same issue
    RECOMMENDATION_CONFLICT = "recommendation_conflict"  # Different solutions proposed
    SCORE_DIVERGENCE = "score_divergence"  # Significant score gap


@dataclass
class Conflict:
    """Represents a conflict between agents."""

    conflict_type: ConflictType
    area: str
    cursor_position: str
    gemini_position: str
    cursor_confidence: float = 0.5
    gemini_confidence: float = 0.5
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "conflict_type": self.conflict_type.value,
            "area": self.area,
            "cursor_position": self.cursor_position,
            "gemini_position": self.gemini_position,
            "cursor_confidence": self.cursor_confidence,
            "gemini_confidence": self.gemini_confidence,
            "details": self.details,
        }


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""

    resolved: bool
    strategy_used: ResolutionStrategy
    winning_position: str
    winning_agent: Optional[str]
    reasoning: str
    requires_human_input: bool = False
    escalation_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "resolved": self.resolved,
            "strategy_used": self.strategy_used.value,
            "winning_position": self.winning_position,
            "winning_agent": self.winning_agent,
            "reasoning": self.reasoning,
            "requires_human_input": self.requires_human_input,
            "escalation_reason": self.escalation_reason,
        }


@dataclass
class ConflictResult:
    """Complete result of conflict detection and resolution."""

    has_conflicts: bool
    conflicts: list[Conflict] = field(default_factory=list)
    resolutions: list[ConflictResolution] = field(default_factory=list)
    unresolved_count: int = 0
    requires_escalation: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "has_conflicts": self.has_conflicts,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "resolutions": [r.to_dict() for r in self.resolutions],
            "unresolved_count": self.unresolved_count,
            "requires_escalation": self.requires_escalation,
        }


class ConflictResolver:
    """Resolves conflicts between Cursor and Gemini feedback.

    Uses weighted expertise areas to determine which agent's
    recommendation should be preferred in case of disagreement.
    """

    # Expertise weights by area (higher = more trusted for that area)
    EXPERTISE_WEIGHTS = {
        "security": {"cursor": 0.8, "gemini": 0.2},
        "architecture": {"cursor": 0.3, "gemini": 0.7},
        "code_quality": {"cursor": 0.7, "gemini": 0.3},
        "scalability": {"cursor": 0.2, "gemini": 0.8},
        "maintainability": {"cursor": 0.6, "gemini": 0.4},
        "testing": {"cursor": 0.7, "gemini": 0.3},
        "performance": {"cursor": 0.4, "gemini": 0.6},
        "patterns": {"cursor": 0.4, "gemini": 0.6},
        "integration": {"cursor": 0.5, "gemini": 0.5},
        "default": {"cursor": 0.5, "gemini": 0.5},
    }

    # Thresholds for detecting conflicts
    SCORE_DIVERGENCE_THRESHOLD = 3.0  # Difference that indicates conflict
    CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence to auto-resolve

    def __init__(
        self,
        default_strategy: ResolutionStrategy = ResolutionStrategy.WEIGHTED,
        custom_weights: Optional[dict[str, dict[str, float]]] = None,
    ):
        """Initialize conflict resolver.

        Args:
            default_strategy: Default resolution strategy
            custom_weights: Optional custom expertise weights
        """
        self.default_strategy = default_strategy
        self.weights = self.EXPERTISE_WEIGHTS.copy()
        if custom_weights:
            self.weights.update(custom_weights)

    def detect_conflicts(
        self,
        cursor_feedback: Optional[dict],
        gemini_feedback: Optional[dict],
    ) -> list[Conflict]:
        """Detect conflicts between agent feedback.

        Args:
            cursor_feedback: Feedback from Cursor
            gemini_feedback: Feedback from Gemini

        Returns:
            List of detected conflicts
        """
        conflicts = []

        if not cursor_feedback or not gemini_feedback:
            return conflicts

        # Check for approval mismatch
        cursor_assessment = cursor_feedback.get("overall_assessment", "").lower()
        gemini_assessment = gemini_feedback.get("overall_assessment", "").lower()

        cursor_approves = cursor_assessment in ("approve", "approved", "pass")
        gemini_approves = gemini_assessment in ("approve", "approved", "pass")

        if cursor_approves != gemini_approves:
            conflicts.append(
                Conflict(
                    conflict_type=ConflictType.APPROVAL_MISMATCH,
                    area="overall_approval",
                    cursor_position="approve" if cursor_approves else "reject",
                    gemini_position="approve" if gemini_approves else "reject",
                    details={
                        "cursor_assessment": cursor_assessment,
                        "gemini_assessment": gemini_assessment,
                    },
                )
            )

        # Check for score divergence
        cursor_score = float(cursor_feedback.get("score", 0))
        gemini_score = float(gemini_feedback.get("score", 0))

        if abs(cursor_score - gemini_score) >= self.SCORE_DIVERGENCE_THRESHOLD:
            conflicts.append(
                Conflict(
                    conflict_type=ConflictType.SCORE_DIVERGENCE,
                    area="overall_score",
                    cursor_position=f"score: {cursor_score}",
                    gemini_position=f"score: {gemini_score}",
                    details={
                        "cursor_score": cursor_score,
                        "gemini_score": gemini_score,
                        "divergence": abs(cursor_score - gemini_score),
                    },
                )
            )

        # Detect severity disagreements on common issues
        cursor_concerns = self._extract_concerns(cursor_feedback)
        gemini_concerns = self._extract_concerns(gemini_feedback)

        for area in set(cursor_concerns.keys()) & set(gemini_concerns.keys()):
            cursor_severity = cursor_concerns[area].get("severity", "").lower()
            gemini_severity = gemini_concerns[area].get("severity", "").lower()

            if cursor_severity != gemini_severity:
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
                        area=area,
                        cursor_position=cursor_severity or "unspecified",
                        gemini_position=gemini_severity or "unspecified",
                        details={
                            "cursor_concern": cursor_concerns[area],
                            "gemini_concern": gemini_concerns[area],
                        },
                    )
                )

        return conflicts

    def _extract_concerns(self, feedback: dict) -> dict[str, dict]:
        """Extract concerns organized by area."""
        concerns = {}

        # From direct concerns array
        for concern in feedback.get("concerns", []):
            if isinstance(concern, dict):
                area = concern.get("area", "unknown")
                concerns[area] = concern

        # From architecture review (Gemini)
        arch_review = feedback.get("architecture_review", {})
        for concern in arch_review.get("concerns", []):
            if isinstance(concern, dict):
                area = concern.get("area", "unknown")
                concerns[area] = concern

        return concerns

    def resolve(
        self,
        conflict: Conflict,
        strategy: Optional[ResolutionStrategy] = None,
    ) -> ConflictResolution:
        """Resolve a single conflict.

        Args:
            conflict: The conflict to resolve
            strategy: Resolution strategy (uses default if not specified)

        Returns:
            ConflictResolution with the decision
        """
        strategy = strategy or self.default_strategy

        if strategy == ResolutionStrategy.UNANIMOUS:
            return self._resolve_unanimous(conflict)
        elif strategy == ResolutionStrategy.WEIGHTED:
            return self._resolve_weighted(conflict)
        elif strategy == ResolutionStrategy.ESCALATE:
            return self._resolve_escalate(conflict)
        elif strategy == ResolutionStrategy.DEFER_TO_LEAD:
            return self._resolve_defer_to_lead(conflict)
        elif strategy == ResolutionStrategy.CONSERVATIVE:
            return self._resolve_conservative(conflict)
        elif strategy == ResolutionStrategy.OPTIMISTIC:
            return self._resolve_optimistic(conflict)
        else:
            return self._resolve_weighted(conflict)

    def _resolve_unanimous(self, conflict: Conflict) -> ConflictResolution:
        """Resolution requiring unanimous agreement - escalates if no agreement."""
        return ConflictResolution(
            resolved=False,
            strategy_used=ResolutionStrategy.UNANIMOUS,
            winning_position="",
            winning_agent=None,
            reasoning="Agents disagree; unanimous agreement required",
            requires_human_input=True,
            escalation_reason=f"Conflict in {conflict.area}: {conflict.cursor_position} vs {conflict.gemini_position}",
        )

    def _resolve_weighted(self, conflict: Conflict) -> ConflictResolution:
        """Resolution based on expertise weights."""
        area = conflict.area.lower()

        # Find best matching expertise area
        weights = self.weights.get("default", {"cursor": 0.5, "gemini": 0.5})
        for key in self.weights:
            if key in area or area in key:
                weights = self.weights[key]
                break

        cursor_weight = weights["cursor"]
        gemini_weight = weights["gemini"]

        # Apply confidence modifiers
        cursor_effective = cursor_weight * conflict.cursor_confidence
        gemini_effective = gemini_weight * conflict.gemini_confidence

        if cursor_effective > gemini_effective:
            return ConflictResolution(
                resolved=True,
                strategy_used=ResolutionStrategy.WEIGHTED,
                winning_position=conflict.cursor_position,
                winning_agent="cursor",
                reasoning=f"Cursor preferred for {area} (weight: {cursor_weight:.2f})",
            )
        elif gemini_effective > cursor_effective:
            return ConflictResolution(
                resolved=True,
                strategy_used=ResolutionStrategy.WEIGHTED,
                winning_position=conflict.gemini_position,
                winning_agent="gemini",
                reasoning=f"Gemini preferred for {area} (weight: {gemini_weight:.2f})",
            )
        else:
            # Tie - escalate
            return ConflictResolution(
                resolved=False,
                strategy_used=ResolutionStrategy.WEIGHTED,
                winning_position="",
                winning_agent=None,
                reasoning=f"Equal weights for {area}; requires human decision",
                requires_human_input=True,
            )

    def _resolve_escalate(self, conflict: Conflict) -> ConflictResolution:
        """Always escalate to human."""
        return ConflictResolution(
            resolved=False,
            strategy_used=ResolutionStrategy.ESCALATE,
            winning_position="",
            winning_agent=None,
            reasoning="Escalation policy: human decision required",
            requires_human_input=True,
            escalation_reason=f"Conflict in {conflict.area} requires review",
        )

    def _resolve_defer_to_lead(self, conflict: Conflict) -> ConflictResolution:
        """Defer to Claude (lead orchestrator) to make the decision."""
        return ConflictResolution(
            resolved=True,
            strategy_used=ResolutionStrategy.DEFER_TO_LEAD,
            winning_position="deferred",
            winning_agent="claude",
            reasoning="Lead orchestrator (Claude) will evaluate and decide",
        )

    def _resolve_conservative(self, conflict: Conflict) -> ConflictResolution:
        """Take the more conservative/cautious position."""
        # For approval conflicts, conservative means reject
        if conflict.conflict_type == ConflictType.APPROVAL_MISMATCH:
            winner = "cursor" if conflict.cursor_position == "reject" else "gemini"
            position = "reject"
        # For severity, take the higher severity
        elif conflict.conflict_type == ConflictType.SEVERITY_DISAGREEMENT:
            severity_order = ["high", "critical", "medium", "low"]
            cursor_idx = self._get_severity_index(conflict.cursor_position, severity_order)
            gemini_idx = self._get_severity_index(conflict.gemini_position, severity_order)
            winner = "cursor" if cursor_idx <= gemini_idx else "gemini"
            position = conflict.cursor_position if winner == "cursor" else conflict.gemini_position
        else:
            # For scores, take the lower score
            if "score" in conflict.cursor_position.lower():
                cursor_score = float(conflict.details.get("cursor_score", 5))
                gemini_score = float(conflict.details.get("gemini_score", 5))
                winner = "cursor" if cursor_score <= gemini_score else "gemini"
                position = (
                    conflict.cursor_position if winner == "cursor" else conflict.gemini_position
                )
            else:
                winner = "cursor"
                position = conflict.cursor_position

        return ConflictResolution(
            resolved=True,
            strategy_used=ResolutionStrategy.CONSERVATIVE,
            winning_position=position,
            winning_agent=winner,
            reasoning=f"Conservative approach: selected more cautious position from {winner}",
        )

    def _resolve_optimistic(self, conflict: Conflict) -> ConflictResolution:
        """Take the more optimistic/permissive position."""
        if conflict.conflict_type == ConflictType.APPROVAL_MISMATCH:
            winner = "cursor" if conflict.cursor_position == "approve" else "gemini"
            position = "approve"
        elif conflict.conflict_type == ConflictType.SEVERITY_DISAGREEMENT:
            severity_order = ["low", "medium", "high", "critical"]
            cursor_idx = self._get_severity_index(conflict.cursor_position, severity_order)
            gemini_idx = self._get_severity_index(conflict.gemini_position, severity_order)
            winner = "cursor" if cursor_idx <= gemini_idx else "gemini"
            position = conflict.cursor_position if winner == "cursor" else conflict.gemini_position
        else:
            if "score" in conflict.cursor_position.lower():
                cursor_score = float(conflict.details.get("cursor_score", 5))
                gemini_score = float(conflict.details.get("gemini_score", 5))
                winner = "cursor" if cursor_score >= gemini_score else "gemini"
                position = (
                    conflict.cursor_position if winner == "cursor" else conflict.gemini_position
                )
            else:
                winner = "gemini"
                position = conflict.gemini_position

        return ConflictResolution(
            resolved=True,
            strategy_used=ResolutionStrategy.OPTIMISTIC,
            winning_position=position,
            winning_agent=winner,
            reasoning=f"Optimistic approach: selected more permissive position from {winner}",
        )

    def _get_severity_index(self, severity: str, order: list[str]) -> int:
        """Get index of severity in order list."""
        severity_lower = severity.lower()
        for i, level in enumerate(order):
            if level in severity_lower or severity_lower in level:
                return i
        return len(order)  # Unknown severity goes to end

    def resolve_all(
        self,
        cursor_feedback: Optional[dict],
        gemini_feedback: Optional[dict],
        strategy: Optional[ResolutionStrategy] = None,
    ) -> ConflictResult:
        """Detect and resolve all conflicts.

        Args:
            cursor_feedback: Feedback from Cursor
            gemini_feedback: Feedback from Gemini
            strategy: Resolution strategy (uses default if not specified)

        Returns:
            ConflictResult with all conflicts and resolutions
        """
        conflicts = self.detect_conflicts(cursor_feedback, gemini_feedback)

        if not conflicts:
            return ConflictResult(has_conflicts=False)

        resolutions = []
        unresolved = 0
        requires_escalation = False

        for conflict in conflicts:
            resolution = self.resolve(conflict, strategy)
            resolutions.append(resolution)

            if not resolution.resolved:
                unresolved += 1
            if resolution.requires_human_input:
                requires_escalation = True

        return ConflictResult(
            has_conflicts=True,
            conflicts=conflicts,
            resolutions=resolutions,
            unresolved_count=unresolved,
            requires_escalation=requires_escalation,
        )

    def get_consensus_recommendation(
        self,
        cursor_feedback: Optional[dict],
        gemini_feedback: Optional[dict],
    ) -> dict:
        """Get a consensus recommendation from both agents.

        Combines feedback, resolving conflicts where necessary.

        Args:
            cursor_feedback: Feedback from Cursor
            gemini_feedback: Feedback from Gemini

        Returns:
            Dictionary with consensus recommendation
        """
        result = self.resolve_all(cursor_feedback, gemini_feedback)

        # Build consensus
        consensus = {
            "has_conflicts": result.has_conflicts,
            "resolved_count": len(result.conflicts) - result.unresolved_count,
            "unresolved_count": result.unresolved_count,
            "requires_escalation": result.requires_escalation,
            "resolutions": [r.to_dict() for r in result.resolutions],
        }

        # Determine overall recommendation
        if result.requires_escalation:
            consensus["recommendation"] = "escalate"
            consensus["recommendation_reason"] = "Unresolved conflicts require human input"
        elif not result.has_conflicts:
            cursor_approved = cursor_feedback and cursor_feedback.get(
                "overall_assessment", ""
            ).lower() in ("approve", "approved")
            gemini_approved = gemini_feedback and gemini_feedback.get(
                "overall_assessment", ""
            ).lower() in ("approve", "approved")
            if cursor_approved and gemini_approved:
                consensus["recommendation"] = "proceed"
                consensus["recommendation_reason"] = "Both agents agree to approve"
            else:
                consensus["recommendation"] = "revise"
                consensus["recommendation_reason"] = "Changes needed based on feedback"
        else:
            # All conflicts resolved
            consensus["recommendation"] = "proceed_with_caution"
            consensus["recommendation_reason"] = "Conflicts resolved through policy"

        return consensus
