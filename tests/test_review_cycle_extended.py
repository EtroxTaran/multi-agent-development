"""Extended unit tests for the review cycle module.

Tests cover additional scenarios beyond the basic tests in test_review_cycle.py:
- Parallel reviewer execution
- No reviewers configured
- Custom reviewers override
- Cycle log bounded growth
- Conflict decision escalation
- Single reviewer error handling
- Working agent failure handling
- Max iterations escalation
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.dispatch import DispatchResult, Task
from orchestrator.review.cycle import ReviewCycle, ReviewDecision, ReviewFeedback
from orchestrator.review.resolver import ResolutionResult


class TestParallelReviewerExecution:
    """Tests for parallel reviewer execution."""

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
    async def test_parallel_reviewer_execution(self, review_cycle, mock_dispatcher):
        """Test that reviewers run concurrently."""
        execution_order = []

        async def track_review(reviewer_id, *args, **kwargs):
            execution_order.append(f"start_{reviewer_id}")
            await asyncio.sleep(0.01)  # Simulate work
            execution_order.append(f"end_{reviewer_id}")
            return DispatchResult(
                task_id=f"review-{reviewer_id}",
                agent_id=reviewer_id,
                status="completed",
                output={"approved": True, "score": 8.0, "blocking_issues": []},
                cli_used="test",
            )

        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )

        mock_dispatcher.dispatch_reviewer = AsyncMock(side_effect=track_review)

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        await review_cycle.run(
            working_agent_id="A04",
            task=task,
            custom_reviewers=["A07", "A08"],
        )

        # Both reviewers should start before either ends (parallel execution)
        # Find indices of start and end events
        a07_start = execution_order.index("start_A07")
        a08_start = execution_order.index("start_A08")
        a07_end = execution_order.index("end_A07")
        a08_end = execution_order.index("end_A08")

        # Both should start before either ends (true parallelism)
        assert a07_start < a07_end
        assert a08_start < a08_end
        # Check that they overlap (both start before both end)
        assert max(a07_start, a08_start) < min(a07_end, a08_end)


class TestNoReviewersConfigured:
    """Tests for handling no reviewers."""

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
    async def test_no_reviewers_returns_error(self, review_cycle, mock_dispatcher):
        """Test error when no reviewers configured."""
        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        # Mock get_agent_reviewers to return empty list
        with patch("orchestrator.review.cycle.get_agent_reviewers", return_value=[]):
            result = await review_cycle.run(
                working_agent_id="A04",
                task=task,
                custom_reviewers=[],  # Empty custom reviewers
            )

        assert result.final_status == "error"
        assert "No reviewers" in result.escalation_reason


class TestCustomReviewersOverride:
    """Tests for custom reviewer override."""

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
    async def test_custom_reviewers_override(self, review_cycle, mock_dispatcher):
        """Test that custom_reviewers param overrides default."""
        called_reviewers = []

        async def track_reviewer(reviewer_id, *args, **kwargs):
            called_reviewers.append(reviewer_id)
            return DispatchResult(
                task_id=f"review-{reviewer_id}",
                agent_id=reviewer_id,
                status="completed",
                output={"approved": True, "score": 8.0, "blocking_issues": []},
                cli_used="test",
            )

        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )
        mock_dispatcher.dispatch_reviewer = AsyncMock(side_effect=track_reviewer)

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        # Use custom reviewers
        await review_cycle.run(
            working_agent_id="A04",
            task=task,
            custom_reviewers=["CUSTOM_1", "CUSTOM_2"],
        )

        # Only custom reviewers should be called
        assert set(called_reviewers) == {"CUSTOM_1", "CUSTOM_2"}


class TestCycleLogBounded:
    """Tests for cycle log size management."""

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

    def test_cycle_log_bounded_to_100(self, review_cycle):
        """Test that MAX_CYCLE_LOG_ENTRIES is enforced."""
        # Manually add many log entries
        for i in range(150):
            mock_iteration = MagicMock()
            mock_iteration.iteration_number = i
            mock_iteration.decision = ReviewDecision.NEEDS_CHANGES
            mock_iteration.reviews = []
            mock_iteration.timestamp = datetime.utcnow()

            review_cycle._log_iteration(mock_iteration)

        # Log should be bounded
        cycle_log = review_cycle.get_cycle_log()
        assert len(cycle_log) <= ReviewCycle.MAX_CYCLE_LOG_ENTRIES


class TestConflictDecisionEscalates:
    """Tests for conflict decision handling using ResolutionResult."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock dispatcher."""
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        dispatcher.dispatch_reviewer = AsyncMock()
        return dispatcher

    @pytest.fixture
    def review_cycle(self, mock_dispatcher, tmp_path):
        """Create a ReviewCycle instance with mocked resolver."""
        cycle = ReviewCycle(mock_dispatcher, tmp_path)
        return cycle

    @pytest.mark.asyncio
    async def test_conflict_decision_escalates(self, review_cycle, mock_dispatcher):
        """Test that high score divergence triggers escalation."""
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )

        # One approves with high score, one rejects with low score (divergence > 3.0)
        mock_dispatcher.dispatch_reviewer.side_effect = [
            DispatchResult(
                task_id="review-A07",
                agent_id="A07",
                status="completed",
                output={"approved": True, "score": 9.0, "blocking_issues": []},
                cli_used="cursor",
            ),
            DispatchResult(
                task_id="review-A08",
                agent_id="A08",
                status="completed",
                output={"approved": False, "score": 3.0, "blocking_issues": ["Major issue"]},
                cli_used="gemini",
            ),
        ]

        # Mock resolver to return escalation action
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = ResolutionResult(
            approved=False,
            final_score=6.0,
            decision_reason="High disagreement (Diff: 6.0). Cursor=9.0, Gemini=3.0",
            blocking_issues=[{"agent": "gemini", "issue": "Major issue"}],
            action="escalate",
        )
        review_cycle.conflict_resolver = mock_resolver

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        result = await review_cycle.run(
            working_agent_id="A04",
            task=task,
            custom_reviewers=["A07", "A08"],
        )

        assert result.final_status == "escalated"
        assert (
            "disagreement" in result.escalation_reason.lower()
            or "conflict" in result.escalation_reason.lower()
        )


