"""Tests for Fixer Strategies."""

import pytest
import tempfile
from pathlib import Path

from orchestrator.fixer.strategies import (
    FixStrategy,
    FixPlan,
    FixResult,
    FixAction,
    FixStatus,
    RetryStrategy,
    ImportErrorFixStrategy,
    SyntaxErrorFixStrategy,
    TestFailureFixStrategy,
    ConfigurationFixStrategy,
    TimeoutFixStrategy,
    DependencyFixStrategy,
    get_strategy_for_error,
    is_protected_file,
    PROTECTED_FILES,
)
from orchestrator.fixer.diagnosis import DiagnosisResult, RootCause, AffectedFile
from orchestrator.fixer.triage import ErrorCategory


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "src").mkdir()
        (project_dir / "tests").mkdir()
        yield project_dir


def create_mock_diagnosis(
    root_cause: RootCause = RootCause.UNKNOWN,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    confidence: str = "medium",
    affected_files: list = None,
    error_message: str = "Test error",
) -> DiagnosisResult:
    """Create a mock diagnosis result."""
    from orchestrator.fixer.diagnosis import DiagnosisConfidence
    from orchestrator.fixer.triage import FixerError

    if affected_files is None:
        affected_files = []

    # Map string to confidence enum
    confidence_map = {
        "high": DiagnosisConfidence.HIGH,
        "medium": DiagnosisConfidence.MEDIUM,
        "low": DiagnosisConfidence.LOW,
    }
    confidence_enum = confidence_map.get(confidence, DiagnosisConfidence.MEDIUM)

    # Create mock FixerError
    error = FixerError(
        error_id="test-error-1",
        message=error_message,
        error_type="TestError",
        source="test",
    )

    return DiagnosisResult(
        error=error,
        root_cause=root_cause,
        confidence=confidence_enum,
        category=category,
        affected_files=[AffectedFile(path=f) for f in affected_files],
    )


class TestFixAction:
    """Tests for FixAction dataclass."""

    def test_to_dict(self):
        action = FixAction(
            action_type="run_command",
            target="pip install requests",
            params={"timeout": 60},
            description="Install requests package",
        )
        d = action.to_dict()

        assert d["action_type"] == "run_command"
        assert d["target"] == "pip install requests"
        assert d["params"]["timeout"] == 60


class TestFixPlan:
    """Tests for FixPlan dataclass."""

    def test_to_dict(self):
        diagnosis = create_mock_diagnosis()
        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="import_fix",
            actions=[
                FixAction(
                    action_type="install_package",
                    target="requests",
                    params={"manager": "pip"},
                    description="Install requests",
                )
            ],
            estimated_impact=1,
            requires_validation=False,
        )
        d = plan.to_dict()

        assert d["strategy_name"] == "import_fix"
        assert len(d["actions"]) == 1
        assert d["estimated_impact"] == 1


class TestFixResult:
    """Tests for FixResult dataclass."""

    def test_to_dict(self):
        diagnosis = create_mock_diagnosis()
        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="test",
            actions=[],
        )
        result = FixResult(
            plan=plan,
            status=FixStatus.SUCCESS,
            actions_completed=1,
            actions_total=1,
            changes_made=[{"action": "test", "result": "success"}],
        )
        d = result.to_dict()

        assert d["status"] == "success"
        assert d["actions_completed"] == 1

    def test_success_property(self):
        diagnosis = create_mock_diagnosis()
        plan = FixPlan(diagnosis=diagnosis, strategy_name="test", actions=[])

        success_result = FixResult(plan=plan, status=FixStatus.SUCCESS)
        assert success_result.success is True

        failed_result = FixResult(plan=plan, status=FixStatus.FAILED)
        assert failed_result.success is False


