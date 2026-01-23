"""Tests for the centralized approval engine."""


from orchestrator.utils.approval import (
    AgentFeedback,
    ApprovalConfig,
    ApprovalEngine,
    ApprovalPolicy,
    ApprovalResult,
    ApprovalStatus,
)


class TestAgentFeedback:
    """Tests for AgentFeedback class."""

    def test_from_cursor_feedback_approve(self):
        """Test creating feedback from Cursor approval."""
        feedback = {
            "overall_assessment": "approve",
            "score": 8,
            "concerns": [],
            "blocking_issues": [],
        }

        result = AgentFeedback.from_cursor_feedback(feedback)

        assert result.agent == "cursor"
        assert result.assessment == "approve"
        assert result.score == 8.0
        assert len(result.blocking_issues) == 0

    def test_from_cursor_feedback_with_high_severity_concern(self):
        """Test that high severity concerns become blocking issues."""
        feedback = {
            "overall_assessment": "needs_changes",
            "score": 5,
            "concerns": [
                {"severity": "high", "area": "security", "description": "SQL injection risk"}
            ],
            "blocking_issues": [],
        }

        result = AgentFeedback.from_cursor_feedback(feedback)

        assert len(result.blocking_issues) == 1
        assert result.blocking_issues[0]["severity"] == "high"

    def test_from_cursor_feedback_none(self):
        """Test handling None feedback."""
        result = AgentFeedback.from_cursor_feedback(None)

        assert result.agent == "cursor"
        assert result.assessment == "unknown"
        assert result.score == 0
        assert result.error is not None

    def test_from_gemini_feedback_approve(self):
        """Test creating feedback from Gemini approval."""
        feedback = {
            "overall_assessment": "approve",
            "score": 9,
            "architecture_review": {"concerns": []},
            "blocking_issues": [],
        }

        result = AgentFeedback.from_gemini_feedback(feedback)

        assert result.agent == "gemini"
        assert result.assessment == "approve"
        assert result.score == 9.0

    def test_from_review_cursor(self):
        """Test creating feedback from cursor review."""
        review = {
            "approved": True,
            "overall_code_quality": 8,
            "files_reviewed": [],
            "blocking_issues": [],
        }

        result = AgentFeedback.from_review(review, "cursor")

        assert result.agent == "cursor"
        assert result.assessment == "approve"
        assert result.score == 8.0

    def test_from_review_gemini(self):
        """Test creating feedback from gemini review."""
        review = {
            "approved": True,
            "architecture_assessment": {"modularity_score": 8},
            "blocking_issues": [],
        }

        result = AgentFeedback.from_review(review, "gemini")

        assert result.agent == "gemini"
        assert result.assessment == "approve"
        assert result.score == 8.0


