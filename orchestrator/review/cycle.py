"""
Review cycle implementation for iterative review-optimize-review workflow.

This module implements the 4-eyes protocol where every agent's work is reviewed
by 2+ different CLI/model combinations. The cycle continues until both reviewers
approve or max iterations are exceeded.

Flow:
    1. EXECUTE: Agent performs task
    2. REVIEW (PARALLEL): 2 reviewers assess work
    3. DECISION: Both approve → DONE, Either rejects → OPTIMIZE
    4. OPTIMIZE: Original agent fixes issues with feedback
    5. REPEAT from step 2 (or ESCALATE if max iterations)

Usage:
    from orchestrator.review import ReviewCycle

    cycle = ReviewCycle(dispatcher, project_dir)
    result = await cycle.run(
        working_agent_id="A04",
        task=task,
        max_iterations=3,
    )
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.dispatch import AgentDispatcher, DispatchResult, Task
from orchestrator.registry import get_agent, get_agent_reviewers, AgentConfig
from orchestrator.review.resolver import ConflictResolver, ConflictResolution

logger = logging.getLogger(__name__)


class ReviewDecision(Enum):
    """Decision from the review process."""

    APPROVED = "approved"
    NEEDS_CHANGES = "needs_changes"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass
class ReviewFeedback:
    """Feedback from a single reviewer."""

    reviewer_id: str
    cli_used: str
    approved: bool
    score: float
    blocking_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    security_findings: List[Dict[str, Any]] = field(default_factory=list)
    raw_output: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_dispatch_result(cls, result: DispatchResult) -> "ReviewFeedback":
        """Create ReviewFeedback from a DispatchResult."""
        output = result.output
        return cls(
            reviewer_id=result.agent_id,
            cli_used=result.cli_used,
            approved=output.get("approved", False),
            score=float(output.get("score", 0)),
            blocking_issues=output.get("blocking_issues", []),
            suggestions=output.get("suggestions", []),
            security_findings=output.get("security_findings", []),
            raw_output=output,
            timestamp=result.timestamp,
        )


@dataclass
class ReviewIteration:
    """Record of a single review iteration."""

    iteration_number: int
    work_result: DispatchResult
    reviews: List[ReviewFeedback]
    decision: ReviewDecision
    resolution: Optional[ConflictResolution] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_approved(self) -> bool:
        """Check if all reviewers approved."""
        return all(r.approved for r in self.reviews)

    @property
    def any_approved(self) -> bool:
        """Check if any reviewer approved."""
        return any(r.approved for r in self.reviews)

    @property
    def blocking_issues(self) -> List[str]:
        """Get all blocking issues from all reviewers."""
        issues = []
        for review in self.reviews:
            issues.extend(review.blocking_issues)
        return issues

    @property
    def all_suggestions(self) -> List[str]:
        """Get all suggestions from all reviewers."""
        suggestions = []
        for review in self.reviews:
            suggestions.extend(review.suggestions)
        return suggestions

    def get_feedback_for_agent(self) -> List[Dict[str, Any]]:
        """Format feedback for the working agent's next iteration."""
        return [
            {
                "from_reviewer": review.reviewer_id,
                "issues": review.blocking_issues,
                "suggestions": review.suggestions,
                "score": review.score,
            }
            for review in self.reviews
            if not review.approved
        ]


@dataclass
class ReviewCycleResult:
    """Final result of the complete review cycle."""

    task_id: str
    working_agent_id: str
    final_status: str  # "approved", "rejected", "escalated", "error"
    iterations: List[ReviewIteration]
    final_output: Optional[DispatchResult] = None
    escalation_reason: Optional[str] = None
    total_execution_time_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def iteration_count(self) -> int:
        """Number of iterations performed."""
        return len(self.iterations)

    @property
    def was_approved(self) -> bool:
        """Whether the work was ultimately approved."""
        return self.final_status == "approved"

    @property
    def required_escalation(self) -> bool:
        """Whether human intervention was required."""
        return self.final_status == "escalated"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "working_agent_id": self.working_agent_id,
            "final_status": self.final_status,
            "iteration_count": self.iteration_count,
            "escalation_reason": self.escalation_reason,
            "total_execution_time_seconds": self.total_execution_time_seconds,
            "timestamp": self.timestamp.isoformat(),
        }