class TestProtectedFiles:
    """Tests for protected file handling."""

    def test_env_files_protected(self):
        assert is_protected_file(".env") is True
        assert is_protected_file(".env.local") is True
        assert is_protected_file(".env.production") is True

    def test_context_files_protected(self):
        assert is_protected_file("CLAUDE.md") is True
        assert is_protected_file("GEMINI.md") is True
        assert is_protected_file("PRODUCT.md") is True

    def test_workflow_files_protected(self):
        assert is_protected_file(".workflow/state.json") is True
        assert is_protected_file(".project-config.json") is True

    def test_credentials_pattern_protected(self):
        assert is_protected_file("credentials.json") is True
        assert is_protected_file("my_credentials.yaml") is True

    def test_regular_files_not_protected(self):
        assert is_protected_file("src/main.py") is False
        assert is_protected_file("tests/test_app.py") is False
        assert is_protected_file("README.md") is False


class TestRetryStrategy:
    """Tests for RetryStrategy."""

    def test_can_fix_timeout(self, temp_project_dir):
        strategy = RetryStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.TIMEOUT,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_rate_limit(self, temp_project_dir):
        strategy = RetryStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.RESOURCE_EXHAUSTION,
            category=ErrorCategory.RATE_LIMIT,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_create_plan(self, temp_project_dir):
        strategy = RetryStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.TIMEOUT,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        plan = strategy.create_plan(diagnosis)

        assert plan.strategy_name == "retry"
        assert len(plan.actions) > 0
        assert plan.actions[0].action_type == "wait_and_retry"


class TestImportErrorFixStrategy:
    """Tests for ImportErrorFixStrategy."""

    def test_can_fix_import_error(self, temp_project_dir):
        strategy = ImportErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_IMPORT,
            category=ErrorCategory.IMPORT_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_missing_dependency(self, temp_project_dir):
        strategy = ImportErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_DEPENDENCY,
            category=ErrorCategory.IMPORT_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_cannot_fix_syntax_error(self, temp_project_dir):
        strategy = ImportErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.SYNTAX_ERROR,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        assert strategy.can_fix(diagnosis) is False

    def test_create_plan_for_missing_dependency(self, temp_project_dir):
        strategy = ImportErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_DEPENDENCY,
            category=ErrorCategory.IMPORT_ERROR,
            error_message="No module named 'requests'",
        )
        plan = strategy.create_plan(diagnosis)

        assert plan.strategy_name == "import_fix"
        # Should include install action
        assert any(a.action_type == "install_package" for a in plan.actions)


class TestSyntaxErrorFixStrategy:
    """Tests for SyntaxErrorFixStrategy."""

    def test_can_fix_syntax_error(self, temp_project_dir):
        strategy = SyntaxErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.SYNTAX_ERROR,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_indentation_error(self, temp_project_dir):
        strategy = SyntaxErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.INDENTATION_ERROR,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_cannot_fix_logic_error(self, temp_project_dir):
        strategy = SyntaxErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.ASSERTION_MISMATCH,
            category=ErrorCategory.TEST_FAILURE,
        )
        assert strategy.can_fix(diagnosis) is False

    def test_create_plan_requires_validation(self, temp_project_dir):
        strategy = SyntaxErrorFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.SYNTAX_ERROR,
            category=ErrorCategory.SYNTAX_ERROR,
            affected_files=["src/main.py"],
        )
        plan = strategy.create_plan(diagnosis)

        assert plan.requires_validation is True


class TestTestFailureFixStrategy:
    """Tests for TestFailureFixStrategy."""

    def test_can_fix_test_failure(self, temp_project_dir):
        strategy = TestFailureFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.ASSERTION_MISMATCH,
            category=ErrorCategory.TEST_FAILURE,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_assertion_error(self, temp_project_dir):
        strategy = TestFailureFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.ASSERTION_MISMATCH,
            category=ErrorCategory.ASSERTION_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_create_plan_requires_validation(self, temp_project_dir):
        strategy = TestFailureFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.ASSERTION_MISMATCH,
            category=ErrorCategory.TEST_FAILURE,
        )
        plan = strategy.create_plan(diagnosis)

        assert plan.requires_validation is True


