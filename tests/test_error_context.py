"""Unit tests for ErrorContextManager."""

from pathlib import Path

import pytest

from orchestrator.agents.error_context import (
    ErrorContext,
    ErrorContextManager,
    ErrorType,
    classify_error,
    extract_files_from_error,
    extract_suggestions,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


@pytest.fixture
def error_manager(temp_project: Path) -> ErrorContextManager:
    """Create an error context manager for testing."""
    return ErrorContextManager(temp_project)


class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        context = ErrorContext(
            id="err-001",
            task_id="T1",
            timestamp="2024-01-15T10:00:00",
            attempt=1,
            error_type=ErrorType.TEST_FAILURE,
            error_message="AssertionError: expected 5, got 3",
            files_involved=["src/calc.py", "tests/test_calc.py"],
        )
        data = context.to_dict()

        assert data["id"] == "err-001"
        assert data["task_id"] == "T1"
        assert data["error_type"] == ErrorType.TEST_FAILURE
        assert data["files_involved"] == ["src/calc.py", "tests/test_calc.py"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "err-002",
            "task_id": "T2",
            "timestamp": "2024-01-15T11:00:00",
            "attempt": 2,
            "error_type": ErrorType.SYNTAX_ERROR,
            "error_message": "SyntaxError: invalid syntax",
            "suggestions": ["Check for missing brackets"],
        }
        context = ErrorContext.from_dict(data)

        assert context.id == "err-002"
        assert context.error_type == ErrorType.SYNTAX_ERROR
        assert len(context.suggestions) == 1

    def test_to_prompt_context(self):
        """Test formatting for retry prompt."""
        context = ErrorContext(
            id="err-001",
            task_id="T1",
            timestamp="2024-01-15T10:00:00",
            attempt=1,
            error_type=ErrorType.TEST_FAILURE,
            error_message="AssertionError: expected 5, got 3",
            files_involved=["src/calc.py"],
            suggestions=["Check the calculation logic"],
        )

        prompt_text = context.to_prompt_context()

        assert "Previous Attempt 1 Failed" in prompt_text
        assert ErrorType.TEST_FAILURE in prompt_text
        assert "AssertionError" in prompt_text
        assert "src/calc.py" in prompt_text
        assert "Check the calculation logic" in prompt_text

    def test_to_prompt_context_truncation(self):
        """Test that long context is truncated."""
        context = ErrorContext(
            id="err-001",
            task_id="T1",
            timestamp="2024-01-15T10:00:00",
            attempt=1,
            error_type=ErrorType.RUNTIME_ERROR,
            error_message="Very long error message " * 100,
            stack_trace="Very long stack trace " * 200,
        )

        prompt_text = context.to_prompt_context(max_chars=500)

        assert len(prompt_text) <= 500


class TestClassifyError:
    """Tests for classify_error function."""

    def test_classify_test_failure(self):
        """Test classifying test failure."""
        result = classify_error(
            "pytest: 3 failed",
            stderr="FAILED test_calc.py::test_add",
        )
        assert result == ErrorType.TEST_FAILURE

    def test_classify_syntax_error(self):
        """Test classifying syntax error."""
        result = classify_error(
            "SyntaxError: invalid syntax",
            stderr="File 'test.py', line 5",
        )
        assert result == ErrorType.SYNTAX_ERROR

    def test_classify_import_error(self):
        """Test classifying import error."""
        result = classify_error(
            "ModuleNotFoundError: No module named 'requests'",
        )
        assert result == ErrorType.IMPORT_ERROR

    def test_classify_type_error(self):
        """Test classifying type error."""
        result = classify_error(
            "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        )
        assert result == ErrorType.TYPE_ERROR

    def test_classify_timeout(self):
        """Test classifying timeout."""
        result = classify_error(
            "Command timed out",
            exit_code=-1,
        )
        assert result == ErrorType.TIMEOUT

    def test_classify_build_failure(self):
        """Test classifying build failure."""
        result = classify_error(
            "Build failed",
            stderr="Compilation error at line 42",
        )
        assert result == ErrorType.BUILD_FAILURE

    def test_classify_lint_error(self):
        """Test classifying lint error."""
        result = classify_error(
            "eslint found problems",
        )
        assert result == ErrorType.LINT_ERROR

    def test_classify_unknown(self):
        """Test classifying unknown error."""
        result = classify_error(
            "Something weird happened",
            exit_code=0,
        )
        assert result == ErrorType.UNKNOWN

    def test_classify_runtime_error(self):
        """Test classifying runtime error by exit code."""
        result = classify_error(
            "Something went wrong",
            exit_code=1,
        )
        assert result == ErrorType.RUNTIME_ERROR


class TestExtractSuggestions:
    """Tests for extract_suggestions function."""

    def test_suggestions_for_test_failure(self):
        """Test suggestions for test failure."""
        suggestions = extract_suggestions(
            ErrorType.TEST_FAILURE,
            "AssertionError",
        )
        assert len(suggestions) > 0
        assert any("test" in s.lower() for s in suggestions)

    def test_suggestions_for_syntax_error(self):
        """Test suggestions for syntax error."""
        suggestions = extract_suggestions(
            ErrorType.SYNTAX_ERROR,
            "SyntaxError",
        )
        assert len(suggestions) > 0
        assert any("bracket" in s.lower() or "indent" in s.lower() for s in suggestions)

    def test_suggestions_for_import_error(self):
        """Test suggestions for import error."""
        suggestions = extract_suggestions(
            ErrorType.IMPORT_ERROR,
            "ModuleNotFoundError",
        )
        assert len(suggestions) > 0
        assert any("install" in s.lower() or "import" in s.lower() for s in suggestions)


class TestExtractFilesFromError:
    """Tests for extract_files_from_error function."""

    def test_extract_python_traceback(self):
        """Test extracting files from Python traceback."""
        error = 'File "src/calc.py", line 10, in add'
        files = extract_files_from_error(error)

        assert "src/calc.py" in files

    def test_extract_javascript_error(self):
        """Test extracting files from JavaScript error."""
        error = "at processFile (src/utils.js:42:13)"
        files = extract_files_from_error(error)

        assert "src/utils.js" in files

    def test_extract_multiple_files(self):
        """Test extracting multiple files."""
        error = """
        File "src/main.py", line 5
        File "src/utils.py", line 10
        at handler (app.ts:20:5)
        """
        files = extract_files_from_error(error)

        assert len(files) >= 2


class TestErrorContextManager:
    """Tests for ErrorContextManager."""

    def test_record_error(self, error_manager: ErrorContextManager):
        """Test recording an error."""
        context = error_manager.record_error(
            task_id="T1",
            error_message="Test failed",
            attempt=1,
            error_type=ErrorType.TEST_FAILURE,
        )

        assert context.task_id == "T1"
        assert context.error_type == ErrorType.TEST_FAILURE
        assert context.attempt == 1

    def test_record_error_auto_classify(self, error_manager: ErrorContextManager):
        """Test that errors are auto-classified."""
        context = error_manager.record_error(
            task_id="T1",
            error_message="SyntaxError: invalid syntax",
            attempt=1,
        )

        assert context.error_type == ErrorType.SYNTAX_ERROR

    def test_record_error_auto_suggestions(self, error_manager: ErrorContextManager):
        """Test that suggestions are auto-generated."""
        context = error_manager.record_error(
            task_id="T1",
            error_message="AssertionError in test_calc",
            stderr="pytest: FAILED",
            attempt=1,
        )

        assert len(context.suggestions) > 0

    def test_get_error_history(self, error_manager: ErrorContextManager):
        """Test getting error history."""
        # Record multiple errors
        for i in range(3):
            error_manager.record_error(
                task_id="T1",
                error_message=f"Error {i}",
                attempt=i + 1,
            )

        history = error_manager.get_error_history("T1")

        assert len(history) == 3
        assert history[0].attempt == 1
        assert history[2].attempt == 3

    def test_get_latest_error(self, error_manager: ErrorContextManager):
        """Test getting latest error."""
        for i in range(3):
            error_manager.record_error(
                task_id="T1",
                error_message=f"Error {i}",
                attempt=i + 1,
            )

        latest = error_manager.get_latest_error("T1")

        assert latest is not None
        assert latest.attempt == 3
        assert latest.error_message == "Error 2"

    def test_get_latest_error_none(self, error_manager: ErrorContextManager):
        """Test getting latest error when none exist."""
        latest = error_manager.get_latest_error("nonexistent")
        assert latest is None

    def test_build_retry_prompt(self, error_manager: ErrorContextManager):
        """Test building retry prompt."""
        error_manager.record_error(
            task_id="T1",
            error_message="AssertionError: expected 5, got 3",
            attempt=1,
            error_type=ErrorType.TEST_FAILURE,
        )

        retry_prompt = error_manager.build_retry_prompt(
            task_id="T1",
            original_prompt="Implement add function",
        )

        assert "Previous Attempt" in retry_prompt
        assert "AssertionError" in retry_prompt
        assert "Implement add function" in retry_prompt
        assert "Retry Attempt 2" in retry_prompt

    def test_build_retry_prompt_no_errors(self, error_manager: ErrorContextManager):
        """Test retry prompt with no errors returns original."""
        original = "Original prompt"
        result = error_manager.build_retry_prompt("T1", original)

        assert result == original

    def test_clear_task_errors(self, error_manager: ErrorContextManager):
        """Test clearing task errors."""
        error_manager.record_error(
            task_id="T1",
            error_message="Error",
            attempt=1,
        )

        result = error_manager.clear_task_errors("T1")

        assert result is True
        assert error_manager.get_error_history("T1") == []

    def test_get_error_summary(self, error_manager: ErrorContextManager):
        """Test getting error summary."""
        error_manager.record_error(
            task_id="T1",
            error_message="Test failed",
            error_type=ErrorType.TEST_FAILURE,
            files_involved=["src/calc.py"],
            attempt=1,
        )
        error_manager.record_error(
            task_id="T1",
            error_message="Syntax error",
            error_type=ErrorType.SYNTAX_ERROR,
            files_involved=["src/calc.py", "tests/test.py"],
            attempt=2,
        )

        summary = error_manager.get_error_summary("T1")

        assert summary["total_errors"] == 2
        assert summary["error_types"][ErrorType.TEST_FAILURE] == 1
        assert summary["error_types"][ErrorType.SYNTAX_ERROR] == 1
        assert "src/calc.py" in summary["files_involved"]
        assert "tests/test.py" in summary["files_involved"]

    def test_max_errors_per_task(self, temp_project: Path):
        """Test that old errors are trimmed."""
        manager = ErrorContextManager(temp_project, max_errors_per_task=3)

        for i in range(5):
            manager.record_error(
                task_id="T1",
                error_message=f"Error {i}",
                attempt=i + 1,
            )

        history = manager.get_error_history("T1")

        # Should only keep the last 3
        assert len(history) == 3
        assert history[0].attempt == 3
        assert history[2].attempt == 5

    def test_error_persistence(self, temp_project: Path):
        """Test that errors persist across manager instances."""
        manager1 = ErrorContextManager(temp_project)
        manager1.record_error(
            task_id="T1",
            error_message="Persistent error",
            attempt=1,
        )

        # Create new manager instance
        manager2 = ErrorContextManager(temp_project)
        history = manager2.get_error_history("T1")

        assert len(history) == 1
        assert history[0].error_message == "Persistent error"
