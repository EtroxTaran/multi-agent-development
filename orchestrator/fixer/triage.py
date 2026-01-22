"""Error triage for the fixer agent.

Triage determines whether an error can be handled by the fixer,
categorizes the error type, and prioritizes errors for fixing.

The triage node runs before diagnosis to quickly determine:
1. Is this error fixable by the fixer?
2. What category does this error belong to?
3. Should we attempt a fix or escalate immediately?
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of errors the fixer can handle."""

    # Code errors
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    NAME_ERROR = "name_error"
    ATTRIBUTE_ERROR = "attribute_error"

    # Test errors
    TEST_FAILURE = "test_failure"
    ASSERTION_ERROR = "assertion_error"

    # Build errors
    BUILD_FAILURE = "build_failure"
    COMPILATION_ERROR = "compilation_error"
    LINT_ERROR = "lint_error"

    # Dependency errors
    DEPENDENCY_ERROR = "dependency_error"
    VERSION_CONFLICT = "version_conflict"
    MISSING_PACKAGE = "missing_package"

    # Configuration errors
    CONFIG_ERROR = "config_error"
    ENV_ERROR = "env_error"

    # Runtime errors
    TIMEOUT_ERROR = "timeout_error"
    MEMORY_ERROR = "memory_error"
    PERMISSION_ERROR = "permission_error"

    # Agent errors
    AGENT_CRASH = "agent_crash"
    RATE_LIMIT = "rate_limit"

    # Security errors (fixable with notification)
    SECURITY_VULNERABILITY = "security_vulnerability"
    SECRET_EXPOSURE = "secret_exposure"

    # Unfixable
    UNKNOWN = "unknown"
    NOT_FIXABLE = "not_fixable"


class TriageDecision(str, Enum):
    """Decisions from triage."""

    ATTEMPT_FIX = "attempt_fix"  # Fixer should attempt to fix
    ESCALATE = "escalate"       # Escalate to human immediately
    SKIP = "skip"               # Skip this error (low priority or already fixed)
    RETRY_LATER = "retry_later"  # Retry after other fixes


# Error patterns for categorization
ERROR_PATTERNS = {
    ErrorCategory.SYNTAX_ERROR: [
        r"SyntaxError:",
        r"IndentationError:",
        r"TabError:",
        r"Unexpected token",
        r"Parse error",
        r"invalid syntax",
    ],
    ErrorCategory.IMPORT_ERROR: [
        r"ImportError:",
        r"ModuleNotFoundError:",
        r"No module named",
        r"cannot import name",
        r"Cannot find module",
    ],
    ErrorCategory.TYPE_ERROR: [
        r"TypeError:",
        r"Type 'None' cannot",
        r"expected .* got",
        r"Argument of type",
    ],
    ErrorCategory.NAME_ERROR: [
        r"NameError:",
        r"ReferenceError:",
        r"is not defined",
        r"undefined variable",
    ],
    ErrorCategory.ATTRIBUTE_ERROR: [
        r"AttributeError:",
        r"has no attribute",
        r"has no property",
    ],
    ErrorCategory.TEST_FAILURE: [
        r"FAILED",
        r"AssertionError",
        r"test failed",
        r"tests? passed, \d+ failed",
        r"pytest.*failed",
        r"jest.*failed",
    ],
    ErrorCategory.ASSERTION_ERROR: [
        r"AssertionError:",
        r"assert .* failed",
        r"expected .* to (equal|be|match)",
    ],
    ErrorCategory.BUILD_FAILURE: [
        r"Build failed",
        r"npm ERR!.*build",
        r"make:.*Error",
        r"cargo build.*failed",
    ],
    ErrorCategory.COMPILATION_ERROR: [
        r"error\[E\d+\]:",
        r"tsc.*error TS",
        r"compilation failed",
        r"cannot compile",
    ],
    ErrorCategory.LINT_ERROR: [
        r"eslint.*error",
        r"pylint.*error",
        r"ruff.*error",
        r"flake8.*error",
    ],
    ErrorCategory.DEPENDENCY_ERROR: [
        r"Could not resolve dependencies",
        r"peer dep missing",
        r"dependency conflict",
        r"version mismatch",
    ],
    ErrorCategory.MISSING_PACKAGE: [
        r"pip install",
        r"npm install",
        r"package.*not found",
        r"Missing required package",
    ],
    ErrorCategory.CONFIG_ERROR: [
        r"Configuration error",
        r"Invalid config",
        r"config.*not found",
        r"\.env.*missing",
    ],
    ErrorCategory.TIMEOUT_ERROR: [
        r"TimeoutError",
        r"timed out",
        r"timeout.*exceeded",
        r"operation took too long",
    ],
    ErrorCategory.MEMORY_ERROR: [
        r"MemoryError",
        r"out of memory",
        r"heap out of memory",
        r"ENOMEM",
    ],
    ErrorCategory.PERMISSION_ERROR: [
        r"PermissionError",
        r"EACCES",
        r"permission denied",
        r"Access denied",
    ],
    ErrorCategory.AGENT_CRASH: [
        r"agent.*crash",
        r"CLI not found",
        r"agent.*error",
        r"subprocess.*failed",
    ],
    ErrorCategory.RATE_LIMIT: [
        r"rate limit",
        r"too many requests",
        r"429",
        r"quota exceeded",
    ],
    ErrorCategory.SECURITY_VULNERABILITY: [
        r"vulnerability",
        r"CVE-\d+",
        r"security.*issue",
        r"XSS",
        r"SQL injection",
        r"command injection",
    ],
    ErrorCategory.SECRET_EXPOSURE: [
        r"secret.*exposed",
        r"API key.*found",
        r"credential.*leaked",
        r"password.*visible",
    ],
}

