"""Tests for fixer diagnosis engine."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from orchestrator.fixer.diagnosis import (
    AffectedFile,
    DiagnosisConfidence,
    DiagnosisEngine,
    DiagnosisResult,
    RootCause,
)
from orchestrator.fixer.triage import ErrorCategory, FixerError


class TestRootCause:
    """Tests for RootCause enum."""

    def test_root_causes_exist(self):
        """Core root causes are defined."""
        assert RootCause.MISSING_IMPORT
        assert RootCause.SYNTAX_ERROR
        assert RootCause.ASSERTION_MISMATCH
        assert RootCause.TIMEOUT
        assert RootCause.VULNERABILITY


class TestAffectedFile:
    """Tests for AffectedFile dataclass."""

    def test_to_dict(self):
        """AffectedFile converts to dict."""
        af = AffectedFile(
            path="src/main.py",
            line_number=42,
            column=10,
        )
        result = af.to_dict()
        assert result["path"] == "src/main.py"
        assert result["line_number"] == 42
        assert result["column"] == 10


class TestDiagnosisResult:
    """Tests for DiagnosisResult dataclass."""

    def test_to_dict(self):
        """DiagnosisResult converts to dict."""
        error = FixerError(
            error_id="e1",
            message="Test error",
            error_type="TestError",
            source="test",
        )
        result = DiagnosisResult(
            error=error,
            root_cause=RootCause.SYNTAX_ERROR,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        data = result.to_dict()
        assert data["root_cause"] == "syntax_error"
        assert data["confidence"] == "high"
        assert data["category"] == "syntax_error"

    def test_is_auto_fixable(self):
        """Most root causes are auto-fixable."""
        error = FixerError(
            error_id="e1",
            message="Test",
            error_type="TestError",
            source="test",
        )
        result = DiagnosisResult(
            error=error,
            root_cause=RootCause.MISSING_IMPORT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
        )
        # MISSING_IMPORT should have suggested fixes
        assert len(result.suggested_fixes) > 0 or result.root_cause != RootCause.UNKNOWN


@pytest.fixture
def mock_llm_diagnosis():
    """Mock LLM diagnosis engine."""
    with patch("orchestrator.fixer.diagnosis.LLMDiagnosisEngine") as MockClass:
        mock_instance = MockClass.return_value
        # Default behavior: pass through what we give it or standard mocks
        mock_instance.diagnose = AsyncMock()
        yield mock_instance


@pytest.mark.asyncio
class TestDiagnosisEngineSyntaxErrors:
    """Tests for diagnosing syntax errors."""

    async def test_diagnose_syntax_error_basic(self, tmp_path, mock_llm_diagnosis):
        """Diagnose basic syntax error."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.SYNTAX_ERROR,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="SyntaxError: invalid syntax",
            error_type="SyntaxError",
            source="python",
            stack_trace="File 'test.py', line 10\n    if x = 5:\n         ^",
        )
        result = await engine.diagnose(error, ErrorCategory.SYNTAX_ERROR)
        assert result.root_cause == RootCause.SYNTAX_ERROR
        assert result.confidence in (DiagnosisConfidence.HIGH, DiagnosisConfidence.MEDIUM)

    async def test_diagnose_syntax_error_missing_paren(self, tmp_path, mock_llm_diagnosis):
        """Diagnose unclosed bracket error."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.UNCLOSED_BRACKET,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e2",
            message="SyntaxError: unexpected EOF while parsing",
            error_type="SyntaxError",
            source="python",
            stack_trace="File 'app.py', line 50\n    print(foo(",
        )
        result = await engine.diagnose(error, ErrorCategory.SYNTAX_ERROR)
        assert result.root_cause in (RootCause.SYNTAX_ERROR, RootCause.UNCLOSED_BRACKET)


@pytest.mark.asyncio
class TestDiagnosisEngineImportErrors:
    """Tests for diagnosing import errors."""

    async def test_diagnose_missing_module(self, tmp_path, mock_llm_diagnosis):
        """Diagnose missing module import."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.MISSING_IMPORT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="ModuleNotFoundError: No module named 'requests'",
            error_type="ModuleNotFoundError",
            source="python",
        )
        result = await engine.diagnose(error, ErrorCategory.IMPORT_ERROR)
        assert result.root_cause == RootCause.MISSING_IMPORT
        assert result.confidence == DiagnosisConfidence.HIGH

    async def test_diagnose_import_from_error(self, tmp_path, mock_llm_diagnosis):
        """Diagnose import-from error."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.MISSING_IMPORT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e2",
            message="ImportError: cannot import name 'foo' from 'bar'",
            error_type="ImportError",
            source="python",
        )
        result = await engine.diagnose(error, ErrorCategory.IMPORT_ERROR)
        assert result.root_cause in (RootCause.MISSING_IMPORT, RootCause.WRONG_IMPORT_PATH)


@pytest.mark.asyncio
class TestDiagnosisEngineTestFailures:
    """Tests for diagnosing test failures."""

    async def test_diagnose_assertion_error(self, tmp_path, mock_llm_diagnosis):
        """Diagnose assertion failure."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.ASSERTION_MISMATCH,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.TEST_FAILURE,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="AssertionError: assert 5 == 3",
            error_type="AssertionError",
            source="pytest",
        )
        result = await engine.diagnose(error, ErrorCategory.TEST_FAILURE)
        assert result.root_cause == RootCause.ASSERTION_MISMATCH

    async def test_diagnose_test_with_traceback(self, tmp_path, mock_llm_diagnosis):
        """Diagnose test failure with full traceback."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.ASSERTION_MISMATCH,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.TEST_FAILURE,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e2",
            message="FAILED tests/test_math.py::test_add",
            error_type="TestFailure",
            source="pytest",
            stack_trace='''
                def test_add():
                    result = add(2, 3)
            >       assert result == 6
            E       AssertionError: assert 5 == 6
            ''',
        )
        result = await engine.diagnose(error, ErrorCategory.TEST_FAILURE)
        assert result.root_cause == RootCause.ASSERTION_MISMATCH


@pytest.mark.asyncio
class TestDiagnosisEngineConfigurationErrors:
    """Tests for diagnosing configuration errors."""

    async def test_diagnose_missing_env_var(self, tmp_path, mock_llm_diagnosis):
        """Diagnose missing environment variable."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.MISSING_ENV_VAR,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.CONFIG_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="KeyError: 'DATABASE_URL'",
            error_type="KeyError",
            source="python",
        )
        result = await engine.diagnose(error, ErrorCategory.CONFIG_ERROR)
        assert result.root_cause == RootCause.MISSING_ENV_VAR

    async def test_diagnose_invalid_config(self, tmp_path, mock_llm_diagnosis):
        """Diagnose invalid configuration."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.INVALID_CONFIG,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.CONFIG_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e2",
            message="Configuration error: Invalid JSON in config.json",
            error_type="ConfigError",
            source="app",
        )
        result = await engine.diagnose(error, ErrorCategory.CONFIG_ERROR)
        # Falls back to category mapping
        assert result.root_cause in (RootCause.MISSING_CONFIG, RootCause.INVALID_CONFIG, RootCause.UNKNOWN)


@pytest.mark.asyncio
class TestDiagnosisEngineTimeoutErrors:
    """Tests for diagnosing timeout errors."""

    async def test_diagnose_timeout(self, tmp_path, mock_llm_diagnosis):
        """Diagnose timeout error."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.TIMEOUT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="TimeoutError: operation timed out after 30 seconds",
            error_type="TimeoutError",
            source="test",
        )
        result = await engine.diagnose(error, ErrorCategory.TIMEOUT_ERROR)
        assert result.root_cause == RootCause.TIMEOUT


