"""Tests for fixer triage module."""

import pytest

from orchestrator.fixer.triage import (
    ErrorCategory,
    ErrorTriage,
    FixerError,
    TriageDecision,
    TriageResult,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_categories_exist(self):
        """Core error categories are defined."""
        assert ErrorCategory.SYNTAX_ERROR
        assert ErrorCategory.IMPORT_ERROR
        assert ErrorCategory.TEST_FAILURE
        assert ErrorCategory.TIMEOUT_ERROR
        assert ErrorCategory.CONFIG_ERROR


class TestTriageDecision:
    """Tests for TriageDecision enum."""

    def test_decisions_exist(self):
        """Core decisions are defined."""
        assert TriageDecision.ATTEMPT_FIX
        assert TriageDecision.ESCALATE
        assert TriageDecision.SKIP


class TestFixerError:
    """Tests for FixerError dataclass."""

    def test_to_dict(self):
        """FixerError converts to dict."""
        error = FixerError(
            error_id="test-1",
            message="Test error message",
            error_type="SyntaxError",
            source="test",
        )
        result = error.to_dict()
        assert result["error_id"] == "test-1"
        assert result["message"] == "Test error message"
        assert result["error_type"] == "SyntaxError"

    def test_from_dict(self):
        """FixerError created from dict."""
        data = {
            "error_id": "test-2",
            "message": "Another error",
            "error_type": "ImportError",
            "source": "pytest",
        }
        error = FixerError.from_dict(data)
        assert error.error_id == "test-2"
        assert error.message == "Another error"


class TestTriageResult:
    """Tests for TriageResult dataclass."""

    def test_to_dict(self):
        """TriageResult converts to dict."""
        error = FixerError(
            error_id="test-1",
            message="Test error",
            error_type="TestError",
            source="test",
        )
        result = TriageResult(
            error=error,
            category=ErrorCategory.SYNTAX_ERROR,
            decision=TriageDecision.ATTEMPT_FIX,
            confidence=0.85,
        )
        data = result.to_dict()
        assert data["category"] == "syntax_error"
        assert data["decision"] == "attempt_fix"
        assert data["confidence"] == 0.85


class TestErrorTriageCategorize:
    """Tests for ErrorTriage categorization."""

    def test_categorize_syntax_error(self):
        """Categorize SyntaxError."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e1",
            message="SyntaxError: invalid syntax at line 10",
            error_type="SyntaxError",
            source="python",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.SYNTAX_ERROR

    def test_categorize_import_error(self):
        """Categorize ImportError."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e2",
            message="ModuleNotFoundError: No module named 'requests'",
            error_type="ModuleNotFoundError",
            source="python",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.IMPORT_ERROR

    def test_categorize_import_error_from_message(self):
        """Categorize ImportError from message pattern."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e3",
            message="ImportError: cannot import name 'foo' from 'bar'",
            error_type="unknown",
            source="python",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.IMPORT_ERROR

    def test_categorize_test_failure(self):
        """Categorize test failure."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e4",
            message="FAILED tests/test_main.py::test_add",
            error_type="TestFailure",
            source="pytest",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.TEST_FAILURE

    def test_categorize_test_failure_from_message(self):
        """Categorize test failure from assertion error."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e5",
            message="AssertionError: assert 5 == 3",
            error_type="unknown",
            source="pytest",
        )
        category, confidence = triage.categorize_error(error)
        assert category in (ErrorCategory.TEST_FAILURE, ErrorCategory.ASSERTION_ERROR)

    def test_categorize_timeout(self):
        """Categorize timeout error."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e6",
            message="TimeoutError: operation timed out after 30s",
            error_type="TimeoutError",
            source="test",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.TIMEOUT_ERROR

    def test_categorize_configuration_error(self):
        """Categorize configuration error."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e7",
            message="Configuration error: Invalid config file",
            error_type="ConfigError",
            source="test",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.CONFIG_ERROR

    def test_categorize_security_error(self):
        """Categorize security vulnerability."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e8",
            message="SQL injection vulnerability detected in query",
            error_type="SecurityIssue",
            source="scanner",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.SECURITY_VULNERABILITY

    def test_categorize_runtime_error(self):
        """Categorize permission error."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e9",
            message="PermissionError: Permission denied",
            error_type="PermissionError",
            source="test",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.PERMISSION_ERROR

    def test_categorize_unknown(self):
        """Unknown errors get UNKNOWN category."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e10",
            message="Something weird happened",
            error_type="WeirdError",
            source="test",
        )
        category, confidence = triage.categorize_error(error)
        assert category == ErrorCategory.UNKNOWN


