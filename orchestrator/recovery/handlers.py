"""
Error recovery handlers for the multi-agent workflow.

Handles different types of errors with appropriate recovery strategies:
- Transient errors: Retry with exponential backoff
- Agent failures: Try backup CLI, then escalate
- Review conflicts: Apply weighted resolution, escalate if unresolved
- Security issues: Immediate halt and escalate
- Spec mismatches: Never auto-modify, escalate for human decision

Usage:
    from orchestrator.recovery import RecoveryHandler

    handler = RecoveryHandler(project_dir)
    result = await handler.handle_transient_error(error, context)
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorCategory(str, Enum):
    """Categories of errors in the workflow."""

    TRANSIENT = "transient"  # Temporary, may succeed on retry
    AGENT_FAILURE = "agent_failure"  # Agent produced invalid/incomplete output
    REVIEW_CONFLICT = "review_conflict"  # Reviewers disagree
    SPEC_MISMATCH = "spec_mismatch"  # Tests don't match PRODUCT.md
    BLOCKING_SECURITY = "blocking_security"  # Critical security issue
    RESOURCE_UNAVAILABLE = "resource_unavailable"  # CLI/service unavailable
    TIMEOUT = "timeout"  # Operation timed out
    VALIDATION = "validation"  # Schema/data validation failed


class RecoveryAction(str, Enum):
    """Actions taken for recovery."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    USE_BACKUP = "use_backup"
    ESCALATE = "escalate"
    HALT = "halt"
    SKIP = "skip"
    ROLLBACK = "rollback"


@dataclass
class ErrorContext:
    """Context for an error occurrence."""

    category: ErrorCategory
    message: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    iteration: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    action_taken: RecoveryAction
    message: str
    should_continue: bool = True
    retry_count: int = 0
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    recovered_value: Any = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "action_taken": self.action_taken.value,
            "message": self.message,
            "should_continue": self.should_continue,
            "retry_count": self.retry_count,
            "escalation_required": self.escalation_required,
            "escalation_reason": self.escalation_reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EscalationRequest:
    """Request for human intervention."""

    task_id: str
    reason: str
    context: str
    attempts_made: int
    options: List[str] = field(default_factory=list)
    recommendation: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "reason": self.reason,
            "context": self.context,
            "attempts_made": self.attempts_made,
            "options": self.options,
            "recommendation": self.recommendation,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
        }


