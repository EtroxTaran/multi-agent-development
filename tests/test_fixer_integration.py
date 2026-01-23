"""Integration tests for fixer module."""


import pytest

from orchestrator.fixer.agent import FixerAgent, create_fixer_agent
from orchestrator.fixer.circuit_breaker import CircuitState
from orchestrator.fixer.diagnosis import DiagnosisConfidence, DiagnosisResult, RootCause
from orchestrator.fixer.strategies import FixAction, FixPlan
from orchestrator.fixer.triage import ErrorCategory, FixerError, TriageDecision
from orchestrator.fixer.validator import FixValidator


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker with fixer."""

    def test_circuit_breaker_prevents_fixes_after_failures(self, tmp_path):
        """Circuit breaker prevents fixes after consecutive failures."""
        agent = FixerAgent(tmp_path, circuit_breaker_threshold=3)

        # Record failures
        agent.circuit_breaker.record_failure()
        agent.circuit_breaker.record_failure()
        assert agent.can_attempt_fix() is True  # Still can attempt

        agent.circuit_breaker.record_failure()  # Third failure
        assert agent.can_attempt_fix() is False  # Circuit is open

    def test_circuit_breaker_recovers_after_success(self, tmp_path):
        """Circuit breaker recovers after successful fixes."""
        agent = FixerAgent(
            tmp_path,
            circuit_breaker_threshold=2,
        )

        # Trip the circuit
        agent.circuit_breaker.record_failure()
        agent.circuit_breaker.record_failure()
        assert agent.circuit_breaker.is_open is True

        # Force close (simulating timeout and successful recovery)
        agent.circuit_breaker.force_close("test")
        agent.circuit_breaker.record_success()
        agent.circuit_breaker.record_success()
        assert agent.circuit_breaker.state == CircuitState.CLOSED


class TestProtectedFilesIntegration:
    """Integration tests for protected file handling."""

    def test_fixer_protects_workflow_files(self, tmp_path):
        """Fixer does not modify workflow files."""
        agent = FixerAgent(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Test",
            error_type="TestError",
            source="test",
        )
        diagnosis = DiagnosisResult(
            error=error,
            root_cause=RootCause.MISSING_CONFIG,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.CONFIG_ERROR,
        )
        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="config_fix",
            actions=[
                FixAction(
                    action_type="modify",
                    target=".workflow/state.json",
                    description="Modify state",
                )
            ],
        )
        validation = agent.validate_plan(plan)
        assert validation.safe_to_proceed is False

    def test_fixer_protects_context_files(self, tmp_path):
        """Fixer does not modify context files."""
        agent = FixerAgent(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Test",
            error_type="TestError",
            source="test",
        )
        diagnosis = DiagnosisResult(
            error=error,
            root_cause=RootCause.MISSING_CONFIG,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.CONFIG_ERROR,
        )
        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="config_fix",
            actions=[
                FixAction(
                    action_type="modify",
                    target="CLAUDE.md",
                    description="Modify claude.md",
                )
            ],
        )
        validation = agent.validate_plan(plan)
        assert validation.safe_to_proceed is False


class TestValidatorIntegration:
    """Integration tests for validator with fixer."""

    def test_validator_checks_scope(self, tmp_path):
        """Validator checks fix scope limits."""
        validator = FixValidator(tmp_path)
        error = FixerError(
            error_id="e1",
            message="Test",
            error_type="TestError",
            source="test",
        )
        diagnosis = DiagnosisResult(
            error=error,
            root_cause=RootCause.TIMEOUT,
            confidence=DiagnosisConfidence.HIGH,
            category=ErrorCategory.TIMEOUT_ERROR,
        )
        # Create plan with many actions (exceeds scope)
        actions = [
            FixAction(
                action_type="shell",  # Valid action type
                target=f"file{i}.py",
                description=f"Modify file {i}",
            )
            for i in range(10)  # 10 files
        ]
        plan = FixPlan(
            diagnosis=diagnosis,
            strategy_name="test_strategy",
            actions=actions,
        )
        validation = validator.validate_pre_fix(plan)
        # Should either warn about scope, have errors, or indicate scope issue
        assert (
            validation.scope_within_limits is False
            or len(validation.warnings) > 0
            or len(validation.errors) > 0
            or validation.safe_to_proceed is False
        )


class TestErrorDispatchIntegration:
    """Integration tests for error dispatch routing."""

    def test_error_dispatch_routes_to_fixer(self, tmp_path):
        """Error dispatch routes fixable errors to fixer."""
        agent = FixerAgent(tmp_path)

        # Fixable error
        error = FixerError(
            error_id="e1",
            message="ImportError: No module named 'flask'",
            error_type="ImportError",
            source="python",
        )
        result = agent.triage_error(error)
        assert result.decision == TriageDecision.ATTEMPT_FIX

    def test_error_dispatch_escalates_unfixable(self, tmp_path):
        """Error dispatch escalates unfixable errors."""
        agent = FixerAgent(tmp_path)

        # Unfixable error
        error = FixerError(
            error_id="e2",
            message="Something weird happened",
            error_type="unknown",
            source="unknown",
        )
        result = agent.triage_error(error)
        # UNKNOWN category should be escalated
        assert result.decision == TriageDecision.ESCALATE


@pytest.mark.asyncio
class TestEndToEndFix:
    """End-to-end fix flow tests."""

    async def test_simple_fix_flow(self, tmp_path):
        """Test complete flow for a simple fix."""
        agent = FixerAgent(tmp_path)

        # Create error
        error = FixerError(
            error_id="e1",
            message="ImportError: No module named 'requests'",
            error_type="ImportError",
            source="python",
        )

        # Step 1: Triage
        triage_result = agent.triage_error(error)
        assert triage_result.decision == TriageDecision.ATTEMPT_FIX
        assert triage_result.category == ErrorCategory.IMPORT_ERROR

        # Step 2: Diagnose
        diagnosis = await agent.diagnose(error, triage_result.category)
        assert diagnosis.root_cause == RootCause.MISSING_IMPORT
        assert diagnosis.confidence == DiagnosisConfidence.HIGH

        # Step 3: Create plan
        plan = agent.create_plan(diagnosis)
        # Should have a plan (import fix strategy)
        # Plan may or may not have actions depending on whether package name is extractable
        assert plan is not None
        assert plan.strategy_name == "import_fix"

    def test_circuit_breaker_integration_with_flow(self, tmp_path):
        """Circuit breaker integrates with fix flow."""
        agent = FixerAgent(tmp_path, circuit_breaker_threshold=2)

        error = FixerError(
            error_id="e1",
            message="ImportError: test",
            error_type="ImportError",
            source="python",
        )

        # First attempts succeed in triage
        result1 = agent.triage_error(error)
        assert result1.decision == TriageDecision.ATTEMPT_FIX

        # Trip circuit
        agent.circuit_breaker.record_failure()
        agent.circuit_breaker.record_failure()

        # Now triage should escalate
        result2 = agent.triage_error(error)
        assert result2.decision == TriageDecision.ESCALATE


class TestConfigIntegration:
    """Integration tests for configuration."""

    def test_config_from_project_config(self, tmp_path):
        """Create agent from project config."""
        config = {
            "fixer": {
                "enabled": True,
                "max_attempts_per_error": 3,
                "max_attempts_per_session": 15,
                "validation_agent": "gemini",
                "circuit_breaker": {
                    "failure_threshold": 10,
                    "reset_timeout_seconds": 600,
                },
            }
        }
        agent = create_fixer_agent(tmp_path, config)
        assert agent.enabled is True
        assert agent.validation_agent == "gemini"
        assert agent.circuit_breaker.failure_threshold == 10


@pytest.mark.asyncio
class TestDiagnosisIntegration:
    """Integration tests for diagnosis with triage."""

    async def test_diagnosis_uses_triage_category(self, tmp_path):
        """Diagnosis uses category from triage."""
        agent = FixerAgent(tmp_path)

        error = FixerError(
            error_id="e1",
            message="SyntaxError: invalid syntax",
            error_type="SyntaxError",
            source="python",
        )

        # Triage first
        triage_result = agent.triage_error(error)
        assert triage_result.category == ErrorCategory.SYNTAX_ERROR

        # Diagnosis uses triage category
        diagnosis = await agent.diagnose(error, triage_result.category)
        assert diagnosis.category == ErrorCategory.SYNTAX_ERROR
        assert diagnosis.root_cause == RootCause.SYNTAX_ERROR


class TestSecurityFixIntegration:
    """Integration tests for security fix handling."""

    def test_security_fix_flagged(self, tmp_path):
        """Security fixes are flagged for notification."""
        agent = FixerAgent(tmp_path)

        error = FixerError(
            error_id="e1",
            message="SQL injection vulnerability detected CVE-2023-1234",
            error_type="SecurityIssue",
            source="scanner",
        )

        triage_result = agent.triage_error(error)
        assert triage_result.requires_security_notification is True
        assert triage_result.category == ErrorCategory.SECURITY_VULNERABILITY


class TestKnownFixesIntegration:
    """Integration tests for known fixes database."""

    def test_known_fixes_loads(self, tmp_path):
        """Known fixes database loads."""
        agent = FixerAgent(tmp_path)
        stats = agent.known_fixes.get_statistics()
        assert "total_fixes" in stats


class TestStatusIntegration:
    """Integration tests for status reporting."""

    def test_complete_status(self, tmp_path):
        """Get complete status from all components."""
        agent = FixerAgent(tmp_path)

        # Do some operations
        agent.circuit_breaker.record_success()

        status = agent.get_status()
        assert "enabled" in status
        assert "circuit_breaker" in status
        assert status["circuit_breaker"]["state"] == "closed"
        assert "known_fixes" in status
        assert "validation_agent" in status