class TestErrorTriageDecisions:
    """Tests for ErrorTriage decision making."""

    def test_triage_when_fixer_disabled(self):
        """When fixer is disabled, always escalate."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e1",
            message="SyntaxError: test",
            error_type="SyntaxError",
            source="test",
        )
        result = triage.triage(error, fixer_enabled=False)
        assert result.decision == TriageDecision.ESCALATE
        assert "disabled" in result.reason.lower()

    def test_triage_when_circuit_breaker_open(self):
        """When circuit breaker is open, escalate."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e2",
            message="SyntaxError: test",
            error_type="SyntaxError",
            source="test",
        )
        result = triage.triage(error, circuit_breaker_open=True)
        assert result.decision == TriageDecision.ESCALATE
        assert "circuit breaker" in result.reason.lower()

    def test_triage_fixable_error(self):
        """Fixable errors should be attempted."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e3",
            message="ImportError: No module named 'requests'",
            error_type="ImportError",
            source="python",
        )
        result = triage.triage(error)
        assert result.decision == TriageDecision.ATTEMPT_FIX
        assert result.category == ErrorCategory.IMPORT_ERROR

    def test_triage_low_confidence_escalates(self):
        """Unknown/low-confidence errors still attempt if not in NOT_FIXABLE."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e4",
            message="Something strange happened",
            error_type="unknown",
            source="test",
        )
        result = triage.triage(error)
        # UNKNOWN is in NOT_FIXABLE_CATEGORIES, so should escalate
        assert result.decision == TriageDecision.ESCALATE

    def test_triage_repeated_failures_escalate(self):
        """After repeated failures, escalate."""
        triage = ErrorTriage(max_attempts_per_error=2)
        error = FixerError(
            error_id="e5",
            message="SyntaxError: test",
            error_type="SyntaxError",
            source="test",
        )
        # Simulate previous failed attempts in history
        fix_history = [
            {"error_id": "e5", "success": False},
            {"error_id": "e5", "success": False},
        ]
        result = triage.triage(error, fix_history=fix_history)
        assert result.decision == TriageDecision.ESCALATE


class TestErrorTriageSessionLimits:
    """Tests for session-level limits."""

    def test_triage_session_limit_reached(self):
        """After max session attempts, escalate all."""
        triage = ErrorTriage(max_attempts_per_session=2)
        # Simulate using up session limit
        triage._session_attempts = 2
        error = FixerError(
            error_id="e1",
            message="SyntaxError: test",
            error_type="SyntaxError",
            source="test",
        )
        result = triage.triage(error)
        assert result.decision == TriageDecision.ESCALATE


class TestErrorTriageRecordAttempt:
    """Tests for recording attempts."""

    def test_record_attempt(self):
        """record_attempt increments counters."""
        triage = ErrorTriage()
        assert triage._session_attempts == 0
        triage.record_attempt("e1")
        assert triage._session_attempts == 1
        assert triage._error_attempts.get("e1") == 1

    def test_reset_session(self):
        """reset_session clears session counter."""
        triage = ErrorTriage()
        triage._session_attempts = 5
        triage.reset_session()
        assert triage._session_attempts == 0


class TestErrorTriageEdgeCases:
    """Tests for edge cases."""

    def test_triage_empty_error(self):
        """Handle error with minimal info."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e1",
            message="",
            error_type="",
            source="",
        )
        result = triage.triage(error)
        assert result.category == ErrorCategory.UNKNOWN
        assert result.decision == TriageDecision.ESCALATE

    def test_triage_error_with_context(self):
        """Error with full context."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e1",
            message="ImportError: No module named 'flask'",
            error_type="ImportError",
            source="python",
            phase=3,
            task_id="T1",
            agent="worker",
            stack_trace="Traceback...",
            context={"file": "app.py"},
        )
        result = triage.triage(error)
        assert result.category == ErrorCategory.IMPORT_ERROR
        assert result.decision == TriageDecision.ATTEMPT_FIX


class TestErrorTriagePriority:
    """Tests for priority assignment."""

    def test_security_has_highest_priority(self):
        """Security issues get priority 1."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e1",
            message="SQL injection vulnerability",
            error_type="SecurityIssue",
            source="scanner",
        )
        category, _ = triage.categorize_error(error)
        priority = triage.get_priority(category, error)
        assert priority == 1

    def test_test_failure_has_high_priority(self):
        """Test failures get priority 2."""
        triage = ErrorTriage()
        error = FixerError(
            error_id="e2",
            message="FAILED test_main.py",
            error_type="TestFailure",
            source="pytest",
        )
        category, _ = triage.categorize_error(error)
        priority = triage.get_priority(category, error)
        assert priority == 2


class TestTriageBatch:
    """Tests for batch triage."""

    def test_triage_batch_sorts_by_priority(self):
        """Batch triage sorts by priority."""
        triage = ErrorTriage()
        errors = [
            FixerError(
                error_id="e1",
                message="Lint error in code",
                error_type="LintError",
                source="eslint",
            ),
            FixerError(
                error_id="e2",
                message="SQL injection vulnerability",
                error_type="SecurityIssue",
                source="scanner",
            ),
            FixerError(
                error_id="e3",
                message="FAILED test_main.py",
                error_type="TestFailure",
                source="pytest",
            ),
        ]
        results = triage.triage_batch(errors)
        # Security (priority 1) should be first
        assert results[0].category == ErrorCategory.SECURITY_VULNERABILITY