class TestReviewerErrorContinues:
    """Tests for single reviewer error handling."""

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
    async def test_reviewer_error_continues(self, review_cycle, mock_dispatcher):
        """Test that single reviewer error doesn't halt the cycle."""
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )

        call_count = 0

        async def mixed_results(reviewer_id, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if reviewer_id == "A07":
                raise RuntimeError("Reviewer A07 crashed")
            return DispatchResult(
                task_id=f"review-{reviewer_id}",
                agent_id=reviewer_id,
                status="completed",
                output={"approved": True, "score": 8.0, "blocking_issues": []},
                cli_used="test",
            )

        mock_dispatcher.dispatch_reviewer = AsyncMock(side_effect=mixed_results)

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        result = await review_cycle.run(
            working_agent_id="A04",
            task=task,
            custom_reviewers=["A07", "A08"],
        )

        # Cycle should continue despite A07 error
        assert call_count >= 2  # Both reviewers were called
        # The result depends on how the cycle handles partial reviews
        # At minimum, it shouldn't crash


class TestWorkingAgentFailure:
    """Tests for working agent error handling."""

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
    async def test_working_agent_failure_returns_error(self, review_cycle, mock_dispatcher):
        """Test that working agent error returns error status."""
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="failed",
            output=None,  # No output on failure
            cli_used="claude",
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
            custom_reviewers=["A07", "A08"],
        )

        assert result.final_status == "error"
        assert "no output" in result.escalation_reason.lower()

    @pytest.mark.asyncio
    async def test_working_agent_exception_returns_error(self, review_cycle, mock_dispatcher):
        """Test that working agent exception returns error status."""
        mock_dispatcher.dispatch.side_effect = RuntimeError("Agent crashed")

        task = Task(
            id="task-1",
            title="Test Task",
            description="A test task",
            acceptance_criteria=["It works"],
        )

        result = await review_cycle.run(
            working_agent_id="A04",
            task=task,
            custom_reviewers=["A07", "A08"],
        )

        assert result.final_status == "error"
        assert "Working agent error" in result.escalation_reason


