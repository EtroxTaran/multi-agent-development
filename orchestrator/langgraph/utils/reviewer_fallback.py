"""Reviewer timeout and fallback utilities.

Provides utilities for handling slow or failing review agents with
configurable timeout and single-agent fallback behavior.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, TypeVar

from ...config.thresholds import ReviewConfig, load_project_config
from ...langgraph.state import AgentFeedback

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ReviewerResult:
    """Result from a reviewer with metadata about the execution."""

    feedback: Optional[AgentFeedback]
    agent_name: str
    success: bool
    duration_seconds: float
    error: Optional[str] = None
    timed_out: bool = False
    retries: int = 0


@dataclass
class ReviewFallbackResult:
    """Result of review with potential single-agent fallback."""

    cursor_result: Optional[ReviewerResult]
    gemini_result: Optional[ReviewerResult]
    used_fallback: bool
    fallback_reason: Optional[str]
    combined_feedback: dict[str, AgentFeedback]

    @property
    def has_cursor(self) -> bool:
        return self.cursor_result is not None and self.cursor_result.success

    @property
    def has_gemini(self) -> bool:
        return self.gemini_result is not None and self.gemini_result.success

    @property
    def has_both(self) -> bool:
        return self.has_cursor and self.has_gemini


async def run_reviewer_with_timeout(
    reviewer_func: Callable[..., Any],
    agent_name: str,
    timeout_seconds: int,
    *args: Any,
    **kwargs: Any,
) -> ReviewerResult:
    """Run a reviewer function with timeout.

    Args:
        reviewer_func: Async function to call the reviewer
        agent_name: Name of the agent (cursor or gemini)
        timeout_seconds: Timeout in seconds
        *args, **kwargs: Arguments to pass to the reviewer function

    Returns:
        ReviewerResult with feedback or error information
    """
    start_time = datetime.now()

    try:
        # Run with timeout
        result = await asyncio.wait_for(
            reviewer_func(*args, **kwargs),
            timeout=timeout_seconds,
        )

        duration = (datetime.now() - start_time).total_seconds()

        # Extract feedback from result
        feedback = None
        if isinstance(result, dict):
            # Handle node return format
            feedback_dict = result.get("validation_feedback") or result.get(
                "verification_feedback", {}
            )
            feedback = feedback_dict.get(agent_name)
        elif isinstance(result, AgentFeedback):
            feedback = result

        return ReviewerResult(
            feedback=feedback,
            agent_name=agent_name,
            success=feedback is not None,
            duration_seconds=duration,
            error=None,
            timed_out=False,
        )

    except asyncio.TimeoutError:
        duration = (datetime.now() - start_time).total_seconds()
        logger.warning(f"{agent_name} reviewer timed out after {timeout_seconds}s")

        return ReviewerResult(
            feedback=None,
            agent_name=agent_name,
            success=False,
            duration_seconds=duration,
            error=f"Timeout after {timeout_seconds} seconds",
            timed_out=True,
        )

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"{agent_name} reviewer failed: {e}")

        return ReviewerResult(
            feedback=None,
            agent_name=agent_name,
            success=False,
            duration_seconds=duration,
            error=str(e),
            timed_out=False,
        )


async def run_parallel_reviewers_with_fallback(
    cursor_func: Callable[..., Any],
    gemini_func: Callable[..., Any],
    config: ReviewConfig,
    cursor_args: Optional[tuple] = None,
    gemini_args: Optional[tuple] = None,
    cursor_kwargs: Optional[dict] = None,
    gemini_kwargs: Optional[dict] = None,
) -> ReviewFallbackResult:
    """Run both reviewers in parallel with timeout and fallback handling.

    This function:
    1. Runs both reviewers in parallel with timeout
    2. If one fails/times out, uses single-agent fallback if configured
    3. Returns combined results with metadata about fallback usage

    Args:
        cursor_func: Async function to run Cursor reviewer
        gemini_func: Async function to run Gemini reviewer
        config: ReviewConfig with timeout and fallback settings
        cursor_args: Positional args for cursor function
        gemini_args: Positional args for gemini function
        cursor_kwargs: Keyword args for cursor function
        gemini_kwargs: Keyword args for gemini function

    Returns:
        ReviewFallbackResult with combined feedback and fallback metadata
    """
    cursor_args = cursor_args or ()
    gemini_args = gemini_args or ()
    cursor_kwargs = cursor_kwargs or {}
    gemini_kwargs = gemini_kwargs or {}

    timeout = config.reviewer_timeout_seconds

    # Run both reviewers in parallel
    cursor_task = run_reviewer_with_timeout(
        cursor_func,
        "cursor",
        timeout,
        *cursor_args,
        **cursor_kwargs,
    )
    gemini_task = run_reviewer_with_timeout(
        gemini_func,
        "gemini",
        timeout,
        *gemini_args,
        **gemini_kwargs,
    )

    cursor_result, gemini_result = await asyncio.gather(
        cursor_task,
        gemini_task,
        return_exceptions=True,
    )

    # Handle gather exceptions
    if isinstance(cursor_result, Exception):
        cursor_result = ReviewerResult(
            feedback=None,
            agent_name="cursor",
            success=False,
            duration_seconds=0,
            error=str(cursor_result),
        )
    if isinstance(gemini_result, Exception):
        gemini_result = ReviewerResult(
            feedback=None,
            agent_name="gemini",
            success=False,
            duration_seconds=0,
            error=str(gemini_result),
        )

    # Log timeouts if configured
    if config.log_timeouts:
        if cursor_result.timed_out:
            logger.warning(f"Cursor reviewer timed out after {timeout}s")
        if gemini_result.timed_out:
            logger.warning(f"Gemini reviewer timed out after {timeout}s")

    # Build combined feedback
    combined_feedback: dict[str, AgentFeedback] = {}
    used_fallback = False
    fallback_reason = None

    if cursor_result.success and cursor_result.feedback:
        combined_feedback["cursor"] = cursor_result.feedback
    if gemini_result.success and gemini_result.feedback:
        combined_feedback["gemini"] = gemini_result.feedback

    # Check if we need fallback
    if not cursor_result.success or not gemini_result.success:
        if config.allow_single_agent_approval:
            used_fallback = True

            if not cursor_result.success and not gemini_result.success:
                fallback_reason = "Both reviewers failed"
            elif not cursor_result.success:
                fallback_reason = f"Cursor failed: {cursor_result.error or 'unknown error'}"
            else:
                fallback_reason = f"Gemini failed: {gemini_result.error or 'unknown error'}"

            logger.info(f"Using single-agent fallback: {fallback_reason}")

    return ReviewFallbackResult(
        cursor_result=cursor_result,
        gemini_result=gemini_result,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        combined_feedback=combined_feedback,
    )


def apply_single_agent_penalty(
    feedback: AgentFeedback,
    config: ReviewConfig,
) -> AgentFeedback:
    """Apply score penalty for single-agent review.

    When only one reviewer provides feedback, apply a penalty to
    account for the missing second opinion.

    Args:
        feedback: Original feedback from single agent
        config: ReviewConfig with penalty settings

    Returns:
        AgentFeedback with adjusted score
    """
    if not feedback:
        return feedback

    # Create modified feedback with penalty
    penalized_score = max(0, feedback.score - config.single_agent_score_penalty)

    # Create a new AgentFeedback with updated score
    return AgentFeedback(
        agent=feedback.agent,
        approved=feedback.approved and penalized_score >= config.single_agent_minimum_score,
        score=penalized_score,
        assessment=feedback.assessment,
        concerns=feedback.concerns,
        blocking_issues=feedback.blocking_issues,
        summary=f"[Single-agent review, score penalty applied] {feedback.summary}",
        raw_output=feedback.raw_output,
    )


def check_single_agent_approval(
    fallback_result: ReviewFallbackResult,
    config: ReviewConfig,
    phase: str = "validation",
) -> tuple[bool, Optional[AgentFeedback], str]:
    """Check if single-agent approval is acceptable.

    Args:
        fallback_result: Result from parallel reviewers
        config: ReviewConfig with approval settings
        phase: "validation" or "verification"

    Returns:
        Tuple of (approved, feedback, reason)
    """
    if fallback_result.has_both:
        return False, None, "Both reviewers succeeded - use normal resolution"

    if not config.allow_single_agent_approval:
        return False, None, "Single-agent approval not allowed"

    if not fallback_result.has_cursor and not fallback_result.has_gemini:
        return False, None, "No reviewer succeeded"

    # Get the successful feedback
    if fallback_result.has_cursor:
        result = fallback_result.cursor_result
        agent_name = "cursor"
    else:
        result = fallback_result.gemini_result
        agent_name = "gemini"

    if not result or not result.feedback:
        return False, None, f"{agent_name} feedback is missing"

    feedback = result.feedback

    # Check preference
    if config.single_agent_preference != "any":
        if config.single_agent_preference != agent_name:
            logger.warning(
                f"Single-agent fallback using {agent_name} but preference is {config.single_agent_preference}"
            )

    # Apply penalty
    penalized_feedback = apply_single_agent_penalty(feedback, config)

    # Check if meets minimum score
    if penalized_feedback.score < config.single_agent_minimum_score:
        return (
            False,
            penalized_feedback,
            f"Score {penalized_feedback.score:.1f} below minimum {config.single_agent_minimum_score}",
        )

    return (
        True,
        penalized_feedback,
        f"Single-agent approval from {agent_name} with penalized score {penalized_feedback.score:.1f}",
    )


def get_review_config(project_dir: str) -> ReviewConfig:
    """Load review configuration from project config.

    Args:
        project_dir: Project directory path

    Returns:
        ReviewConfig with project-specific settings
    """
    try:
        project_config = load_project_config(project_dir)
        return project_config.review
    except Exception as e:
        logger.warning(f"Could not load project config: {e}. Using defaults.")
        return ReviewConfig()