class TestApprovalEngine:
    """Tests for ApprovalEngine."""

    def test_init_default_configs(self):
        """Test initialization with default configs."""
        engine = ApprovalEngine()

        assert 2 in engine.configs
        assert 4 in engine.configs
        assert engine.configs[2].policy == ApprovalPolicy.NO_BLOCKERS
        assert engine.configs[4].policy == ApprovalPolicy.ALL_MUST_APPROVE

    def test_init_custom_configs(self):
        """Test initialization with custom configs."""
        custom = {2: ApprovalConfig(policy=ApprovalPolicy.MAJORITY)}
        engine = ApprovalEngine(custom_configs=custom)

        assert engine.configs[2].policy == ApprovalPolicy.MAJORITY

    def test_evaluate_both_approve(self):
        """Test evaluation when both agents approve."""
        engine = ApprovalEngine()
        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="approve", score=9)

        result = engine.evaluate(cursor, gemini, phase=2)

        assert result.approved
        assert result.cursor_approved
        assert result.gemini_approved
        assert result.status == ApprovalStatus.APPROVED

    def test_evaluate_one_rejects(self):
        """Test evaluation when one agent rejects."""
        engine = ApprovalEngine()
        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="reject", score=4)

        result = engine.evaluate(cursor, gemini, phase=4)

        assert not result.approved
        assert result.cursor_approved
        assert not result.gemini_approved
        assert result.status == ApprovalStatus.NEEDS_CHANGES

    def test_evaluate_with_blocking_issues(self):
        """Test evaluation with blocking issues."""
        engine = ApprovalEngine()
        cursor = AgentFeedback(
            agent="cursor",
            assessment="reject",
            score=4,
            blocking_issues=[{"description": "Critical bug"}],
        )
        gemini = AgentFeedback(agent="gemini", assessment="approve", score=8)

        result = engine.evaluate(cursor, gemini, phase=2)

        assert not result.approved
        assert len(result.blocking_issues) == 1
        assert result.status == ApprovalStatus.REJECTED

    def test_evaluate_no_blockers_policy(self):
        """Test NO_BLOCKERS policy."""
        config = ApprovalConfig(
            policy=ApprovalPolicy.NO_BLOCKERS,
            minimum_score=6.0,
        )
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="needs_changes", score=7)
        gemini = AgentFeedback(agent="gemini", assessment="needs_changes", score=8)

        result = engine.evaluate(cursor, gemini, phase=2, config=config)

        # Should approve because no blocking issues and score >= 6
        assert result.approved
        assert result.policy_used == ApprovalPolicy.NO_BLOCKERS

    def test_evaluate_no_blockers_below_threshold(self):
        """Test NO_BLOCKERS policy with score below threshold."""
        config = ApprovalConfig(
            policy=ApprovalPolicy.NO_BLOCKERS,
            minimum_score=8.0,
        )
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="approve", score=5)
        gemini = AgentFeedback(agent="gemini", assessment="approve", score=6)

        result = engine.evaluate(cursor, gemini, phase=2, config=config)

        # Should reject because average score 5.5 < 8.0
        assert not result.approved
        assert "below" in result.reasoning.lower()

    def test_evaluate_all_must_approve_policy(self):
        """Test ALL_MUST_APPROVE policy."""
        config = ApprovalConfig(policy=ApprovalPolicy.ALL_MUST_APPROVE)
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="reject", score=7)

        result = engine.evaluate(cursor, gemini, phase=4, config=config)

        assert not result.approved
        assert "Gemini did not approve" in result.reasoning

    def test_evaluate_majority_policy(self):
        """Test MAJORITY policy."""
        config = ApprovalConfig(policy=ApprovalPolicy.MAJORITY)
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="reject", score=5)

        result = engine.evaluate(cursor, gemini, phase=2, config=config)

        # Should approve because at least one approved
        assert result.approved
        assert "majority" in result.reasoning.lower()

    def test_evaluate_weighted_score_policy(self):
        """Test WEIGHTED_SCORE policy."""
        config = ApprovalConfig(
            policy=ApprovalPolicy.WEIGHTED_SCORE,
            minimum_score=7.0,
        )
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="approve", score=6)

        result = engine.evaluate(cursor, gemini, phase=2, config=config)

        # Weighted score = 8*0.5 + 6*0.5 = 7.0 (meets threshold)
        assert result.approved

    def test_evaluate_single_agent_available(self):
        """Test evaluation when only one agent responds."""
        config = ApprovalConfig(
            policy=ApprovalPolicy.ALL_MUST_APPROVE,
            allow_single_agent=True,
        )
        engine = ApprovalEngine()

        cursor = AgentFeedback(agent="cursor", assessment="approve", score=8)
        gemini = AgentFeedback(agent="gemini", assessment="unknown", score=0, error="unavailable")

        result = engine.evaluate(cursor, gemini, phase=4, config=config)

        # Should approve because single agent allowed
        assert result.approved
        assert "Only Cursor responded" in result.reasoning

    def test_evaluate_for_validation(self):
        """Test convenience method for Phase 2."""
        engine = ApprovalEngine()

        cursor_feedback = {
            "overall_assessment": "approve",
            "score": 8,
            "concerns": [],
        }
        gemini_feedback = {
            "overall_assessment": "approve",
            "score": 9,
            "architecture_review": {"concerns": []},
        }

        result = engine.evaluate_for_validation(cursor_feedback, gemini_feedback)

        assert result.approved
        assert result.policy_used == ApprovalPolicy.NO_BLOCKERS

    def test_evaluate_for_verification(self):
        """Test convenience method for Phase 4."""
        engine = ApprovalEngine()

        cursor_review = {
            "approved": True,
            "overall_code_quality": 8,
            "files_reviewed": [],
        }
        gemini_review = {
            "approved": True,
            "architecture_assessment": {"modularity_score": 8},
        }

        result = engine.evaluate_for_verification(cursor_review, gemini_review)

        assert result.approved
        assert result.policy_used == ApprovalPolicy.ALL_MUST_APPROVE


class TestApprovalResult:
    """Tests for ApprovalResult."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = ApprovalResult(
            status=ApprovalStatus.APPROVED,
            approved=True,
            cursor_approved=True,
            gemini_approved=True,
            combined_score=8.5,
            reasoning="Both approved",
            policy_used=ApprovalPolicy.NO_BLOCKERS,
        )

        data = result.to_dict()

        assert data["status"] == "approved"
        assert data["approved"] is True
        assert data["combined_score"] == 8.5
        assert data["policy_used"] == "no_blockers"


class TestApprovalConfig:
    """Tests for ApprovalConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = ApprovalConfig()

        assert config.policy == ApprovalPolicy.NO_BLOCKERS
        assert config.minimum_score == 6.0
        assert config.require_both_agents is True
        assert config.allow_single_agent is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ApprovalConfig(
            policy=ApprovalPolicy.ALL_MUST_APPROVE,
            minimum_score=8.0,
            require_both_agents=True,
            allow_single_agent=False,
        )

        assert config.policy == ApprovalPolicy.ALL_MUST_APPROVE
        assert config.minimum_score == 8.0
        assert config.allow_single_agent is False