# Categories that are NOT fixable by the fixer
NOT_FIXABLE_CATEGORIES = {
    ErrorCategory.MEMORY_ERROR,  # Need system-level fix
    ErrorCategory.UNKNOWN,
    ErrorCategory.NOT_FIXABLE,
}

# Categories that require security notification
SECURITY_CATEGORIES = {
    ErrorCategory.SECURITY_VULNERABILITY,
    ErrorCategory.SECRET_EXPOSURE,
}


@dataclass
class FixerError:
    """Represents an error to be fixed.

    Attributes:
        error_id: Unique error identifier
        message: Error message
        error_type: Type of error
        source: Where the error originated
        phase: Workflow phase where error occurred
        task_id: Task that caused the error
        agent: Agent that reported the error
        stack_trace: Full stack trace if available
        context: Additional context
        timestamp: When the error occurred
    """

    error_id: str
    message: str
    error_type: str
    source: str
    phase: Optional[int] = None
    task_id: Optional[str] = None
    agent: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[dict] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "message": self.message,
            "error_type": self.error_type,
            "source": self.source,
            "phase": self.phase,
            "task_id": self.task_id,
            "agent": self.agent,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixerError":
        return cls(
            error_id=data.get("error_id", data.get("id", "")),
            message=data.get("message", ""),
            error_type=data.get("error_type", data.get("type", "unknown")),
            source=data.get("source", "unknown"),
            phase=data.get("phase"),
            task_id=data.get("task_id"),
            agent=data.get("agent"),
            stack_trace=data.get("stack_trace"),
            context=data.get("context"),
            timestamp=data.get("timestamp"),
        )

    @classmethod
    def from_state_error(cls, error: dict, index: int = 0) -> "FixerError":
        """Create from a workflow state error entry."""
        return cls(
            error_id=error.get("id", f"state_error_{index}"),
            message=error.get("message", str(error)),
            error_type=error.get("type", "unknown"),
            source="state",
            phase=error.get("phase"),
            task_id=error.get("task_id"),
            agent=error.get("agent"),
            stack_trace=error.get("stack_trace"),
            context=error.get("context"),
            timestamp=error.get("timestamp"),
        )


@dataclass
class TriageResult:
    """Result of error triage.

    Attributes:
        error: The error being triaged
        category: Categorized error type
        decision: What to do with this error
        confidence: How confident we are in the categorization (0-1)
        priority: Fix priority (1=highest, 5=lowest)
        reason: Explanation for the decision
        requires_security_notification: Whether this is a security fix
        suggested_strategy: Name of suggested fix strategy
        related_errors: IDs of related errors that might be fixed together
    """

    error: FixerError
    category: ErrorCategory
    decision: TriageDecision
    confidence: float
    priority: int = 3
    reason: str = ""
    requires_security_notification: bool = False
    suggested_strategy: Optional[str] = None
    related_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "error": self.error.to_dict(),
            "category": self.category.value,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "priority": self.priority,
            "reason": self.reason,
            "requires_security_notification": self.requires_security_notification,
            "suggested_strategy": self.suggested_strategy,
            "related_errors": self.related_errors,
        }


