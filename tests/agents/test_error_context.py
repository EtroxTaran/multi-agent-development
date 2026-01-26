"""Tests for error context manager.

Tests error recording, classification, suggestions, and retry prompt building.
"""



from orchestrator.agents.error_context import (
    DEFAULT_ERROR_DIR,
    MAX_ERRORS_PER_TASK,
    ErrorContext,
    ErrorContextManager,
    ErrorType,
    classify_error,
    extract_files_from_error,
    extract_suggestions,
)


class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_error_context_creation(self, sample_error_context):
        """Test ErrorContext creation."""
        assert sample_error_context.id == "err-T1-20260126120000-1"
        assert sample_error_context.task_id == "T1"
        assert sample_error_context.attempt == 1
        assert sample_error_context.error_type == "test_failure"
        assert sample_error_context.error_message == "AssertionError: expected 5, got 3"
        assert "src/calc.py" in sample_error_context.files_involved

    def test_error_context_to_dict(self, sample_error_context):
        """Test serialization to dictionary."""
        d = sample_error_context.to_dict()
        assert d["id"] == "err-T1-20260126120000-1"
        assert d["task_id"] == "T1"
        assert d["error_type"] == "test_failure"
        assert d["files_involved"] == ["src/calc.py", "tests/test_calc.py"]

    def test_error_context_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "err-T2-123",
            "task_id": "T2",
            "timestamp": "2026-01-26T12:00:00",
            "attempt": 2,
            "error_type": "syntax_error",
            "error_message": "SyntaxError: invalid syntax",
            "stdout_excerpt": "",
            "stderr_excerpt": "",
            "files_involved": ["src/main.py"],
            "stack_trace": None,
            "suggestions": ["Check brackets"],
            "metadata": {},
        }
        context = ErrorContext.from_dict(data)
        assert context.id == "err-T2-123"
        assert context.task_id == "T2"
        assert context.error_type == "syntax_error"

    def test_error_context_to_prompt_context(self, sample_error_context):
        """Test formatting for retry prompt."""
        prompt_context = sample_error_context.to_prompt_context()

        assert "Previous Attempt 1 Failed" in prompt_context
        assert "Error Type: test_failure" in prompt_context
        assert "AssertionError" in prompt_context
        assert "src/calc.py" in prompt_context

    def test_error_context_to_prompt_context_truncation(self, sample_error_context):
        """Test that prompt context is truncated."""
        prompt_context = sample_error_context.to_prompt_context(max_chars=100)
        assert len(prompt_context) <= 103  # 100 + "..."


class TestErrorType:
    """Tests for ErrorType constants."""

    def test_error_type_values(self):
        """Test error type constant values."""
        assert ErrorType.TEST_FAILURE == "test_failure"
        assert ErrorType.SYNTAX_ERROR == "syntax_error"
        assert ErrorType.IMPORT_ERROR == "import_error"
        assert ErrorType.TYPE_ERROR == "type_error"
        assert ErrorType.RUNTIME_ERROR == "runtime_error"
        assert ErrorType.TIMEOUT == "timeout"
        assert ErrorType.BUILD_FAILURE == "build_failure"
        assert ErrorType.LINT_ERROR == "lint_error"
        assert ErrorType.SECURITY_ISSUE == "security_issue"
        assert ErrorType.CLARIFICATION_NEEDED == "clarification_needed"
        assert ErrorType.UNKNOWN == "unknown"


