"""Centralized approval policy engine for the orchestration workflow.

Provides configurable approval policies for validation and verification phases,
replacing duplicated logic in phase2 and phase4.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ApprovalPolicy(str, Enum):
    """Approval policy types."""

    ALL_MUST_APPROVE = "all_must_approve"  # Both agents must approve
    NO_BLOCKERS = "no_blockers"  # Approve if no blocking issues
    WEIGHTED_SCORE = "weighted_score"  # Approve based on weighted scores
    MAJORITY = "majority"  # At least one must approve


class ApprovalStatus(str, Enum):
    """Status of an approval decision."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    PENDING = "pending"


@dataclass
class ApprovalConfig:
    """Configuration for approval evaluation."""

    policy: ApprovalPolicy = ApprovalPolicy.NO_BLOCKERS
    minimum_score: float = 6.0
    require_both_agents: bool = True
    allow_single_agent: bool = True  # Allow approval if only one agent responds
    blocking_severity_threshold: str = "high"  # high, medium, low


@dataclass
class AgentFeedback:
    """Normalized feedback from an agent."""

    agent: str
    assessment: str  # approve, needs_changes, reject
    score: float
    blocking_issues: list[dict] = field(default_factory=list)
    concerns: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    @classmethod
    def from_cursor_feedback(cls, feedback: Optional[dict]) -> "AgentFeedback":
        """Create from Cursor feedback format."""
        if not feedback:
            return cls(agent="cursor", assessment="unknown", score=0, error="No feedback")

        blocking = []
        concerns_list = feedback.get("concerns", [])
        for concern in concerns_list:
            if isinstance(concern, dict):
                if concern.get("severity") == "high":
                    blocking.append(concern)

        return cls(
            agent="cursor",
            assessment=feedback.get("overall_assessment", "unknown"),
            score=float(feedback.get("score", 0)),
            blocking_issues=feedback.get("blocking_issues", []) + blocking,
            concerns=concerns_list,
            error=feedback.get("error"),
        )

    @classmethod
    def from_gemini_feedback(cls, feedback: Optional[dict]) -> "AgentFeedback":
        """Create from Gemini feedback format."""
        if not feedback:
            return cls(agent="gemini", assessment="unknown", score=0, error="No feedback")

        blocking = feedback.get("blocking_issues", [])
        arch_review = feedback.get("architecture_review", {})

        return cls(
            agent="gemini",
            assessment=feedback.get("overall_assessment", "unknown"),
            score=float(feedback.get("score", 0)),
            blocking_issues=blocking,
            concerns=arch_review.get("concerns", []),
            error=feedback.get("error"),
        )

    @classmethod
    def from_review(cls, review: Optional[dict], agent: str) -> "AgentFeedback":
        """Create from verification review format."""
        if not review:
            return cls(agent=agent, assessment="unknown", score=0, error="No review")

        blocking = []
        if agent == "cursor":
            for file_review in review.get("files_reviewed", []):
                for issue in file_review.get("issues", []):
                    if issue.get("severity") == "error":
                        blocking.append(
                            {
                                "file": file_review.get("file"),
                                "description": issue.get("description"),
                                "type": issue.get("type"),
                            }
                        )

        # Check approved field for review phase
        assessment = "approve" if review.get("approved", False) else "needs_changes"
        if review.get("overall_assessment"):
            assessment = review.get("overall_assessment")

        score = review.get("overall_code_quality", 0) or review.get("score", 0)
        if agent == "gemini":
            arch = review.get("architecture_assessment", {})
            score = arch.get("modularity_score", 0) or review.get("score", 0)

        return cls(
            agent=agent,
            assessment=assessment,
            score=float(score),
            blocking_issues=blocking + review.get("blocking_issues", []),
            concerns=review.get("concerns", []),
            error=review.get("error"),
        )


@dataclass
class ApprovalResult:
    """Result of an approval evaluation."""

    status: ApprovalStatus
    approved: bool
    cursor_approved: bool
    gemini_approved: bool
    combined_score: float
    blocking_issues: list[dict] = field(default_factory=list)
    reasoning: str = ""
    policy_used: ApprovalPolicy = ApprovalPolicy.NO_BLOCKERS

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "approved": self.approved,
            "cursor_approved": self.cursor_approved,
            "gemini_approved": self.gemini_approved,
            "combined_score": self.combined_score,
            "blocking_issues": self.blocking_issues,
            "reasoning": self.reasoning,
            "policy_used": self.policy_used.value,
        }