class ErrorTriage:
    """Triages errors to determine fixability and priority.

    The triage component quickly categorizes errors and decides
    whether the fixer should attempt to fix them.
    """

    def __init__(
        self,
        max_attempts_per_error: int = 2,
        max_attempts_per_session: int = 10,
    ):
        """Initialize the triage component.

        Args:
            max_attempts_per_error: Max fix attempts per error
            max_attempts_per_session: Max fix attempts per session
        """
        self.max_attempts_per_error = max_attempts_per_error
        self.max_attempts_per_session = max_attempts_per_session
        self._session_attempts = 0
        self._error_attempts: dict[str, int] = {}

    def categorize_error(self, error: FixerError) -> tuple[ErrorCategory, float]:
        """Categorize an error based on its message and context.

        Args:
            error: The error to categorize

        Returns:
            Tuple of (category, confidence)
        """
        message = error.message.lower()
        stack_trace = (error.stack_trace or "").lower()
        combined_text = f"{message} {stack_trace}"

        best_category = ErrorCategory.UNKNOWN
        best_confidence = 0.0

        for category, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    # Calculate confidence based on specificity
                    confidence = 0.7 + (0.1 * len(pattern) / 50)  # Longer patterns = more confident
                    if confidence > best_confidence:
                        best_category = category
                        best_confidence = min(confidence, 0.95)

        # Check error_type field for additional categorization
        error_type_lower = error.error_type.lower()
        for category, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                pattern_clean = pattern.replace(":", "").replace(r"\d+", "").lower()
                if pattern_clean in error_type_lower:
                    return category, 0.9

        return best_category, best_confidence

    def get_priority(self, category: ErrorCategory, error: FixerError) -> int:
        """Determine fix priority for an error.

        Priority levels:
        1 = Critical (security, blocking)
        2 = High (test failures, build failures)
        3 = Medium (import errors, syntax errors)
        4 = Low (lint errors, warnings)
        5 = Lowest (cosmetic issues)

        Args:
            category: Error category
            error: The error

        Returns:
            Priority level (1-5)
        """
        priority_map = {
            # Critical - security issues
            ErrorCategory.SECURITY_VULNERABILITY: 1,
            ErrorCategory.SECRET_EXPOSURE: 1,

            # High - blocking issues
            ErrorCategory.BUILD_FAILURE: 2,
            ErrorCategory.TEST_FAILURE: 2,
            ErrorCategory.COMPILATION_ERROR: 2,
            ErrorCategory.AGENT_CRASH: 2,

            # Medium - common fixable issues
            ErrorCategory.IMPORT_ERROR: 3,
            ErrorCategory.SYNTAX_ERROR: 3,
            ErrorCategory.DEPENDENCY_ERROR: 3,
            ErrorCategory.MISSING_PACKAGE: 3,
            ErrorCategory.TYPE_ERROR: 3,
            ErrorCategory.NAME_ERROR: 3,

            # Lower - less critical
            ErrorCategory.ATTRIBUTE_ERROR: 4,
            ErrorCategory.CONFIG_ERROR: 4,
            ErrorCategory.TIMEOUT_ERROR: 4,
            ErrorCategory.LINT_ERROR: 4,

            # Lowest - minor issues
            ErrorCategory.RATE_LIMIT: 5,
            ErrorCategory.PERMISSION_ERROR: 5,
            ErrorCategory.UNKNOWN: 5,
        }

        return priority_map.get(category, 5)

    def get_suggested_strategy(self, category: ErrorCategory) -> Optional[str]:
        """Get suggested fix strategy for a category.

        Args:
            category: Error category

        Returns:
            Strategy name or None
        """
        strategy_map = {
            ErrorCategory.SYNTAX_ERROR: "syntax_fix",
            ErrorCategory.IMPORT_ERROR: "import_fix",
            ErrorCategory.MISSING_PACKAGE: "dependency_fix",
            ErrorCategory.DEPENDENCY_ERROR: "dependency_fix",
            ErrorCategory.TEST_FAILURE: "test_failure_fix",
            ErrorCategory.ASSERTION_ERROR: "test_failure_fix",
            ErrorCategory.BUILD_FAILURE: "build_fix",
            ErrorCategory.CONFIG_ERROR: "config_fix",
            ErrorCategory.TIMEOUT_ERROR: "timeout_fix",
            ErrorCategory.RATE_LIMIT: "retry",
            ErrorCategory.AGENT_CRASH: "retry",
            ErrorCategory.TYPE_ERROR: "type_fix",
            ErrorCategory.NAME_ERROR: "name_fix",
        }

        return strategy_map.get(category)

    def triage(
        self,
        error: FixerError,
        fixer_enabled: bool = True,
        circuit_breaker_open: bool = False,
        fix_history: Optional[list[dict]] = None,
    ) -> TriageResult:
        """Triage an error to determine if and how to fix it.

        Args:
            error: The error to triage
            fixer_enabled: Whether fixer is enabled
            circuit_breaker_open: Whether circuit breaker is open
            fix_history: History of previous fix attempts

        Returns:
            TriageResult with decision
        """
        # Categorize the error
        category, confidence = self.categorize_error(error)

        # Start with default values
        decision = TriageDecision.ATTEMPT_FIX
        reason = ""
        priority = self.get_priority(category, error)
        requires_security_notification = category in SECURITY_CATEGORIES
        suggested_strategy = self.get_suggested_strategy(category)

        # Check if fixer is disabled
        if not fixer_enabled:
            return TriageResult(
                error=error,
                category=category,
                decision=TriageDecision.ESCALATE,
                confidence=confidence,
                priority=priority,
                reason="Fixer is disabled",
                requires_security_notification=requires_security_notification,
                suggested_strategy=suggested_strategy,
            )

        # Check circuit breaker
        if circuit_breaker_open:
            return TriageResult(
                error=error,
                category=category,
                decision=TriageDecision.ESCALATE,
                confidence=confidence,
                priority=priority,
                reason="Circuit breaker is open",
                requires_security_notification=requires_security_notification,
                suggested_strategy=suggested_strategy,
            )

        # Check if category is fixable
        if category in NOT_FIXABLE_CATEGORIES:
            return TriageResult(
                error=error,
                category=category,
                decision=TriageDecision.ESCALATE,
                confidence=confidence,
                priority=priority,
                reason=f"Category '{category.value}' is not auto-fixable",
                requires_security_notification=requires_security_notification,
                suggested_strategy=suggested_strategy,
            )

        # Check per-error attempt limit
        error_attempts = self._error_attempts.get(error.error_id, 0)
        if error_attempts >= self.max_attempts_per_error:
            return TriageResult(
                error=error,
                category=category,
                decision=TriageDecision.ESCALATE,
                confidence=confidence,
                priority=priority,
                reason=f"Max attempts ({self.max_attempts_per_error}) reached for this error",
                requires_security_notification=requires_security_notification,
                suggested_strategy=suggested_strategy,
            )

        # Check session attempt limit
        if self._session_attempts >= self.max_attempts_per_session:
            return TriageResult(
                error=error,
                category=category,
                decision=TriageDecision.ESCALATE,
                confidence=confidence,
                priority=priority,
                reason=f"Max session attempts ({self.max_attempts_per_session}) reached",
                requires_security_notification=requires_security_notification,
                suggested_strategy=suggested_strategy,
            )

        # Check fix history for repeated failures
        if fix_history:
            same_error_fixes = [
                f for f in fix_history
                if f.get("error_id") == error.error_id
            ]
            failed_fixes = [f for f in same_error_fixes if not f.get("success")]
            if len(failed_fixes) >= self.max_attempts_per_error:
                return TriageResult(
                    error=error,
                    category=category,
                    decision=TriageDecision.ESCALATE,
                    confidence=confidence,
                    priority=priority,
                    reason=f"Previous fix attempts ({len(failed_fixes)}) failed",
                    requires_security_notification=requires_security_notification,
                    suggested_strategy=suggested_strategy,
                )

        # If we get here, attempt the fix
        reason = f"Error categorized as '{category.value}' with confidence {confidence:.2f}"
        if suggested_strategy:
            reason += f", suggested strategy: {suggested_strategy}"

        return TriageResult(
            error=error,
            category=category,
            decision=TriageDecision.ATTEMPT_FIX,
            confidence=confidence,
            priority=priority,
            reason=reason,
            requires_security_notification=requires_security_notification,
            suggested_strategy=suggested_strategy,
        )

    def record_attempt(self, error_id: str) -> None:
        """Record a fix attempt for an error.

        Args:
            error_id: ID of the error being fixed
        """
        self._session_attempts += 1
        self._error_attempts[error_id] = self._error_attempts.get(error_id, 0) + 1

    def reset_session(self) -> None:
        """Reset session attempt counter."""
        self._session_attempts = 0

    def triage_batch(
        self,
        errors: list[FixerError],
        fixer_enabled: bool = True,
        circuit_breaker_open: bool = False,
        fix_history: Optional[list[dict]] = None,
    ) -> list[TriageResult]:
        """Triage multiple errors and sort by priority.

        Args:
            errors: List of errors to triage
            fixer_enabled: Whether fixer is enabled
            circuit_breaker_open: Whether circuit breaker is open
            fix_history: History of previous fix attempts

        Returns:
            List of TriageResults sorted by priority
        """
        results = [
            self.triage(error, fixer_enabled, circuit_breaker_open, fix_history)
            for error in errors
        ]

        # Sort by priority (1=highest) then by confidence (highest first)
        results.sort(key=lambda r: (r.priority, -r.confidence))

        return results