class TestClassifyError:
    """Tests for classify_error function."""

    def test_classify_timeout(self):
        """Test timeout classification."""
        assert classify_error("", "", exit_code=-1) == ErrorType.TIMEOUT
        assert classify_error("timeout error", "") == ErrorType.TIMEOUT

    def test_classify_syntax_error(self):
        """Test syntax error classification."""
        assert classify_error("SyntaxError: invalid syntax", "") == ErrorType.SYNTAX_ERROR
        assert classify_error("", "syntax error on line 5") == ErrorType.SYNTAX_ERROR

    def test_classify_import_error(self):
        """Test import error classification."""
        assert classify_error("ImportError: No module named foo", "") == ErrorType.IMPORT_ERROR
        assert classify_error("ModuleNotFoundError: No module", "") == ErrorType.IMPORT_ERROR

    def test_classify_type_error(self):
        """Test type error classification."""
        assert classify_error("TypeError: cannot add str and int", "") == ErrorType.TYPE_ERROR

    def test_classify_test_failure(self):
        """Test test failure classification."""
        assert classify_error("AssertionError: expected 5", "test failed") == ErrorType.TEST_FAILURE
        assert classify_error("", "pytest FAILED test_calc.py") == ErrorType.TEST_FAILURE
        assert classify_error("", "jest test failed") == ErrorType.TEST_FAILURE

    def test_classify_build_failure(self):
        """Test build failure classification."""
        assert classify_error("build failed", "") == ErrorType.BUILD_FAILURE
        assert classify_error("", "compilation error") == ErrorType.BUILD_FAILURE

    def test_classify_lint_error(self):
        """Test lint error classification."""
        assert classify_error("lint error", "") == ErrorType.LINT_ERROR
        assert classify_error("", "eslint: error") == ErrorType.LINT_ERROR
        assert classify_error("", "flake8: E501") == ErrorType.LINT_ERROR

    def test_classify_security_issue(self):
        """Test security issue classification."""
        assert classify_error("security vulnerability found", "") == ErrorType.SECURITY_ISSUE

    def test_classify_clarification_needed(self):
        """Test clarification needed classification."""
        assert classify_error("need clarification", "") == ErrorType.CLARIFICATION_NEEDED
        assert classify_error("requirements unclear", "") == ErrorType.CLARIFICATION_NEEDED

    def test_classify_runtime_error(self):
        """Test runtime error classification (non-zero exit)."""
        assert classify_error("Something went wrong", "", exit_code=1) == ErrorType.RUNTIME_ERROR

    def test_classify_unknown(self):
        """Test unknown classification."""
        assert classify_error("random message", "", exit_code=0) == ErrorType.UNKNOWN


class TestExtractSuggestions:
    """Tests for extract_suggestions function."""

    def test_suggestions_test_failure(self):
        """Test suggestions for test failure."""
        suggestions = extract_suggestions(ErrorType.TEST_FAILURE, "Test failed", "")
        assert len(suggestions) > 0
        assert any("test" in s.lower() for s in suggestions)

    def test_suggestions_syntax_error(self):
        """Test suggestions for syntax error."""
        suggestions = extract_suggestions(ErrorType.SYNTAX_ERROR, "SyntaxError", "")
        assert len(suggestions) > 0
        assert any("bracket" in s.lower() or "indentation" in s.lower() for s in suggestions)

    def test_suggestions_import_error(self):
        """Test suggestions for import error."""
        suggestions = extract_suggestions(ErrorType.IMPORT_ERROR, "ImportError", "")
        assert len(suggestions) > 0
        assert any("module" in s.lower() or "import" in s.lower() for s in suggestions)

    def test_suggestions_type_error(self):
        """Test suggestions for type error."""
        suggestions = extract_suggestions(ErrorType.TYPE_ERROR, "TypeError", "")
        assert len(suggestions) > 0
        assert any("type" in s.lower() for s in suggestions)

    def test_suggestions_timeout(self):
        """Test suggestions for timeout."""
        suggestions = extract_suggestions(ErrorType.TIMEOUT, "Timeout", "")
        assert len(suggestions) > 0
        assert any("loop" in s.lower() or "blocking" in s.lower() for s in suggestions)

    def test_suggestions_unknown(self):
        """Test suggestions for unknown error (empty)."""
        suggestions = extract_suggestions(ErrorType.UNKNOWN, "Unknown", "")
        assert suggestions == []


class TestExtractFilesFromError:
    """Tests for extract_files_from_error function."""

    def test_extract_python_traceback(self):
        """Test extracting files from Python traceback."""
        error = 'File "src/calc.py", line 10, in add'
        files = extract_files_from_error(error)
        assert "src/calc.py" in files

    def test_extract_javascript_error(self):
        """Test extracting files from JavaScript error."""
        stderr = "at Object.<anonymous> (src/index.js:15"
        files = extract_files_from_error("", stderr)
        assert any("index.js" in f for f in files)

    def test_extract_generic_path(self):
        """Test extracting generic file paths."""
        error = "Error in tests/test_main.py:25"
        files = extract_files_from_error(error)
        assert "tests/test_main.py" in files

    def test_extract_no_files(self):
        """Test extracting when no files mentioned."""
        error = "Something went wrong"
        files = extract_files_from_error(error)
        assert files == []

    def test_extract_multiple_files(self):
        """Test extracting multiple files."""
        error = """
        File "src/calc.py", line 10
        File "tests/test_calc.py", line 5
        """
        files = extract_files_from_error(error)
        assert "src/calc.py" in files
        assert "tests/test_calc.py" in files