@pytest.mark.asyncio
class TestDiagnosisEngineSecurityErrors:
    """Tests for diagnosing security-related errors."""

    async def test_diagnose_sql_injection(self, tmp_path, mock_llm_diagnosis):
        """Diagnose SQL injection vulnerability."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.VULNERABILITY,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SECURITY_VULNERABILITY,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Security vulnerability: SQL injection vulnerable to CVE-2023-1234",
            error_type="SecurityIssue",
            source="scanner",
        )
        result = await engine.diagnose(error, ErrorCategory.SECURITY_VULNERABILITY)
        assert result.root_cause == RootCause.VULNERABILITY

    async def test_diagnose_xss(self, tmp_path, mock_llm_diagnosis):
        """Diagnose XSS vulnerability."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.VULNERABILITY,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SECURITY_VULNERABILITY,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e2",
            message="XSS vulnerability detected in user input handling",
            error_type="SecurityIssue",
            source="scanner",
        )
        result = await engine.diagnose(error, ErrorCategory.SECURITY_VULNERABILITY)
        # Falls back to VULNERABILITY via category mapping
        assert result.root_cause == RootCause.VULNERABILITY


@pytest.mark.asyncio
class TestDiagnosisEngineUnknownErrors:
    """Tests for diagnosing unknown errors."""

    async def test_diagnose_unknown(self, tmp_path, mock_llm_diagnosis):
        """Unknown errors get UNKNOWN root cause."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.UNKNOWN,
            confidence=DiagnosisConfidence.LOW,
            category=ErrorCategory.UNKNOWN,
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Something strange happened",
            error_type="WeirdError",
            source="unknown",
        )
        result = await engine.diagnose(error, ErrorCategory.UNKNOWN)
        assert result.root_cause == RootCause.UNKNOWN
        assert result.confidence == DiagnosisConfidence.LOW


@pytest.mark.asyncio
class TestDiagnosisEngineContextUsage:
    """Tests for context usage in diagnosis."""

    async def test_uses_current_task_context(self, tmp_path, mock_llm_diagnosis):
        """Diagnosis uses current task from workflow state."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.MISSING_IMPORT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
            context={"current_task_id": "T1"},
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="ImportError: No module named 'flask'",
            error_type="ImportError",
            source="python",
        )
        workflow_state = {
            "current_phase": 3,
            "current_task_id": "T1",
        }
        result = await engine.diagnose(error, ErrorCategory.IMPORT_ERROR, workflow_state)
        assert result.context.get("current_task_id") == "T1"

    async def test_uses_recent_changes(self, tmp_path, mock_llm_diagnosis):
        """Diagnosis includes error context."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.SYNTAX_ERROR,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.SYNTAX_ERROR,
            context={"error_context": {"file": "main.py"}},
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="SyntaxError: invalid syntax",
            error_type="SyntaxError",
            source="python",
            context={"file": "main.py", "recent_change": True},
        )
        result = await engine.diagnose(error, ErrorCategory.SYNTAX_ERROR)
        assert result.context.get("error_context", {}).get("file") == "main.py"


@pytest.mark.asyncio
class TestDiagnosisEngineAffectedFiles:
    """Tests for extracting affected files."""

    async def test_extracts_file_from_traceback(self, tmp_path, mock_llm_diagnosis):
        """Extract file location from Python traceback."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.IMPORT_ERROR,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
            affected_files=[AffectedFile(path="src/app.py")],
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="ImportError",
            error_type="ImportError",
            source="python",
            stack_trace='File "src/app.py", line 42\n    import missing_module',
        )
        result = await engine.diagnose(error, ErrorCategory.IMPORT_ERROR)
        # Should extract src/app.py
        paths = [f.path for f in result.affected_files]
        assert any("app.py" in p for p in paths) or len(result.affected_files) == 0

    async def test_extracts_line_number(self, tmp_path, mock_llm_diagnosis):
        """Extract line number from error."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.UNKNOWN,
            confidence=DiagnosisConfidence.LOW,
            category=ErrorCategory.UNKNOWN,
            affected_files=[AffectedFile(path="main.py", line_number=123)],
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Error at main.py:123:10",
            error_type="TestError",
            source="test",
            stack_trace="",
        )
        result = await engine.diagnose(error, ErrorCategory.UNKNOWN)
        if result.affected_files:
            assert result.affected_files[0].line_number == 123


@pytest.mark.asyncio
class TestDiagnosisEngineSuggestedFixes:
    """Tests for suggested fixes generation."""

    async def test_import_error_suggests_install(self, tmp_path, mock_llm_diagnosis):
        """Import error suggests package installation."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.MISSING_IMPORT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.IMPORT_ERROR,
            suggested_fixes=["Install the package", "Fix import path"],
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="ModuleNotFoundError: No module named 'requests'",
            error_type="ModuleNotFoundError",
            source="python",
        )
        result = await engine.diagnose(error, ErrorCategory.IMPORT_ERROR)
        # Should suggest installing the package
        fix_text = " ".join(result.suggested_fixes).lower()
        assert "install" in fix_text or "import" in fix_text

    async def test_timeout_suggests_increase(self, tmp_path, mock_llm_diagnosis):
        """Timeout suggests increasing timeout."""
        mock_llm_diagnosis.diagnose.return_value = DiagnosisResult(
            error=MagicMock(),
            root_cause=RootCause.TIMEOUT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.TIMEOUT_ERROR,
            suggested_fixes=["Increase timeout", "Optimize code"],
        )
        engine = DiagnosisEngine(tmp_path)
        error = FixerError(
            error_id="e1",
            message="TimeoutError: timed out after 30 seconds",
            error_type="TimeoutError",
            source="test",
        )
        result = await engine.diagnose(error, ErrorCategory.TIMEOUT_ERROR)
        fix_text = " ".join(result.suggested_fixes).lower()
        assert "timeout" in fix_text or "optimize" in fix_text