class ApprovalEngine:
    """Centralized engine for evaluating approvals.

    Replaces duplicated _check_approval() methods in phase2 and phase4.
    """

    # Default configurations per phase
    PHASE_CONFIGS = {
        2: ApprovalConfig(
            policy=ApprovalPolicy.NO_BLOCKERS,
            minimum_score=6.0,
            require_both_agents=False,
        ),
        4: ApprovalConfig(
            policy=ApprovalPolicy.ALL_MUST_APPROVE,
            minimum_score=7.0,
            require_both_agents=True,
        ),
    }

    # Agent expertise weights for different areas
    EXPERTISE_WEIGHTS = {
        "security": {"cursor": 0.8, "gemini": 0.2},
        "architecture": {"cursor": 0.3, "gemini": 0.7},
        "code_quality": {"cursor": 0.7, "gemini": 0.3},
        "scalability": {"cursor": 0.2, "gemini": 0.8},
        "maintainability": {"cursor": 0.6, "gemini": 0.4},
        "testing": {"cursor": 0.7, "gemini": 0.3},
        "default": {"cursor": 0.5, "gemini": 0.5},
    }

    def __init__(self, custom_configs: Optional[dict[int, ApprovalConfig]] = None):
        """Initialize approval engine.

        Args:
            custom_configs: Optional custom configurations per phase
        """
        self.configs = self.PHASE_CONFIGS.copy()
        if custom_configs:
            self.configs.update(custom_configs)

    def get_config(self, phase: int) -> ApprovalConfig:
        """Get configuration for a phase.

        Args:
            phase: Phase number

        Returns:
            ApprovalConfig for the phase
        """
        return self.configs.get(phase, ApprovalConfig())

    def evaluate(
        self,
        cursor_feedback: AgentFeedback,
        gemini_feedback: AgentFeedback,
        phase: int,
        config: Optional[ApprovalConfig] = None,
    ) -> ApprovalResult:
        """Evaluate approval based on agent feedback.

        Args:
            cursor_feedback: Feedback from Cursor agent
            gemini_feedback: Feedback from Gemini agent
            phase: Current phase number
            config: Optional custom config (overrides phase default)

        Returns:
            ApprovalResult with evaluation details
        """
        cfg = config or self.get_config(phase)

        # Determine individual approvals
        cursor_approved = self._is_approved(cursor_feedback)
        gemini_approved = self._is_approved(gemini_feedback)

        # Collect all blocking issues
        all_blocking = []
        all_blocking.extend(cursor_feedback.blocking_issues)
        all_blocking.extend(gemini_feedback.blocking_issues)

        # Calculate combined score
        combined_score = self._calculate_combined_score(cursor_feedback, gemini_feedback)

        # Evaluate based on policy
        if cfg.policy == ApprovalPolicy.ALL_MUST_APPROVE:
            approved, reasoning = self._eval_all_must_approve(
                cursor_approved, gemini_approved, cursor_feedback, gemini_feedback, cfg
            )
        elif cfg.policy == ApprovalPolicy.NO_BLOCKERS:
            approved, reasoning = self._eval_no_blockers(all_blocking, combined_score, cfg)
        elif cfg.policy == ApprovalPolicy.WEIGHTED_SCORE:
            approved, reasoning = self._eval_weighted_score(cursor_feedback, gemini_feedback, cfg)
        elif cfg.policy == ApprovalPolicy.MAJORITY:
            approved, reasoning = self._eval_majority(cursor_approved, gemini_approved, cfg)
        else:
            approved = cursor_approved and gemini_approved
            reasoning = "Default policy: both must approve"

        # Determine status
        if approved:
            status = ApprovalStatus.APPROVED
        elif all_blocking:
            status = ApprovalStatus.REJECTED
        else:
            status = ApprovalStatus.NEEDS_CHANGES

        return ApprovalResult(
            status=status,
            approved=approved,
            cursor_approved=cursor_approved,
            gemini_approved=gemini_approved,
            combined_score=combined_score,
            blocking_issues=all_blocking,
            reasoning=reasoning,
            policy_used=cfg.policy,
        )

    def _is_approved(self, feedback: AgentFeedback) -> bool:
        """Check if an agent's feedback indicates approval."""
        if feedback.error:
            return False
        return feedback.assessment.lower() in ("approve", "approved", "pass")

    def _calculate_combined_score(
        self,
        cursor_feedback: AgentFeedback,
        gemini_feedback: AgentFeedback,
    ) -> float:
        """Calculate weighted combined score from both agents."""
        cursor_score = cursor_feedback.score if not cursor_feedback.error else 0
        gemini_score = gemini_feedback.score if not gemini_feedback.error else 0

        # If only one agent provided feedback, use that score
        if cursor_feedback.error and not gemini_feedback.error:
            return gemini_score
        if gemini_feedback.error and not cursor_feedback.error:
            return cursor_score

        # Average the scores (equal weight by default)
        return (cursor_score + gemini_score) / 2

    def _eval_all_must_approve(
        self,
        cursor_approved: bool,
        gemini_approved: bool,
        cursor_feedback: AgentFeedback,
        gemini_feedback: AgentFeedback,
        config: ApprovalConfig,
    ) -> tuple[bool, str]:
        """Evaluate using ALL_MUST_APPROVE policy."""
        # Handle single agent scenarios
        if cursor_feedback.error and not gemini_feedback.error:
            if config.allow_single_agent:
                return gemini_approved, "Only Gemini responded; approved by Gemini"
            return False, "Cursor unavailable; both agents required"

        if gemini_feedback.error and not cursor_feedback.error:
            if config.allow_single_agent:
                return cursor_approved, "Only Cursor responded; approved by Cursor"
            return False, "Gemini unavailable; both agents required"

        if cursor_approved and gemini_approved:
            return True, "Both agents approved"

        reasons = []
        if not cursor_approved:
            reasons.append("Cursor did not approve")
        if not gemini_approved:
            reasons.append("Gemini did not approve")

        return False, "; ".join(reasons)

    def _eval_no_blockers(
        self,
        blocking_issues: list[dict],
        combined_score: float,
        config: ApprovalConfig,
    ) -> tuple[bool, str]:
        """Evaluate using NO_BLOCKERS policy."""
        if blocking_issues:
            return False, f"Has {len(blocking_issues)} blocking issue(s)"

        if combined_score < config.minimum_score:
            return False, f"Score {combined_score:.1f} below minimum {config.minimum_score}"

        return True, f"No blockers; score {combined_score:.1f} meets threshold"

    def _eval_weighted_score(
        self,
        cursor_feedback: AgentFeedback,
        gemini_feedback: AgentFeedback,
        config: ApprovalConfig,
    ) -> tuple[bool, str]:
        """Evaluate using WEIGHTED_SCORE policy."""
        weights = self.EXPERTISE_WEIGHTS["default"]

        cursor_score = cursor_feedback.score if not cursor_feedback.error else 0
        gemini_score = gemini_feedback.score if not gemini_feedback.error else 0

        weighted_score = cursor_score * weights["cursor"] + gemini_score * weights["gemini"]

        if weighted_score >= config.minimum_score:
            return (
                True,
                f"Weighted score {weighted_score:.1f} meets threshold {config.minimum_score}",
            )

        return False, f"Weighted score {weighted_score:.1f} below threshold {config.minimum_score}"

    def _eval_majority(
        self,
        cursor_approved: bool,
        gemini_approved: bool,
        config: ApprovalConfig,
    ) -> tuple[bool, str]:
        """Evaluate using MAJORITY policy."""
        approvals = sum([cursor_approved, gemini_approved])

        if approvals >= 1:
            return True, f"{approvals}/2 agents approved (majority)"

        return False, "No agents approved"

    def evaluate_for_validation(
        self,
        cursor_feedback: Optional[dict],
        gemini_feedback: Optional[dict],
        config: Optional[ApprovalConfig] = None,
    ) -> ApprovalResult:
        """Convenience method for Phase 2 validation.

        Args:
            cursor_feedback: Raw Cursor feedback dict
            gemini_feedback: Raw Gemini feedback dict
            config: Optional custom config

        Returns:
            ApprovalResult
        """
        cursor = AgentFeedback.from_cursor_feedback(cursor_feedback)
        gemini = AgentFeedback.from_gemini_feedback(gemini_feedback)
        return self.evaluate(cursor, gemini, phase=2, config=config)

    def evaluate_for_verification(
        self,
        cursor_review: Optional[dict],
        gemini_review: Optional[dict],
        config: Optional[ApprovalConfig] = None,
    ) -> ApprovalResult:
        """Convenience method for Phase 4 verification.

        Args:
            cursor_review: Raw Cursor review dict
            gemini_review: Raw Gemini review dict
            config: Optional custom config

        Returns:
            ApprovalResult
        """
        cursor = AgentFeedback.from_review(cursor_review, "cursor")
        gemini = AgentFeedback.from_review(gemini_review, "gemini")
        return self.evaluate(cursor, gemini, phase=4, config=config)