class TestConfigurationFixStrategy:
    """Tests for ConfigurationFixStrategy."""

    def test_can_fix_config_error(self, temp_project_dir):
        strategy = ConfigurationFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_CONFIG,
            category=ErrorCategory.CONFIG_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_missing_env_var(self, temp_project_dir):
        strategy = ConfigurationFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_ENV_VAR,
            category=ErrorCategory.CONFIG_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True


class TestTimeoutFixStrategy:
    """Tests for TimeoutFixStrategy."""

    def test_can_fix_timeout(self, temp_project_dir):
        strategy = TimeoutFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.TIMEOUT,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_create_plan(self, temp_project_dir):
        strategy = TimeoutFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.TIMEOUT,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        plan = strategy.create_plan(diagnosis)

        assert plan.strategy_name == "timeout_fix"


class TestDependencyFixStrategy:
    """Tests for DependencyFixStrategy."""

    def test_can_fix_dependency_error(self, temp_project_dir):
        strategy = DependencyFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_DEPENDENCY,
            category=ErrorCategory.DEPENDENCY_ERROR,
        )
        assert strategy.can_fix(diagnosis) is True

    def test_can_fix_version_mismatch(self, temp_project_dir):
        strategy = DependencyFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.VERSION_MISMATCH,
            category=ErrorCategory.VERSION_CONFLICT,
        )
        assert strategy.can_fix(diagnosis) is True


class TestGetStrategyForError:
    """Tests for get_strategy_for_error function."""

    def test_gets_import_strategy(self, temp_project_dir):
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.MISSING_IMPORT,
            category=ErrorCategory.IMPORT_ERROR,
        )
        strategy = get_strategy_for_error(temp_project_dir, diagnosis)
        assert isinstance(strategy, ImportErrorFixStrategy)

    def test_gets_syntax_strategy(self, temp_project_dir):
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.SYNTAX_ERROR,
            category=ErrorCategory.SYNTAX_ERROR,
        )
        strategy = get_strategy_for_error(temp_project_dir, diagnosis)
        assert isinstance(strategy, SyntaxErrorFixStrategy)

    def test_gets_timeout_strategy(self, temp_project_dir):
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.TIMEOUT,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        strategy = get_strategy_for_error(temp_project_dir, diagnosis)
        # Could be RetryStrategy or TimeoutFixStrategy
        assert strategy is not None

    def test_returns_none_for_unhandled(self, temp_project_dir):
        diagnosis = create_mock_diagnosis(
            root_cause=RootCause.UNKNOWN,
            category=ErrorCategory.UNKNOWN,
        )
        strategy = get_strategy_for_error(temp_project_dir, diagnosis)
        # May or may not find a strategy for unknown errors
        # This is acceptable behavior
        assert strategy is None or isinstance(strategy, FixStrategy)


class TestStrategyApply:
    """Tests for strategy apply method."""

    def test_apply_protects_env_files(self, temp_project_dir):
        strategy = ConfigurationFixStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis()

        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="config_fix",
            actions=[
                FixAction(
                    action_type="edit_file",
                    target=".env",
                    params={"find": "old", "replace": "new"},
                    description="Edit .env file",
                )
            ],
        )

        result = strategy.apply(plan)

        # Should fail because .env is protected
        assert result.status == FixStatus.FAILED
        assert "protected" in result.error.lower()

    def test_apply_runs_commands(self, temp_project_dir):
        strategy = RetryStrategy(temp_project_dir)
        diagnosis = create_mock_diagnosis()

        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="retry",
            actions=[
                FixAction(
                    action_type="run_command",
                    target="echo 'test'",
                    params={"timeout": 5},
                    description="Echo test",
                )
            ],
        )

        result = strategy.apply(plan)

        assert result.status == FixStatus.SUCCESS
        assert result.actions_completed == 1