class TestErrorContextManager:
    """Tests for ErrorContextManager class."""

    def test_initialization(self, temp_project_dir):
        """Test manager initialization."""
        manager = ErrorContextManager(temp_project_dir)
        assert manager.project_dir == temp_project_dir
        assert manager.error_dir == temp_project_dir / DEFAULT_ERROR_DIR
        assert manager.max_errors_per_task == MAX_ERRORS_PER_TASK

    def test_initialization_custom_dir(self, temp_project_dir):
        """Test initialization with custom error directory."""
        manager = ErrorContextManager(temp_project_dir, error_dir="custom/errors")
        assert manager.error_dir == temp_project_dir / "custom/errors"

    def test_initialization_custom_max_errors(self, temp_project_dir):
        """Test initialization with custom max errors."""
        manager = ErrorContextManager(temp_project_dir, max_errors_per_task=10)
        assert manager.max_errors_per_task == 10

    def test_record_error(self, error_context_manager):
        """Test recording an error."""
        context = error_context_manager.record_error(
            task_id="T1",
            error_message="Test failed",
            attempt=1,
            error_type="test_failure",
        )

        assert context.task_id == "T1"
        assert context.error_message == "Test failed"
        assert context.attempt == 1
        assert context.error_type == "test_failure"
        assert context.id is not None

    def test_record_error_auto_classify(self, error_context_manager):
        """Test error auto-classification."""
        context = error_context_manager.record_error(
            task_id="T1",
            error_message="SyntaxError: invalid syntax",
            attempt=1,
        )

        assert context.error_type == ErrorType.SYNTAX_ERROR

    def test_record_error_auto_extract_files(self, error_context_manager):
        """Test auto file extraction."""
        context = error_context_manager.record_error(
            task_id="T1",
            error_message='File "src/calc.py", line 10',
            attempt=1,
            stderr='File "tests/test_calc.py", line 5',
        )

        assert "src/calc.py" in context.files_involved
        assert "tests/test_calc.py" in context.files_involved

    def test_record_error_auto_suggestions(self, error_context_manager):
        """Test auto suggestion generation."""
        context = error_context_manager.record_error(
            task_id="T1",
            error_message="AssertionError: test failed",
            attempt=1,
            error_type=ErrorType.TEST_FAILURE,
        )

        assert len(context.suggestions) > 0

    def test_record_error_with_metadata(self, error_context_manager):
        """Test recording error with metadata."""
        context = error_context_manager.record_error(
            task_id="T1",
            error_message="Error",
            attempt=1,
            metadata={"phase": "implementation", "iteration": 3},
        )

        assert context.metadata == {"phase": "implementation", "iteration": 3}

    def test_record_error_truncates_long_content(self, error_context_manager):
        """Test that long content is truncated."""
        long_message = "x" * 1000
        long_stdout = "y" * 2000
        long_stderr = "z" * 2000
        long_trace = "t" * 5000

        context = error_context_manager.record_error(
            task_id="T1",
            error_message=long_message,
            attempt=1,
            stdout=long_stdout,
            stderr=long_stderr,
            stack_trace=long_trace,
        )

        assert len(context.error_message) <= 500
        assert len(context.stdout_excerpt) <= 1000
        assert len(context.stderr_excerpt) <= 1000
        assert len(context.stack_trace) <= 2000

    def test_get_error_history(self, error_context_manager):
        """Test getting error history."""
        error_context_manager.record_error("T1", "Error 1", attempt=1)
        error_context_manager.record_error("T1", "Error 2", attempt=2)
        error_context_manager.record_error("T1", "Error 3", attempt=3)

        history = error_context_manager.get_error_history("T1")

        assert len(history) == 3
        assert history[0].error_message == "Error 1"
        assert history[2].error_message == "Error 3"

    def test_get_error_history_empty(self, error_context_manager):
        """Test getting empty error history."""
        history = error_context_manager.get_error_history("T-NONEXISTENT")
        assert history == []

    def test_get_latest_error(self, error_context_manager):
        """Test getting latest error."""
        error_context_manager.record_error("T1", "Error 1", attempt=1)
        error_context_manager.record_error("T1", "Error 2", attempt=2)

        latest = error_context_manager.get_latest_error("T1")

        assert latest is not None
        assert latest.error_message == "Error 2"
        assert latest.attempt == 2

    def test_get_latest_error_none(self, error_context_manager):
        """Test getting latest error when none exist."""
        latest = error_context_manager.get_latest_error("T-NONEXISTENT")
        assert latest is None

    def test_build_retry_prompt(self, error_context_manager):
        """Test building enhanced retry prompt."""
        error_context_manager.record_error(
            "T1",
            "AssertionError: expected 5, got 3",
            attempt=1,
            error_type="test_failure",
        )

        original = "Implement the calculator add function"
        enhanced = error_context_manager.build_retry_prompt("T1", original)

        assert "Previous Attempts Failed" in enhanced
        assert "AssertionError" in enhanced
        assert "Retry Attempt 2" in enhanced
        assert original in enhanced
        assert "Retry Instructions" in enhanced

    def test_build_retry_prompt_no_errors(self, error_context_manager):
        """Test retry prompt with no previous errors."""
        original = "Implement feature"
        result = error_context_manager.build_retry_prompt("T1", original)
        assert result == original

    def test_build_retry_prompt_multiple_errors(self, error_context_manager):
        """Test retry prompt with multiple errors."""
        error_context_manager.record_error("T1", "Error 1", attempt=1)
        error_context_manager.record_error("T1", "Error 2", attempt=2)
        error_context_manager.record_error("T1", "Error 3", attempt=3)

        enhanced = error_context_manager.build_retry_prompt("T1", "Original prompt")

        # Should include context from multiple errors
        assert "Error 1" in enhanced or "Error 2" in enhanced or "Error 3" in enhanced
        assert "Retry Attempt 4" in enhanced

    def test_clear_task_errors(self, error_context_manager):
        """Test clearing errors for a task."""
        error_context_manager.record_error("T1", "Error", attempt=1)

        result = error_context_manager.clear_task_errors("T1")

        assert result is True
        assert error_context_manager.get_error_history("T1") == []

    def test_clear_task_errors_nonexistent(self, error_context_manager):
        """Test clearing errors for task with no errors."""
        result = error_context_manager.clear_task_errors("T-NONEXISTENT")
        assert result is False

    def test_get_error_summary(self, error_context_manager):
        """Test getting error summary."""
        error_context_manager.record_error(
            "T1", "Test error 1", attempt=1, error_type="test_failure", files_involved=["a.py"]
        )
        error_context_manager.record_error(
            "T1", "Test error 2", attempt=2, error_type="test_failure", files_involved=["b.py"]
        )
        error_context_manager.record_error(
            "T1", "Syntax error", attempt=3, error_type="syntax_error", files_involved=["a.py"]
        )

        summary = error_context_manager.get_error_summary("T1")

        assert summary["task_id"] == "T1"
        assert summary["total_errors"] == 3
        assert summary["error_types"]["test_failure"] == 2
        assert summary["error_types"]["syntax_error"] == 1
        assert "a.py" in summary["files_involved"]
        assert "b.py" in summary["files_involved"]
        assert summary["latest_error"] == "syntax_error"

    def test_get_error_summary_empty(self, error_context_manager):
        """Test getting summary for task with no errors."""
        summary = error_context_manager.get_error_summary("T-NONEXISTENT")

        assert summary["task_id"] == "T-NONEXISTENT"
        assert summary["total_errors"] == 0
        assert summary["error_types"] == {}
        assert summary["files_involved"] == []

    def test_max_errors_trimming(self, temp_project_dir):
        """Test that errors are trimmed to max limit."""
        manager = ErrorContextManager(temp_project_dir, max_errors_per_task=3)

        for i in range(5):
            manager.record_error("T1", f"Error {i+1}", attempt=i + 1)

        history = manager.get_error_history("T1")

        # Should only keep last 3
        assert len(history) == 3
        assert history[0].error_message == "Error 3"
        assert history[2].error_message == "Error 5"

    def test_persistence(self, temp_project_dir):
        """Test that errors persist across manager instances."""
        manager1 = ErrorContextManager(temp_project_dir)
        manager1.record_error("T1", "Persisted error", attempt=1, error_type="test_failure")

        manager2 = ErrorContextManager(temp_project_dir)
        history = manager2.get_error_history("T1")

        assert len(history) == 1
        assert history[0].error_message == "Persisted error"
