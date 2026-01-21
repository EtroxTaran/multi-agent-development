"""
Conflict resolver adapter for the review cycle.

This module provides a simplified interface to the conflict resolution
system, adapted for the 4-eyes review protocol where multiple reviewers
(not just Cursor and Gemini) may disagree.

Usage:
    from orchestrator.review import ConflictResolver

    resolver = ConflictResolver()
    resolution = resolver.resolve(reviews)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from orchestrator.registry import get_agent, AgentConfig

logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """Types of reviewer conflicts."""

    APPROVAL_MISMATCH = "approval_mismatch"
    SCORE_DIVERGENCE = "score_divergence"
    SEVERITY_DISAGREEMENT = "severity_disagreement"
    SECURITY_VS_QUALITY = "security_vs_quality"


@dataclass
class ReviewConflict:
    """Represents a conflict between reviewers."""

    conflict_type: ConflictType
    reviewers: List[str]
    positions: Dict[str, str]  # reviewer_id -> position
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""

    resolved: bool
    final_decision: str  # "approved", "rejected", "needs_changes"
    winning_reviewer: Optional[str] = None
    reasoning: str = ""
    requires_human_input: bool = False
    escalation_reason: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resolved": self.resolved,
            "final_decision": self.final_decision,
            "winning_reviewer": self.winning_reviewer,
            "reasoning": self.reasoning,
            "requires_human_input": self.requires_human_input,
            "escalation_reason": self.escalation_reason,
            "confidence": self.confidence,
        }


class ConflictResolver:
    """Resolves conflicts between multiple reviewers.

    Uses weighted expertise to determine which reviewer's assessment
    should be preferred when there is disagreement.
    """

    # Base weights by review specialization
    SPECIALIZATION_WEIGHTS = {
        "security": 0.8,  # Security issues get high priority
        "code_quality": 0.6,
        "architecture": 0.7,
        None: 0.5,  # Default weight
    }

    # Score divergence threshold
    SCORE_DIVERGENCE_THRESHOLD = 2.0

    # Minimum confidence to auto-resolve
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(
        self,
        custom_weights: Optional[Dict[str, float]] = None,
        score_threshold: float = SCORE_DIVERGENCE_THRESHOLD,
    ):
        """Initialize conflict resolver.

        Args:
            custom_weights: Custom weights by agent ID
            score_threshold: Score difference to consider divergent
        """
        self.custom_weights = custom_weights or {}
        self.score_threshold = score_threshold

    def resolve(
        self,
        reviews: List[Dict[str, Any]],
    ) -> ConflictResolution:
        """Resolve conflicts between reviewer assessments.

        Args:
            reviews: List of review dictionaries with:
                - agent_id: Reviewer agent ID
                - approved: Boolean approval
                - score: Numeric score (1-10)
                - blocking_issues: List of blocking issues
                - security_findings: List of security findings

        Returns:
            ConflictResolution with final decision
        """
        if not reviews:
            return ConflictResolution(
                resolved=False,
                final_decision="error",
                reasoning="No reviews provided",
            )

        # Check for unanimous approval
        all_approved = all(r.get("approved", False) for r in reviews)
        none_approved = all(not r.get("approved", False) for r in reviews)

        if all_approved:
            avg_score = sum(r.get("score", 0) for r in reviews) / len(reviews)
            return ConflictResolution(
                resolved=True,
                final_decision="approved",
                reasoning="All reviewers approved",
                confidence=avg_score / 10.0,
            )

        if none_approved:
            return ConflictResolution(
                resolved=True,
                final_decision="needs_changes",
                reasoning="All reviewers requested changes",
                confidence=0.8,
            )

        # There's a conflict - need to resolve
        return self._resolve_conflict(reviews)

    def _resolve_conflict(
        self,
        reviews: List[Dict[str, Any]],
    ) -> ConflictResolution:
        """Resolve a conflict between reviewers.

        Args:
            reviews: Conflicting reviews

        Returns:
            ConflictResolution
        """
        # Calculate weighted scores
        weighted_scores: Dict[str, float] = {}
        total_weight = 0.0

        for review in reviews:
            agent_id = review.get("agent_id", "unknown")
            approved = review.get("approved", False)
            score = review.get("score", 5.0)
            has_security_findings = bool(review.get("security_findings", []))
            has_blocking_issues = bool(review.get("blocking_issues", []))

            # Get weight for this reviewer
            weight = self._get_reviewer_weight(agent_id, has_security_findings)
            total_weight += weight

            # Convert approval + score to a single metric
            if approved:
                effective_score = score * weight
            else:
                effective_score = (10 - score) * weight * -1  # Negative for rejection

            weighted_scores[agent_id] = {
                "score": effective_score,
                "weight": weight,
                "approved": approved,
                "has_blocking": has_blocking_issues,
                "has_security": has_security_findings,
            }

        # Calculate final weighted decision
        total_score = sum(ws["score"] for ws in weighted_scores.values())
        normalized_score = total_score / total_weight if total_weight > 0 else 0

        logger.debug(f"Weighted scores: {weighted_scores}, total: {normalized_score}")

        # Check for security override
        security_rejection = any(
            ws["has_security"] and not ws["approved"]
            for ws in weighted_scores.values()
        )

        if security_rejection:
            # Security always wins for rejection
            security_reviewer = next(
                agent_id
                for agent_id, ws in weighted_scores.items()
                if ws["has_security"] and not ws["approved"]
            )
            return ConflictResolution(
                resolved=True,
                final_decision="needs_changes",
                winning_reviewer=security_reviewer,
                reasoning="Security findings require resolution before approval",
                confidence=0.9,
            )

        # Use weighted score to determine outcome
        if normalized_score > 0:
            # Positive = leaning toward approval
            confidence = min(normalized_score / 10.0, 1.0)
            if confidence >= self.CONFIDENCE_THRESHOLD:
                winning = max(
                    weighted_scores.items(),
                    key=lambda x: x[1]["score"] if x[1]["approved"] else float("-inf"),
                )
                return ConflictResolution(
                    resolved=True,
                    final_decision="approved",
                    winning_reviewer=winning[0],
                    reasoning=f"Weighted resolution favors approval (score: {normalized_score:.2f})",
                    confidence=confidence,
                )
            else:
                # Not confident enough - escalate
                return ConflictResolution(
                    resolved=False,
                    final_decision="escalate",
                    reasoning=f"Marginal approval (score: {normalized_score:.2f}), confidence too low",
                    requires_human_input=True,
                    escalation_reason="Low confidence resolution requires human verification",
                    confidence=confidence,
                )
        else:
            # Negative = leaning toward rejection
            winning = max(
                weighted_scores.items(),
                key=lambda x: abs(x[1]["score"]) if not x[1]["approved"] else 0,
            )
            return ConflictResolution(
                resolved=True,
                final_decision="needs_changes",
                winning_reviewer=winning[0],
                reasoning=f"Weighted resolution favors changes (score: {normalized_score:.2f})",
                confidence=min(abs(normalized_score) / 10.0, 1.0),
            )

    def _get_reviewer_weight(
        self,
        agent_id: str,
        has_security_findings: bool,
    ) -> float:
        """Get the weight for a reviewer.

        Args:
            agent_id: Agent identifier
            has_security_findings: Whether the review has security findings

        Returns:
            Weight (0.0 - 1.0)
        """
        # Check for custom weight
        if agent_id in self.custom_weights:
            return self.custom_weights[agent_id]

        # Look up agent specialization
        try:
            agent = get_agent(agent_id)
            specialization = agent.review_specialization
            base_weight = agent.weight_in_conflicts
        except KeyError:
            specialization = None
            base_weight = 0.5

        # Security findings boost the weight of security reviewers
        if has_security_findings and specialization == "security":
            return min(base_weight * 1.2, 1.0)

        return base_weight

    def detect_conflicts(
        self,
        reviews: List[Dict[str, Any]],
    ) -> List[ReviewConflict]:
        """Detect conflicts between reviews.

        Args:
            reviews: List of review dictionaries

        Returns:
            List of detected conflicts
        """
        conflicts = []

        if len(reviews) < 2:
            return conflicts

        # Check for approval mismatch
        approvals = {r.get("agent_id", f"reviewer_{i}"): r.get("approved", False) for i, r in enumerate(reviews)}
        if len(set(approvals.values())) > 1:
            conflicts.append(
                ReviewConflict(
                    conflict_type=ConflictType.APPROVAL_MISMATCH,
                    reviewers=list(approvals.keys()),
                    positions={k: "approve" if v else "reject" for k, v in approvals.items()},
                )
            )

        # Check for score divergence
        scores = {r.get("agent_id", f"reviewer_{i}"): r.get("score", 5.0) for i, r in enumerate(reviews)}
        max_score = max(scores.values())
        min_score = min(scores.values())
        if max_score - min_score >= self.score_threshold:
            conflicts.append(
                ReviewConflict(
                    conflict_type=ConflictType.SCORE_DIVERGENCE,
                    reviewers=list(scores.keys()),
                    positions={k: f"score:{v}" for k, v in scores.items()},
                    details={"divergence": max_score - min_score},
                )
            )

        # Check for security vs quality conflict
        has_security_issues = any(bool(r.get("security_findings", [])) for r in reviews)
        all_approved = all(r.get("approved", False) for r in reviews)
        if has_security_issues and all_approved:
            # Security findings exist but everyone approved - potential issue
            security_reviews = [r for r in reviews if r.get("security_findings")]
            if security_reviews:
                conflicts.append(
                    ReviewConflict(
                        conflict_type=ConflictType.SECURITY_VS_QUALITY,
                        reviewers=[r.get("agent_id", "unknown") for r in security_reviews],
                        positions={
                            r.get("agent_id", "unknown"): "approved_with_security_findings"
                            for r in security_reviews
                        },
                    )
                )

        return conflicts


def create_resolver_for_agents(
    agent_ids: List[str],
) -> ConflictResolver:
    """Create a conflict resolver with weights based on agent registry.

    Args:
        agent_ids: List of reviewer agent IDs

    Returns:
        ConflictResolver configured with appropriate weights
    """
    custom_weights = {}

    for agent_id in agent_ids:
        try:
            agent = get_agent(agent_id)
            custom_weights[agent_id] = agent.weight_in_conflicts
        except KeyError:
            custom_weights[agent_id] = 0.5

    return ConflictResolver(custom_weights=custom_weights)