class RecoveryHandler:
    """Handles error recovery throughout the workflow."""

    # Retry configuration
    MAX_TRANSIENT_RETRIES = 3
    BASE_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 30.0
    JITTER_RANGE = (0.0, 1.0)

    # Escalation triggers
    ESCALATION_TRIGGERS = {
        "max_iterations_exceeded",
        "reviewer_conflict_unresolved",
        "test_spec_mismatch",
        "blocking_security_issue",
        "clarification_needed",
        "resource_unavailable",
    }

    def __init__(
        self,
        project_dir: Path,
        max_retries: int = MAX_TRANSIENT_RETRIES,
        escalation_callback: Optional[Callable[[EscalationRequest], None]] = None,
    ):
        """Initialize recovery handler.

        Args:
            project_dir: Project directory
            max_retries: Maximum retry attempts for transient errors
            escalation_callback: Optional callback for escalations
        """
        self.project_dir = Path(project_dir)
        self.max_retries = max_retries
        self.escalation_callback = escalation_callback
        self._error_log: List[Dict[str, Any]] = []
        self._escalation_log: List[EscalationRequest] = []

    async def handle_error(
        self,
        error: Exception,
        context: ErrorContext,
        retry_operation: Optional[Callable[[], T]] = None,
    ) -> RecoveryResult:
        """Handle an error with appropriate recovery strategy.

        Args:
            error: The exception that occurred
            context: Error context
            retry_operation: Optional callable to retry

        Returns:
            RecoveryResult with recovery outcome
        """
        # Log the error
        self._log_error(error, context)

        # Determine recovery strategy based on category
        if context.category == ErrorCategory.TRANSIENT:
            return await self.handle_transient_error(error, context, retry_operation)

        elif context.category == ErrorCategory.AGENT_FAILURE:
            return await self.handle_agent_failure(error, context)

        elif context.category == ErrorCategory.REVIEW_CONFLICT:
            return await self.handle_review_conflict(context.details.get("reviews", []), context)

        elif context.category == ErrorCategory.SPEC_MISMATCH:
            return await self.handle_spec_mismatch(error, context)

        elif context.category == ErrorCategory.BLOCKING_SECURITY:
            return await self.handle_security_issue(error, context)

        elif context.category == ErrorCategory.TIMEOUT:
            return await self.handle_timeout(error, context, retry_operation)

        else:
            return await self.handle_unknown_error(error, context)

    async def handle_transient_error(
        self,
        error: Exception,
        context: ErrorContext,
        retry_operation: Optional[Callable[[], T]] = None,
    ) -> RecoveryResult:
        """Handle transient errors with exponential backoff.

        Transient errors include:
        - Network timeouts
        - Rate limiting
        - Temporary service unavailability

        Args:
            error: The exception
            context: Error context
            retry_operation: Callable to retry

        Returns:
            RecoveryResult
        """
        for attempt in range(self.max_retries):
            # Calculate backoff with jitter
            backoff = min(
                self.BASE_BACKOFF_SECONDS * (2 ** attempt),
                self.MAX_BACKOFF_SECONDS,
            )
            jitter = random.uniform(*self.JITTER_RANGE)
            wait_time = backoff + jitter

            logger.info(
                f"Transient error retry {attempt + 1}/{self.max_retries}, "
                f"waiting {wait_time:.2f}s"
            )

            await asyncio.sleep(wait_time)

            if retry_operation:
                try:
                    result = await retry_operation() if asyncio.iscoroutinefunction(retry_operation) else retry_operation()
                    return RecoveryResult(
                        success=True,
                        action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
                        message=f"Succeeded after {attempt + 1} retries",
                        retry_count=attempt + 1,
                        recovered_value=result,
                    )
                except Exception as retry_error:
                    logger.warning(f"Retry {attempt + 1} failed: {retry_error}")
                    continue
            else:
                # No retry operation provided, just wait and return
                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY,
                    message="Backoff completed, retry manually",
                    retry_count=attempt + 1,
                )

        # Max retries exceeded - escalate
        return await self._escalate(
            context=context,
            reason="max_iterations_exceeded",
            message=f"Transient error persists after {self.max_retries} retries: {error}",
        )

    async def handle_agent_failure(
        self,
        error: Exception,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Handle agent execution failures.

        Strategy:
        1. Try backup CLI if available
        2. Escalate if backup also fails

        Args:
            error: The exception
            context: Error context

        Returns:
            RecoveryResult
        """
        agent_id = context.agent_id
        used_backup = context.details.get("used_backup", False)

        if not used_backup:
            # Suggest trying backup CLI
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.USE_BACKUP,
                message=f"Agent {agent_id} failed, try backup CLI",
                should_continue=True,
            )

        # Backup also failed - escalate
        return await self._escalate(
            context=context,
            reason="agent_failure",
            message=f"Agent {agent_id} failed on both primary and backup CLI: {error}",
            options=[
                "Retry with different agent",
                "Provide manual fix",
                "Skip this task",
            ],
        )

    async def handle_review_conflict(
        self,
        reviews: List[Dict[str, Any]],
        context: ErrorContext,
    ) -> RecoveryResult:
        """Handle conflicts between reviewers.

        Args:
            reviews: List of review results
            context: Error context

        Returns:
            RecoveryResult
        """
        # Import here to avoid circular dependency
        from orchestrator.review import ConflictResolver

        resolver = ConflictResolver()
        resolution = resolver.resolve(reviews)

        if resolution.resolved:
            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.SKIP,  # Skip escalation
                message=f"Conflict resolved: {resolution.final_decision}",
                recovered_value=resolution,
            )

        # Unresolved conflict - escalate
        return await self._escalate(
            context=context,
            reason="reviewer_conflict_unresolved",
            message="Reviewers disagree and weighted resolution failed",
            options=[
                "Accept Reviewer 1 (Security)",
                "Accept Reviewer 2 (Code Quality)",
                "Request third opinion",
                "Override and approve",
                "Override and reject",
            ],
            recommendation="Review security findings before making decision",
        )

    async def handle_spec_mismatch(
        self,
        error: Exception,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Handle test/spec mismatches.

        CRITICAL: Never auto-modify tests. Always escalate.

        Args:
            error: The exception
            context: Error context

        Returns:
            RecoveryResult
        """
        return await self._escalate(
            context=context,
            reason="test_spec_mismatch",
            message=f"Test expectations don't match PRODUCT.md: {error}",
            severity="high",
            options=[
                "Update PRODUCT.md to match tests",
                "Rewrite tests to match PRODUCT.md",
                "Clarify requirements with stakeholder",
            ],
            recommendation="Review acceptance criteria in PRODUCT.md before deciding",
        )

    async def handle_security_issue(
        self,
        error: Exception,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Handle blocking security issues.

        CRITICAL: Immediate halt, no retry.

        Args:
            error: The exception
            context: Error context

        Returns:
            RecoveryResult
        """
        # Log security finding
        logger.critical(f"SECURITY ISSUE: {error}")

        # Immediate escalation
        return await self._escalate(
            context=context,
            reason="blocking_security_issue",
            message=f"Critical security issue found: {error}",
            severity="critical",
            options=[
                "Fix security issue before proceeding",
                "Accept risk (requires approval)",
                "Abort workflow",
            ],
            recommendation="Fix the security issue before any further work",
        )

    async def handle_timeout(
        self,
        error: Exception,
        context: ErrorContext,
        retry_operation: Optional[Callable[[], T]] = None,
    ) -> RecoveryResult:
        """Handle timeout errors.

        Args:
            error: The exception
            context: Error context
            retry_operation: Optional retry callable

        Returns:
            RecoveryResult
        """
        # Timeouts get one retry with longer timeout
        if context.details.get("retry_count", 0) < 1:
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.RETRY,
                message="Timeout occurred, retry with extended timeout",
                should_continue=True,
                retry_count=1,
            )

        # Already retried - escalate
        return await self._escalate(
            context=context,
            reason="timeout",
            message=f"Operation timed out after retry: {error}",
            options=[
                "Retry with even longer timeout",
                "Break task into smaller parts",
                "Skip this task",
            ],
        )

    async def handle_unknown_error(
        self,
        error: Exception,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Handle unknown/unexpected errors.

        Args:
            error: The exception
            context: Error context

        Returns:
            RecoveryResult
        """
        return await self._escalate(
            context=context,
            reason="unknown_error",
            message=f"Unexpected error: {error}",
            severity="medium",
            options=[
                "Investigate and retry",
                "Skip this task",
                "Abort workflow",
            ],
        )

    async def _escalate(
        self,
        context: ErrorContext,
        reason: str,
        message: str,
        severity: str = "medium",
        options: Optional[List[str]] = None,
        recommendation: Optional[str] = None,
    ) -> RecoveryResult:
        """Create an escalation request.

        Args:
            context: Error context
            reason: Escalation reason
            message: Human-readable message
            severity: Severity level
            options: Available options for human
            recommendation: Suggested action

        Returns:
            RecoveryResult with escalation
        """
        escalation = EscalationRequest(
            task_id=context.task_id or "unknown",
            reason=reason,
            context=message,
            attempts_made=context.iteration,
            options=options or [],
            recommendation=recommendation,
            severity=severity,
        )

        self._escalation_log.append(escalation)

        # Call escalation callback if provided
        if self.escalation_callback:
            try:
                self.escalation_callback(escalation)
            except Exception as e:
                logger.error(f"Escalation callback failed: {e}")

        # Write escalation to workflow directory
        self._write_escalation(escalation)

        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.ESCALATE,
            message=message,
            should_continue=False,
            escalation_required=True,
            escalation_reason=reason,
        )

    def _log_error(self, error: Exception, context: ErrorContext) -> None:
        """Log an error occurrence."""
        log_entry = {
            "category": context.category.value,
            "message": str(error),
            "task_id": context.task_id,
            "agent_id": context.agent_id,
            "iteration": context.iteration,
            "timestamp": context.timestamp.isoformat(),
            "details": context.details,
        }
        self._error_log.append(log_entry)
        logger.error(f"Error [{context.category.value}]: {error}")

    def _write_escalation(self, escalation: EscalationRequest) -> None:
        """Write escalation to workflow directory."""
        import json

        escalation_dir = self.project_dir / ".workflow" / "escalations"
        escalation_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{escalation.task_id}_{escalation.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        escalation_file = escalation_dir / filename

        escalation_file.write_text(json.dumps(escalation.to_dict(), indent=2))
        logger.info(f"Escalation written to {escalation_file}")

    def get_error_log(self) -> List[Dict[str, Any]]:
        """Get the error log."""
        return self._error_log.copy()

    def get_escalation_log(self) -> List[Dict[str, Any]]:
        """Get the escalation log."""
        return [e.to_dict() for e in self._escalation_log]


# Convenience functions
async def handle_transient_error(
    project_dir: Path,
    error: Exception,
    context: ErrorContext,
    retry_operation: Optional[Callable] = None,
) -> RecoveryResult:
    """Handle a transient error."""
    handler = RecoveryHandler(project_dir)
    return await handler.handle_transient_error(error, context, retry_operation)


async def handle_agent_failure(
    project_dir: Path,
    error: Exception,
    context: ErrorContext,
) -> RecoveryResult:
    """Handle an agent failure."""
    handler = RecoveryHandler(project_dir)
    return await handler.handle_agent_failure(error, context)


async def handle_review_conflict(
    project_dir: Path,
    reviews: List[Dict[str, Any]],
    context: ErrorContext,
) -> RecoveryResult:
    """Handle a review conflict."""
    handler = RecoveryHandler(project_dir)
    return await handler.handle_review_conflict(reviews, context)
