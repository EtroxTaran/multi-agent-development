"""Tests for verification strategy layer.

Tests the pluggable verification strategies (tests, lint, security)
used by the unified loop runner.
"""

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.langgraph.integrations.verification import (
    CompositeVerification,
    LintVerification,
    NoVerification,
    SecurityVerification,
    TestVerification,
    VerificationContext,
    VerificationResult,
    VerificationType,
    create_composite_verifier,
    create_verifier,
)


class TestVerificationType:
    """Tests for VerificationType enum."""

    def test_verification_types_exist(self):
        """Test that all expected verification types exist."""
        assert VerificationType.TESTS == "tests"
        assert VerificationType.LINT == "lint"
        assert VerificationType.SECURITY == "security"
        assert VerificationType.COMPOSITE == "composite"
        assert VerificationType.NONE == "none"

    def test_verification_type_from_string(self):
        """Test creating VerificationType from string."""
        assert VerificationType("tests") == VerificationType.TESTS
        assert VerificationType("lint") == VerificationType.LINT


class TestVerificationContext:
    """Tests for VerificationContext dataclass."""

    def test_default_context(self, tmp_path):
        """Test default context values."""
        ctx = VerificationContext(project_dir=tmp_path)
        assert ctx.project_dir == tmp_path
        assert ctx.test_files == []
        assert ctx.source_files == []
        assert ctx.timeout == 60

    def test_custom_context(self, tmp_path):
        """Test context with custom values."""
        ctx = VerificationContext(
            project_dir=tmp_path,
            test_files=["test_foo.py"],
            source_files=["foo.py"],
            task_id="T1",
            iteration=3,
            timeout=120,
        )
        assert ctx.test_files == ["test_foo.py"]
        assert ctx.task_id == "T1"
        assert ctx.iteration == 3
        assert ctx.timeout == 120


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_passed_result(self):
        """Test creating a passed result."""
        result = VerificationResult(
            passed=True,
            verification_type=VerificationType.TESTS,
            summary="All tests passed",
        )
        assert result.passed is True
        assert result.verification_type == VerificationType.TESTS
        assert result.failures == []

    def test_failed_result(self):
        """Test creating a failed result."""
        result = VerificationResult(
            passed=False,
            verification_type=VerificationType.LINT,
            summary="2 errors found",
            failures=["error1", "error2"],
        )
        assert result.passed is False
        assert len(result.failures) == 2

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = VerificationResult(
            passed=True,
            verification_type=VerificationType.TESTS,
            summary="5 passed",
            warnings=["deprecation warning"],
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["verification_type"] == "tests"
        assert d["summary"] == "5 passed"
        assert "timestamp" in d


class TestTestVerification:
    """Tests for TestVerification strategy."""

    def test_verification_type(self, tmp_path):
        """Test verification type is tests."""
        verifier = TestVerification(tmp_path)
        assert verifier.verification_type == VerificationType.TESTS

    @pytest.mark.asyncio
    async def test_verify_passes(self, tmp_path):
        """Test verification when tests pass."""
        verifier = TestVerification(tmp_path)
        ctx = VerificationContext(
            project_dir=tmp_path,
            test_files=["test_foo.py"],
        )

        with patch.object(verifier, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "===== 5 passed in 0.1s =====", "")

            result = await verifier.verify(ctx)

            assert result.passed is True
            assert "5 passed" in result.summary

    @pytest.mark.asyncio
    async def test_verify_fails(self, tmp_path):
        """Test verification when tests fail."""
        verifier = TestVerification(tmp_path)
        ctx = VerificationContext(
            project_dir=tmp_path,
            test_files=["test_foo.py"],
        )

        with patch.object(verifier, "_run_command") as mock_run:
            mock_run.return_value = (1, "FAILED test_foo.py::test_bar", "")

            result = await verifier.verify(ctx)

            assert result.passed is False
            assert len(result.failures) > 0

    @pytest.mark.asyncio
    async def test_no_test_files_runs_discovery(self, tmp_path):
        """Test verification with no test files runs pytest discovery."""
        verifier = TestVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        # When no test files, pytest runs discovery and may pass or fail
        # depending on what it finds. Here we mock a successful discovery.
        with patch.object(verifier, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "===== 3 passed in 0.5s =====", "")

            result = await verifier.verify(ctx)

            assert result.passed is True
            mock_run.assert_called_once()

    def test_detect_pytest(self, tmp_path):
        """Test pytest detection."""
        (tmp_path / "pytest.ini").touch()
        verifier = TestVerification(tmp_path)
        cmd = verifier._detect_test_framework()
        assert "pytest" in cmd

    def test_detect_jest(self, tmp_path):
        """Test jest detection."""
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')
        verifier = TestVerification(tmp_path)
        cmd = verifier._detect_test_framework()
        assert "npm" in cmd

    def test_detect_cargo(self, tmp_path):
        """Test cargo test detection."""
        (tmp_path / "Cargo.toml").touch()
        verifier = TestVerification(tmp_path)
        cmd = verifier._detect_test_framework()
        assert "cargo test" in cmd


class TestLintVerification:
    """Tests for LintVerification strategy."""

    def test_verification_type(self, tmp_path):
        """Test verification type is lint."""
        verifier = LintVerification(tmp_path)
        assert verifier.verification_type == VerificationType.LINT

    @pytest.mark.asyncio
    async def test_verify_passes(self, tmp_path):
        """Test verification when lint passes."""
        verifier = LintVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        with patch.object(verifier, "_run_command") as mock_run:
            mock_run.return_value = (0, "", "")

            result = await verifier.verify(ctx)

            assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_fails(self, tmp_path):
        """Test verification when lint fails."""
        verifier = LintVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        with patch.object(verifier, "_run_command") as mock_run:
            mock_run.return_value = (
                1,
                "foo.py:10:1: E501 line too long",
                "",
            )

            result = await verifier.verify(ctx)

            assert result.passed is False


class TestSecurityVerification:
    """Tests for SecurityVerification strategy."""

    def test_verification_type(self, tmp_path):
        """Test verification type is security."""
        verifier = SecurityVerification(tmp_path)
        assert verifier.verification_type == VerificationType.SECURITY

    @pytest.mark.asyncio
    async def test_verify_passes(self, tmp_path):
        """Test verification when security scan passes."""
        (tmp_path / "pyproject.toml").touch()
        verifier = SecurityVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/bandit"
            with patch.object(verifier, "_run_command") as mock_run:
                mock_run.return_value = (0, "No issues found", "")

                result = await verifier.verify(ctx)

                assert result.passed is True

    @pytest.mark.asyncio
    async def test_no_scanner_configured(self, tmp_path):
        """Test when no security scanner is available."""
        verifier = SecurityVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            result = await verifier.verify(ctx)

            # Should pass with warning
            assert result.passed is True
            assert "No security scanner" in result.summary


class TestCompositeVerification:
    """Tests for CompositeVerification strategy."""

    def test_verification_type(self, tmp_path):
        """Test verification type is composite."""
        verifier = CompositeVerification(tmp_path)
        assert verifier.verification_type == VerificationType.COMPOSITE

    @pytest.mark.asyncio
    async def test_all_pass(self, tmp_path):
        """Test when all strategies pass."""
        test_verifier = TestVerification(tmp_path)
        lint_verifier = LintVerification(tmp_path)

        composite = CompositeVerification(
            tmp_path,
            strategies=[test_verifier, lint_verifier],
            require_all=True,
        )

        ctx = VerificationContext(project_dir=tmp_path)

        with patch.object(test_verifier, "verify") as mock_test:
            mock_test.return_value = VerificationResult(
                passed=True,
                verification_type=VerificationType.TESTS,
                summary="5 passed",
            )
            with patch.object(lint_verifier, "verify") as mock_lint:
                mock_lint.return_value = VerificationResult(
                    passed=True,
                    verification_type=VerificationType.LINT,
                    summary="No errors",
                )

                result = await composite.verify(ctx)

                assert result.passed is True

    @pytest.mark.asyncio
    async def test_one_fails_require_all(self, tmp_path):
        """Test when one strategy fails with require_all=True."""
        test_verifier = TestVerification(tmp_path)
        lint_verifier = LintVerification(tmp_path)

        composite = CompositeVerification(
            tmp_path,
            strategies=[test_verifier, lint_verifier],
            require_all=True,
        )

        ctx = VerificationContext(project_dir=tmp_path)

        with patch.object(test_verifier, "verify") as mock_test:
            mock_test.return_value = VerificationResult(
                passed=True,
                verification_type=VerificationType.TESTS,
                summary="5 passed",
            )
            with patch.object(lint_verifier, "verify") as mock_lint:
                mock_lint.return_value = VerificationResult(
                    passed=False,
                    verification_type=VerificationType.LINT,
                    summary="2 errors",
                    failures=["error1", "error2"],
                )

                result = await composite.verify(ctx)

                assert result.passed is False

    @pytest.mark.asyncio
    async def test_one_passes_require_any(self, tmp_path):
        """Test when one strategy passes with require_all=False."""
        test_verifier = TestVerification(tmp_path)
        lint_verifier = LintVerification(tmp_path)

        composite = CompositeVerification(
            tmp_path,
            strategies=[test_verifier, lint_verifier],
            require_all=False,
        )

        ctx = VerificationContext(project_dir=tmp_path)

        with patch.object(test_verifier, "verify") as mock_test:
            mock_test.return_value = VerificationResult(
                passed=True,
                verification_type=VerificationType.TESTS,
                summary="5 passed",
            )
            with patch.object(lint_verifier, "verify") as mock_lint:
                mock_lint.return_value = VerificationResult(
                    passed=False,
                    verification_type=VerificationType.LINT,
                    summary="2 errors",
                )

                result = await composite.verify(ctx)

                assert result.passed is True

    @pytest.mark.asyncio
    async def test_no_strategies(self, tmp_path):
        """Test with no strategies configured."""
        composite = CompositeVerification(tmp_path, strategies=[])
        ctx = VerificationContext(project_dir=tmp_path)

        result = await composite.verify(ctx)

        assert result.passed is True
        assert "No verification strategies" in result.summary

    def test_add_strategy(self, tmp_path):
        """Test adding strategies dynamically."""
        composite = CompositeVerification(tmp_path)
        assert len(composite.strategies) == 0

        composite.add_strategy(TestVerification(tmp_path))
        assert len(composite.strategies) == 1


class TestNoVerification:
    """Tests for NoVerification strategy."""

    def test_verification_type(self, tmp_path):
        """Test verification type is none."""
        verifier = NoVerification(tmp_path)
        assert verifier.verification_type == VerificationType.NONE

    @pytest.mark.asyncio
    async def test_always_passes(self, tmp_path):
        """Test that NoVerification always passes."""
        verifier = NoVerification(tmp_path)
        ctx = VerificationContext(project_dir=tmp_path)

        result = await verifier.verify(ctx)

        assert result.passed is True
        assert "No verification required" in result.summary


class TestCreateVerifier:
    """Tests for create_verifier factory function."""

    def test_create_test_verifier(self, tmp_path):
        """Test creating test verifier."""
        verifier = create_verifier(VerificationType.TESTS, tmp_path)
        assert isinstance(verifier, TestVerification)

    def test_create_lint_verifier(self, tmp_path):
        """Test creating lint verifier."""
        verifier = create_verifier(VerificationType.LINT, tmp_path)
        assert isinstance(verifier, LintVerification)

    def test_create_security_verifier(self, tmp_path):
        """Test creating security verifier."""
        verifier = create_verifier(VerificationType.SECURITY, tmp_path)
        assert isinstance(verifier, SecurityVerification)

    def test_create_none_verifier(self, tmp_path):
        """Test creating no-op verifier."""
        verifier = create_verifier(VerificationType.NONE, tmp_path)
        assert isinstance(verifier, NoVerification)

    def test_create_composite_verifier(self, tmp_path):
        """Test creating composite verifier."""
        verifier = create_verifier(VerificationType.COMPOSITE, tmp_path)
        assert isinstance(verifier, CompositeVerification)

    def test_create_verifier_from_string(self, tmp_path):
        """Test creating verifier from string."""
        verifier = create_verifier("tests", tmp_path)
        assert isinstance(verifier, TestVerification)

    def test_create_verifier_with_timeout(self, tmp_path):
        """Test creating verifier with timeout."""
        verifier = create_verifier("tests", tmp_path, timeout=120)
        assert verifier.timeout == 120

    def test_invalid_type_raises(self, tmp_path):
        """Test that invalid type raises ValueError."""
        with pytest.raises(ValueError):
            create_verifier("invalid", tmp_path)


class TestCreateCompositeVerifier:
    """Tests for create_composite_verifier function."""

    def test_default_strategies(self, tmp_path):
        """Test default composite verifier has tests and lint."""
        verifier = create_composite_verifier(tmp_path)
        assert len(verifier.strategies) == 2
        types = [s.verification_type for s in verifier.strategies]
        assert VerificationType.TESTS in types
        assert VerificationType.LINT in types

    def test_include_security(self, tmp_path):
        """Test including security verification."""
        verifier = create_composite_verifier(tmp_path, include_security=True)
        assert len(verifier.strategies) == 3
        types = [s.verification_type for s in verifier.strategies]
        assert VerificationType.SECURITY in types

    def test_exclude_tests(self, tmp_path):
        """Test excluding test verification."""
        verifier = create_composite_verifier(tmp_path, include_tests=False)
        types = [s.verification_type for s in verifier.strategies]
        assert VerificationType.TESTS not in types

    def test_require_all_setting(self, tmp_path):
        """Test require_all setting."""
        verifier = create_composite_verifier(tmp_path, require_all=False)
        assert verifier.require_all is False