class ReviewCycle:
    """Manages the iterative review-optimize-review cycle."""

    # Default thresholds
    DEFAULT_APPROVAL_SCORE = 7.0
    DEFAULT_MAX_ITERATIONS = 3
    DEFAULT_REVIEW_TIMEOUT = 300  # 5 minutes per reviewer

    def __init__(
        self,
        dispatcher: AgentDispatcher,
        project_dir: Path,
        conflict_resolver: Optional[ConflictResolver] = None,
    ):
        """Initialize review cycle.

        Args:
            dispatcher: Agent dispatcher for executing agents
            project_dir: Project directory
            conflict_resolver: Custom conflict resolver (uses default if None)
        """
        self.dispatcher = dispatcher
        self.project_dir = Path(project_dir)
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self._cycle_log: List[Dict[str, Any]] = []

    async def run(
        self,
        working_agent_id: str,
        task: Task,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        approval_score: float = DEFAULT_APPROVAL_SCORE,
        custom_reviewers: Optional[List[str]] = None,
    ) -> ReviewCycleResult:
        """Run the complete review cycle.

        This executes the iterative review-optimize-review loop until:
        - Both reviewers approve (success)
        - Max iterations reached (escalate)
        - Unrecoverable error occurs (error)

        Args:
            working_agent_id: ID of the agent doing the work
            task: Task to complete
            max_iterations: Maximum review iterations before escalation
            approval_score: Minimum score for approval
            custom_reviewers: Override default reviewers (optional)

        Returns:
            ReviewCycleResult with complete cycle information
        """
        start_time = datetime.utcnow()
        iterations: List[ReviewIteration] = []
        working_agent = get_agent(working_agent_id)

        # Get reviewers
        if custom_reviewers:
            reviewer_ids = custom_reviewers
        else:
            reviewers = get_agent_reviewers(working_agent_id)
            reviewer_ids = [r.id for r in reviewers]

        if len(reviewer_ids) < 2:
            logger.warning(
                f"Agent {working_agent_id} has fewer than 2 reviewers. "
                f"4-eyes protocol requires at least 2 reviewers."
            )
            if not reviewer_ids:
                return ReviewCycleResult(
                    task_id=task.id,
                    working_agent_id=working_agent_id,
                    final_status="error",
                    iterations=[],
                    escalation_reason="No reviewers configured for agent",
                )

        logger.info(
            f"Starting review cycle for task {task.id} with agent {working_agent_id}. "
            f"Reviewers: {reviewer_ids}, max iterations: {max_iterations}"
        )

        current_task = task
        final_output = None

        for iteration_num in range(1, max_iterations + 1):
            logger.info(f"Review cycle iteration {iteration_num}/{max_iterations}")

            # Step 1: Execute working agent
            try:
                work_result = await self.dispatcher.dispatch(
                    working_agent_id,
                    current_task,
                )
            except Exception as e:
                logger.error(f"Working agent {working_agent_id} failed: {e}")
                return ReviewCycleResult(
                    task_id=task.id,
                    working_agent_id=working_agent_id,
                    final_status="error",
                    iterations=iterations,
                    escalation_reason=f"Working agent error: {str(e)}",
                    total_execution_time_seconds=(
                        datetime.utcnow() - start_time
                    ).total_seconds(),
                )

            if work_result.status == "failed":
                logger.warning(f"Working agent returned failed status")
                # Still send to review in case it's partially useful
                if not work_result.output:
                    return ReviewCycleResult(
                        task_id=task.id,
                        working_agent_id=working_agent_id,
                        final_status="error",
                        iterations=iterations,
                        final_output=work_result,
                        escalation_reason="Working agent produced no output",
                        total_execution_time_seconds=(
                            datetime.utcnow() - start_time
                        ).total_seconds(),
                    )

            # Step 2: Parallel review by all reviewers
            reviews = await self._run_parallel_reviews(
                reviewer_ids,
                work_result,
                task,
                iteration_num,
            )

            # Step 3: Determine decision
            decision, resolution = self._determine_decision(reviews, approval_score)

            # Record iteration
            iteration = ReviewIteration(
                iteration_number=iteration_num,
                work_result=work_result,
                reviews=reviews,
                decision=decision,
                resolution=resolution,
            )
            iterations.append(iteration)
            final_output = work_result

            # Log iteration
            self._log_iteration(iteration)

            # Step 4: Check if approved
            if decision == ReviewDecision.APPROVED:
                logger.info(f"Task {task.id} approved after {iteration_num} iteration(s)")
                return ReviewCycleResult(
                    task_id=task.id,
                    working_agent_id=working_agent_id,
                    final_status="approved",
                    iterations=iterations,
                    final_output=final_output,
                    total_execution_time_seconds=(
                        datetime.utcnow() - start_time
                    ).total_seconds(),
                )

            # Step 5: Prepare feedback for next iteration
            if iteration_num < max_iterations:
                logger.info(f"Preparing feedback for iteration {iteration_num + 1}")
                feedback = iteration.get_feedback_for_agent()
                current_task = Task(
                    id=task.id,
                    title=task.title,
                    description=task.description,
                    acceptance_criteria=task.acceptance_criteria,
                    input_files=task.input_files,
                    expected_output_files=task.expected_output_files,
                    test_files=task.test_files,
                    iteration=iteration_num + 1,
                    previous_feedback=feedback,
                    metadata=task.metadata,
                )

        # Max iterations exceeded - escalate
        logger.warning(
            f"Task {task.id} not approved after {max_iterations} iterations. Escalating."
        )
        return ReviewCycleResult(
            task_id=task.id,
            working_agent_id=working_agent_id,
            final_status="escalated",
            iterations=iterations,
            final_output=final_output,
            escalation_reason=f"Max iterations ({max_iterations}) exceeded without approval",
            total_execution_time_seconds=(
                datetime.utcnow() - start_time
            ).total_seconds(),
        )

    async def _run_parallel_reviews(
        self,
        reviewer_ids: List[str],
        work_result: DispatchResult,
        original_task: Task,
        iteration: int,
    ) -> List[ReviewFeedback]:
        """Run reviews in parallel by all reviewers.

        Args:
            reviewer_ids: List of reviewer agent IDs
            work_result: Result from working agent
            original_task: Original task for context
            iteration: Current iteration number

        Returns:
            List of ReviewFeedback from each reviewer
        """
        # Prepare review context
        work_to_review = {
            "task_id": original_task.id,
            "task_title": original_task.title,
            "task_description": original_task.description,
            "acceptance_criteria": original_task.acceptance_criteria,
            "files_created": work_result.files_created,
            "files_modified": work_result.files_modified,
            "agent_output": work_result.output,
            "iteration": iteration,
        }

        # Standard review checklist
        review_checklist = [
            "Code correctness: Does the implementation match acceptance criteria?",
            "Test coverage: Are all acceptance criteria covered by tests?",
            "Code quality: Is the code clean, readable, and maintainable?",
            "Security: Are there any security vulnerabilities (OWASP Top 10)?",
            "Performance: Are there obvious performance issues?",
            "Error handling: Are errors handled appropriately?",
        ]

        # Dispatch reviews in parallel
        async def run_review(reviewer_id: str) -> ReviewFeedback:
            try:
                result = await self.dispatcher.dispatch_reviewer(
                    reviewer_id,
                    work_to_review,
                    review_checklist,
                )
                return ReviewFeedback.from_dispatch_result(result)
            except Exception as e:
                logger.error(f"Review by {reviewer_id} failed: {e}")
                return ReviewFeedback(
                    reviewer_id=reviewer_id,
                    cli_used="error",
                    approved=False,
                    score=0.0,
                    blocking_issues=[f"Review failed: {str(e)}"],
                )

        tasks = [run_review(rid) for rid in reviewer_ids]
        reviews = await asyncio.gather(*tasks)

        return list(reviews)

    def _determine_decision(
        self,
        reviews: List[ReviewFeedback],
        approval_score: float,
    ) -> Tuple[ReviewDecision, Optional[ConflictResolution]]:
        """Determine the overall decision from reviews.

        Args:
            reviews: List of review feedback
            approval_score: Minimum score for approval

        Returns:
            Tuple of (decision, optional resolution if there was a conflict)
        """
        # Check if all reviews passed
        all_approved = all(r.approved and r.score >= approval_score for r in reviews)
        any_approved = any(r.approved and r.score >= approval_score for r in reviews)

        if all_approved:
            return ReviewDecision.APPROVED, None

        if not any_approved:
            # All rejected - clear needs_changes
            return ReviewDecision.NEEDS_CHANGES, None

        # Conflict - some approved, some didn't
        # Use conflict resolver
        resolution = self.conflict_resolver.resolve(
            [
                {
                    "agent_id": r.reviewer_id,
                    "approved": r.approved,
                    "score": r.score,
                    "blocking_issues": r.blocking_issues,
                    "security_findings": r.security_findings,
                }
                for r in reviews
            ]
        )

        if resolution.resolved:
            if resolution.final_decision == "approved":
                return ReviewDecision.APPROVED, resolution
            else:
                return ReviewDecision.NEEDS_CHANGES, resolution
        else:
            return ReviewDecision.CONFLICT, resolution

    def _log_iteration(self, iteration: ReviewIteration) -> None:
        """Log an iteration for debugging and audit."""
        log_entry = {
            "iteration": iteration.iteration_number,
            "decision": iteration.decision.value,
            "reviews": [
                {
                    "reviewer": r.reviewer_id,
                    "approved": r.approved,
                    "score": r.score,
                    "blocking_issues_count": len(r.blocking_issues),
                }
                for r in iteration.reviews
            ],
            "timestamp": iteration.timestamp.isoformat(),
        }
        self._cycle_log.append(log_entry)
        logger.debug(f"Iteration {iteration.iteration_number}: {log_entry}")

    def get_cycle_log(self) -> List[Dict[str, Any]]:
        """Get the cycle log for debugging/audit."""
        return self._cycle_log.copy()


async def run_review_cycle(
    project_dir: Path,
    working_agent_id: str,
    task: Task,
    max_iterations: int = 3,
) -> ReviewCycleResult:
    """Convenience function to run a complete review cycle.

    Args:
        project_dir: Project directory
        working_agent_id: Agent to do the work
        task: Task to complete
        max_iterations: Max review iterations

    Returns:
        ReviewCycleResult
    """
    dispatcher = AgentDispatcher(project_dir)
    cycle = ReviewCycle(dispatcher, project_dir)
    return await cycle.run(working_agent_id, task, max_iterations)
