"""Unit tests for the review cycle module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from pathlib import Path

from orchestrator.review.cycle import (
    ReviewCycle,
    ReviewCycleResult,
    ReviewDecision,
    ReviewFeedback,
    ReviewIteration,
)
from orchestrator.review.resolver import (
    ConflictResolver,
    ConflictResolution,
    ReviewConflict,
    ConflictType,
)
from orchestrator.dispatch import DispatchResult, Task


class TestReviewFeedback:
    """Tests for ReviewFeedback class."""

    def test_from_dispatch_result(self):
        """Test creating feedback from dispatch result."""
        result = DispatchResult(
            task_id="task-1",
            agent_id="A07",
            status="completed",
            output={
                "approved": True,
                "score": 8.5,
                "blocking_issues": [],
                "suggestions": ["Consider adding more tests"],
                "security_findings": [],
            },
            cli_used="cursor",
        )

        feedback = ReviewFeedback.from_dispatch_result(result)

        assert feedback.reviewer_id == "A07"
        assert feedback.cli_used == "cursor"
        assert feedback.approved is True
        assert feedback.score == 8.5
        assert len(feedback.suggestions) == 1

    def test_from_dispatch_result_with_issues(self):
        """Test creating feedback with blocking issues."""
        result = DispatchResult(
            task_id="task-1",
            agent_id="A08",
            status="completed",
            output={
                "approved": False,
                "score": 5.0,
                "blocking_issues": ["Missing error handling", "No input validation"],
                "suggestions": [],
            },
            cli_used="gemini",
        )

        feedback = ReviewFeedback.from_dispatch_result(result)

        assert feedback.approved is False
        assert feedback.score == 5.0
        assert len(feedback.blocking_issues) == 2


class TestReviewIteration:
    """Tests for ReviewIteration class."""

    def test_all_approved(self):
        """Test all_approved property."""
        reviews = [
            ReviewFeedback(reviewer_id="A07", cli_used="cursor", approved=True, score=8.0),
            ReviewFeedback(reviewer_id="A08", cli_used="gemini", approved=True, score=7.5),
        ]

        iteration = ReviewIteration(
            iteration_number=1,
            work_result=MagicMock(),
            reviews=reviews,
            decision=ReviewDecision.APPROVED,
        )

        assert iteration.all_approved is True
        assert iteration.any_approved is True

    def test_none_approved(self):
        """Test when no reviewers approve."""
        reviews = [
            ReviewFeedback(reviewer_id="A07", cli_used="cursor", approved=False, score=4.0),
            ReviewFeedback(reviewer_id="A08", cli_used="gemini", approved=False, score=5.0),
        ]

        iteration = ReviewIteration(
            iteration_number=1,
            work_result=MagicMock(),
            reviews=reviews,
            decision=ReviewDecision.NEEDS_CHANGES,
        )

        assert iteration.all_approved is False
        assert iteration.any_approved is False

    def test_blocking_issues_aggregation(self):
        """Test that blocking issues are aggregated from all reviewers."""
        reviews = [
            ReviewFeedback(
                reviewer_id="A07",
                cli_used="cursor",
                approved=False,
                score=4.0,
                blocking_issues=["SQL injection vulnerability"],
            ),
            ReviewFeedback(
                reviewer_id="A08",
                cli_used="gemini",
                approved=False,
                score=5.0,
                blocking_issues=["Missing tests", "Poor documentation"],
            ),
        ]

        iteration = ReviewIteration(
            iteration_number=1,
            work_result=MagicMock(),
            reviews=reviews,
            decision=ReviewDecision.NEEDS_CHANGES,
        )

        assert len(iteration.blocking_issues) == 3

    def test_get_feedback_for_agent(self):
        """Test formatting feedback for the working agent."""
        reviews = [
            ReviewFeedback(
                reviewer_id="A07",
                cli_used="cursor",
                approved=False,
                score=4.0,
                blocking_issues=["Security issue"],
                suggestions=["Use parameterized queries"],
            ),
            ReviewFeedback(
                reviewer_id="A08",
                cli_used="gemini",
                approved=True,
                score=7.0,
            ),
        ]

        iteration = ReviewIteration(
            iteration_number=1,
            work_result=MagicMock(),
            reviews=reviews,
            decision=ReviewDecision.NEEDS_CHANGES,
        )

        feedback = iteration.get_feedback_for_agent()

        # Only A07 should be in feedback (the one that rejected)
        assert len(feedback) == 1
        assert feedback[0]["from_reviewer"] == "A07"
        assert "Security issue" in feedback[0]["issues"]


class TestReviewCycleResult:
    """Tests for ReviewCycleResult class."""

    def test_was_approved(self):
        """Test was_approved property."""
        result = ReviewCycleResult(
            task_id="task-1",
            working_agent_id="A04",
            final_status="approved",
            iterations=[],
        )

        assert result.was_approved is True

    def test_required_escalation(self):
        """Test required_escalation property."""
        result = ReviewCycleResult(
            task_id="task-1",
            working_agent_id="A04",
            final_status="escalated",
            iterations=[],
            escalation_reason="Max iterations exceeded",
        )

        assert result.required_escalation is True

    def test_iteration_count(self):
        """Test iteration counting."""
        result = ReviewCycleResult(
            task_id="task-1",
            working_agent_id="A04",
            final_status="approved",
            iterations=[MagicMock(), MagicMock(), MagicMock()],
        )

        assert result.iteration_count == 3


class TestConflictResolver:
    """Tests for ConflictResolver class."""

    def test_all_approved_no_conflict(self):
        """Test resolution when all reviewers approve."""
        resolver = ConflictResolver()

        reviews = [
            {"agent_id": "A07", "approved": True, "score": 8.0},
            {"agent_id": "A08", "approved": True, "score": 7.5},
        ]

        resolution = resolver.resolve(reviews)

        assert resolution.resolved is True
        assert resolution.final_decision == "approved"

    def test_all_rejected_no_conflict(self):
        """Test resolution when all reviewers reject."""
        resolver = ConflictResolver()

        reviews = [
            {"agent_id": "A07", "approved": False, "score": 4.0},
            {"agent_id": "A08", "approved": False, "score": 5.0},
        ]

        resolution = resolver.resolve(reviews)

        assert resolution.resolved is True
        assert resolution.final_decision == "needs_changes"

    def test_conflict_with_security_priority(self):
        """Test that security issues take priority in conflicts."""
        resolver = ConflictResolver()

        reviews = [
            {
                "agent_id": "A07",
                "approved": False,
                "score": 4.0,
                "security_findings": [{"severity": "high", "description": "SQL injection"}],
                "blocking_issues": ["SQL injection"],
            },
            {"agent_id": "A08", "approved": True, "score": 8.0, "blocking_issues": []},
        ]

        resolution = resolver.resolve(reviews)

        # Security rejection should win
        assert resolution.final_decision == "needs_changes"
        assert resolution.winning_reviewer == "A07"

    def test_detect_approval_mismatch(self):
        """Test detection of approval mismatch conflict."""
        resolver = ConflictResolver()

        reviews = [
            {"agent_id": "A07", "approved": True, "score": 7.5},
            {"agent_id": "A08", "approved": False, "score": 5.5},
        ]

        conflicts = resolver.detect_conflicts(reviews)

        # May detect both approval mismatch AND score divergence (2.0 difference)
        assert len(conflicts) >= 1
        assert any(c.conflict_type == ConflictType.APPROVAL_MISMATCH for c in conflicts)

    def test_detect_score_divergence(self):
        """Test detection of score divergence conflict."""
        resolver = ConflictResolver(score_threshold=2.0)

        reviews = [
            {"agent_id": "A07", "approved": True, "score": 9.0},
            {"agent_id": "A08", "approved": True, "score": 5.0},
        ]

        conflicts = resolver.detect_conflicts(reviews)

        assert any(c.conflict_type == ConflictType.SCORE_DIVERGENCE for c in conflicts)


class TestReviewCycle:
    """Tests for ReviewCycle class."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock dispatcher."""
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        dispatcher.dispatch_reviewer = AsyncMock()
        return dispatcher

    @pytest.fixture
    def review_cycle(self, mock_dispatcher, tmp_path):
        """Create a ReviewCycle instance."""
        return ReviewCycle(mock_dispatcher, tmp_path)

    @pytest.mark.asyncio
    async def test_run_approved_first_try(self, review_cycle, mock_dispatcher):
        """Test successful approval on first iteration."""
        # Setup mock for working agent
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={"files_created": ["src/main.py"]},
            cli_used="claude",
        )

        # Setup mock for reviewers (both approve)
        mock_dispatcher.dispatch_reviewer.side_effect = [
            DispatchResult(
                task_id="review-task-1-A07",
                agent_id="A07",
                status="completed",
                output={"approved": True, "score": 8.0, "blocking_issues": []},
                cli_used="cursor",
            ),
            DispatchResult(
                task_id="review-task-1-A08",
                agent_id="A08",
                status="completed",
                output={"approved": True, "score": 7.5, "blocking_issues": []},
                cli_used="gemini",
            ),
        ]

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        result = await review_cycle.run(
            working_agent_id="A04",
            task=task,
            max_iterations=3,
            custom_reviewers=["A07", "A08"],
        )

        assert result.was_approved is True
        assert result.iteration_count == 1

    @pytest.mark.asyncio
    async def test_run_escalates_after_max_iterations(self, review_cycle, mock_dispatcher):
        """Test escalation after max iterations."""
        # Setup mock for working agent
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )

        # Setup mock for reviewers (always reject)
        mock_dispatcher.dispatch_reviewer.return_value = DispatchResult(
            task_id="review-task-1-A07",
            agent_id="A07",
            status="completed",
            output={
                "approved": False,
                "score": 4.0,
                "blocking_issues": ["Needs improvement"],
            },
            cli_used="cursor",
        )

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        result = await review_cycle.run(
            working_agent_id="A04",
            task=task,
            max_iterations=2,
            custom_reviewers=["A07", "A08"],
        )

        assert result.required_escalation is True
        assert result.iteration_count == 2
        assert "Max iterations" in result.escalation_reason