class TestMaxIterationsEscalates:
    """Tests for max iterations handling."""

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
    async def test_max_iterations_escalates(self, review_cycle, mock_dispatcher):
        """Test escalation after 3 iterations without approval."""
        mock_dispatcher.dispatch.return_value = DispatchResult(
            task_id="task-1",
            agent_id="A04",
            status="completed",
            output={},
            cli_used="claude",
        )

        # Reviewers always reject
        mock_dispatcher.dispatch_reviewer.return_value = DispatchResult(
            task_id="review-task",
            agent_id="A07",
            status="completed",
            output={
                "approved": False,
                "score": 5.0,
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
            max_iterations=3,
            custom_reviewers=["A07", "A08"],
        )

        assert result.final_status == "escalated"
        assert result.iteration_count == 3
        assert "Max iterations" in result.escalation_reason


class TestDetermineDecision:
    """Tests for _determine_decision logic."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock dispatcher."""
        return MagicMock()

    @pytest.fixture
    def review_cycle(self, mock_dispatcher, tmp_path):
        """Create a ReviewCycle instance."""
        return ReviewCycle(mock_dispatcher, tmp_path)

    def test_all_approved_returns_approved(self, review_cycle):
        """Test that all approvals return APPROVED."""
        reviews = [
            ReviewFeedback(reviewer_id="A07", cli_used="cursor", approved=True, score=8.0),
            ReviewFeedback(reviewer_id="A08", cli_used="gemini", approved=True, score=7.5),
        ]

        decision, resolution = review_cycle._determine_decision(reviews, approval_score=7.0)

        assert decision == ReviewDecision.APPROVED

    def test_all_rejected_returns_needs_changes(self, review_cycle):
        """Test that all rejections return NEEDS_CHANGES."""
        reviews = [
            ReviewFeedback(reviewer_id="A07", cli_used="cursor", approved=False, score=4.0),
            ReviewFeedback(reviewer_id="A08", cli_used="gemini", approved=False, score=5.0),
        ]

        decision, resolution = review_cycle._determine_decision(reviews, approval_score=7.0)

        assert decision == ReviewDecision.NEEDS_CHANGES

    def test_score_below_threshold_not_approved(self, review_cycle):
        """Test that approval requires meeting score threshold."""
        reviews = [
            ReviewFeedback(
                reviewer_id="A07", cli_used="cursor", approved=True, score=6.0
            ),  # Below threshold
            ReviewFeedback(
                reviewer_id="A08", cli_used="gemini", approved=True, score=6.5
            ),  # Below threshold
        ]

        decision, resolution = review_cycle._determine_decision(reviews, approval_score=7.0)

        # Even though approved=True, score < threshold means not approved
        assert decision != ReviewDecision.APPROVED


class TestReviewFeedbackFromDispatchResult:
    """Tests for ReviewFeedback.from_dispatch_result."""

    def test_handles_missing_fields(self):
        """Test that missing optional fields get defaults."""
        result = DispatchResult(
            task_id="task-1",
            agent_id="A07",
            status="completed",
            output={"approved": True, "score": 7.0},  # Minimal output
            cli_used="cursor",
        )

        feedback = ReviewFeedback.from_dispatch_result(result)

        assert feedback.approved is True
        assert feedback.score == 7.0
        assert feedback.blocking_issues == []
        assert feedback.suggestions == []
        assert feedback.security_findings == []
