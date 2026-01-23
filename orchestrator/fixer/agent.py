"""Fixer Agent for self-healing workflow errors.

The FixerAgent is the main entry point for the fixer module. It coordinates
the triage, diagnosis, planning, and application of fixes.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..agents.base import BaseAgent, AgentResult
from .circuit_breaker import CircuitBreaker, CircuitState
from .diagnosis import DiagnosisEngine, DiagnosisResult
from .known_fixes import KnownFixDatabase
from .strategies import (
    FixPlan,
    FixResult,
    FixStatus,
    get_strategy_for_error,
)
from .triage import (
    ErrorTriage,
    TriageResult,
    TriageDecision,
    FixerError,
)
from .validator import FixValidator, PreValidation, PostValidation

logger = logging.getLogger(__name__)


@dataclass
class FixAttempt:
    """Record of a fix attempt.

    Attributes:
        error_id: ID of the error being fixed
        triage: Triage result
        diagnosis: Diagnosis result
        plan: Fix plan (if created)
        result: Fix result (if applied)
        pre_validation: Pre-fix validation
        post_validation: Post-fix validation
        security_notification_sent: Whether security notification was sent
        timestamp: When the attempt was made
    """

    error_id: str
    triage: TriageResult
    diagnosis: Optional[DiagnosisResult] = None
    plan: Optional[FixPlan] = None
    result: Optional[FixResult] = None
    pre_validation: Optional[PreValidation] = None
    post_validation: Optional[PostValidation] = None
    security_notification_sent: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "triage": self.triage.to_dict(),
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "result": self.result.to_dict() if self.result else None,
            "pre_validation": self.pre_validation.to_dict() if self.pre_validation else None,
            "post_validation": self.post_validation.to_dict() if self.post_validation else None,
            "security_notification_sent": self.security_notification_sent,
            "timestamp": self.timestamp,
        }


class FixerAgent(BaseAgent):
    """Self-healing agent for automatic error fixing.

    The FixerAgent intercepts errors before human escalation,
    diagnoses root causes, creates fix plans, and applies fixes
    automatically.

    Usage:
        fixer = FixerAgent(project_dir)

        # Full fix flow
        attempt = await fixer.attempt_fix(error, workflow_state)

        # Or step by step
        triage = fixer.triage_error(error)
        if triage.decision == TriageDecision.ATTEMPT_FIX:
            diagnosis = fixer.diagnose(error, triage.category)
            plan = fixer.create_plan(diagnosis)
            result = fixer.apply_fix(plan)
    """

    name = "fixer"

    def __init__(
        self,
        project_dir: str | Path,
        enabled: bool = True,
        max_attempts_per_error: int = 2,
        max_attempts_per_session: int = 10,
        validation_agent: str = "cursor",
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 300,
    ):
        """Initialize the fixer agent.

        Args:
            project_dir: Project directory
            enabled: Whether fixer is enabled (default True)
            max_attempts_per_error: Max fix attempts per error
            max_attempts_per_session: Max fix attempts per session
            validation_agent: Agent to use for fix validation
            circuit_breaker_threshold: Failures before circuit trips
            circuit_breaker_timeout: Seconds before circuit retry
        """
        super().__init__(project_dir)
        self.enabled = enabled
        self.validation_agent = validation_agent

        # Initialize components
        workflow_dir = self.project_dir / ".workflow"
        self.circuit_breaker = CircuitBreaker(
            workflow_dir,
            failure_threshold=circuit_breaker_threshold,
            reset_timeout_seconds=circuit_breaker_timeout,
        )
        self.triage = ErrorTriage(
            max_attempts_per_error=max_attempts_per_error,
            max_attempts_per_session=max_attempts_per_session,
        )
        self.diagnosis_engine = DiagnosisEngine(project_dir)
        self.known_fixes = KnownFixDatabase(workflow_dir)
        self.validator = FixValidator(project_dir)

        # Security notification log
        self.security_log_file = workflow_dir / "security_fixes.jsonl"

    def build_command(self, prompt: str, **kwargs) -> list[str]:
        """Build command for external agent calls (for validation)."""
        if self.validation_agent == "cursor":
            return ["cursor-agent", "--print", "--output-format", "json", prompt]
        else:
            return ["gemini", "--yolo", prompt]

    def get_cli_command(self) -> str:
        """Get CLI command name."""
        return self.validation_agent

    def can_attempt_fix(self) -> bool:
        """Check if a fix can be attempted.

        Returns:
            True if fixer is enabled and circuit breaker allows
        """
        if not self.enabled:
            return False
        return self.circuit_breaker.can_attempt()

    def triage_error(
        self,
        error: FixerError | dict,
        workflow_state: Optional[dict] = None,
    ) -> TriageResult:
        """Triage an error to determine if it should be fixed.

        Args:
            error: Error to triage (FixerError or dict)
            workflow_state: Current workflow state

        Returns:
            TriageResult with decision
        """
        # Convert dict to FixerError if needed
        if isinstance(error, dict):
            error = FixerError.from_dict(error)

        fixer_enabled = workflow_state.get("fixer_enabled", True) if workflow_state else self.enabled
        circuit_open = self.circuit_breaker.is_open
        fix_history = workflow_state.get("fix_history", []) if workflow_state else []

        return self.triage.triage(
            error=error,
            fixer_enabled=fixer_enabled,
            circuit_breaker_open=circuit_open,
            fix_history=fix_history,
        )

    async def diagnose(
        self,
        error: FixerError | dict,
        category=None,
        workflow_state: Optional[dict] = None,
    ) -> DiagnosisResult:
        """Diagnose an error to determine root cause.

        Args:
            error: Error to diagnose
            category: Error category (from triage)
            workflow_state: Current workflow state

        Returns:
            DiagnosisResult with root cause
        """
        if isinstance(error, dict):
            error = FixerError.from_dict(error)

        # If no category provided, triage first
        if category is None:
            triage_result = self.triage_error(error, workflow_state)
            category = triage_result.category

        return await self.diagnosis_engine.diagnose(error, category, workflow_state)

    def create_plan(
        self,
        diagnosis: DiagnosisResult,
        use_known_fixes: bool = True,
    ) -> Optional[FixPlan]:
        """Create a fix plan for the diagnosed error.

        Args:
            diagnosis: Diagnosis result
            use_known_fixes: Whether to check known fixes database

        Returns:
            FixPlan or None if no strategy found
        """
        # Check known fixes first
        if use_known_fixes:
            known_fix = self.known_fixes.find_matching_fix(diagnosis)
            if known_fix:
                logger.info(f"Found known fix: {known_fix.id}")
                # Create plan from known fix
                # (Known fixes are applied differently, this is handled in apply_fix)

        # Get appropriate strategy
        strategy = get_strategy_for_error(self.project_dir, diagnosis)
        if strategy is None:
            logger.warning(f"No strategy found for {diagnosis.category}")
            return None

        return strategy.create_plan(diagnosis)

    def validate_plan(self, plan: FixPlan) -> PreValidation:
        """Validate a fix plan before applying.

        Args:
            plan: Fix plan to validate

        Returns:
            PreValidation result
        """
        return self.validator.validate_pre_fix(plan)

    def apply_fix(self, plan: FixPlan) -> FixResult:
        """Apply a fix plan.

        Args:
            plan: Fix plan to apply

        Returns:
            FixResult with outcome
        """
        # Get strategy and apply
        strategy = get_strategy_for_error(self.project_dir, plan.diagnosis)
        if strategy is None:
            return FixResult(
                plan=plan,
                status=FixStatus.FAILED,
                error="No strategy found to apply fix",
            )

        result = strategy.apply(plan)

        # Update circuit breaker and known fixes
        if result.success:
            self.circuit_breaker.record_success()
            # Record in known fixes if this was a new fix
            self._record_successful_fix(plan)
        else:
            self.circuit_breaker.record_failure(result.error)

        return result

    def verify_fix(
        self,
        result: FixResult,
        original_error: dict,
        run_tests: bool = True,
    ) -> PostValidation:
        """Verify a fix was successful.

        Args:
            result: Fix result to verify
            original_error: Original error that was fixed
            run_tests: Whether to run tests

        Returns:
            PostValidation result
        """
        return self.validator.validate_post_fix(result, original_error, run_tests)

    async def attempt_fix(
        self,
        error: FixerError | dict,
        workflow_state: Optional[dict] = None,
        validate_with_agent: bool = False,
    ) -> FixAttempt:
        """Attempt to fix an error end-to-end.

        This is the main entry point for fixing errors. It:
        1. Triages the error
        2. Diagnoses root cause
        3. Creates a fix plan
        4. Validates the plan
        5. Applies the fix
        6. Verifies the result
        7. Handles security notifications

        Args:
            error: Error to fix
            workflow_state: Current workflow state
            validate_with_agent: Whether to validate plan with external agent

        Returns:
            FixAttempt record
        """
        if isinstance(error, dict):
            error = FixerError.from_dict(error)

        # Record attempt
        self.triage.record_attempt(error.error_id)

        # Step 1: Triage
        triage_result = self.triage_error(error, workflow_state)
        attempt = FixAttempt(
            error_id=error.error_id,
            triage=triage_result,
        )

        if triage_result.decision != TriageDecision.ATTEMPT_FIX:
            logger.info(f"Triage decision: {triage_result.decision} - {triage_result.reason}")
            return attempt

        # Step 2: Diagnose
        diagnosis = await self.diagnose(error, triage_result.category, workflow_state)
        attempt.diagnosis = diagnosis

        # Step 3: Create plan
        plan = self.create_plan(diagnosis)
        if plan is None:
            logger.warning("Could not create fix plan")
            return attempt
        attempt.plan = plan

        # Step 4: Pre-validation
        pre_validation = self.validate_plan(plan)
        attempt.pre_validation = pre_validation

        if not pre_validation.safe_to_proceed:
            logger.warning(f"Pre-validation failed: {pre_validation.errors}")
            self.circuit_breaker.record_failure("pre_validation_failed")
            return attempt

        # Step 4.5: Optional agent validation for complex fixes
        if validate_with_agent and plan.requires_validation:
            agent_validation = await self._validate_with_agent(plan)
            if not agent_validation.get("approved", False):
                logger.warning(f"Agent validation failed: {agent_validation.get('reason')}")
                return attempt

        # Step 5: Apply fix
        result = self.apply_fix(plan)
        attempt.result = result

        if not result.success:
            logger.warning(f"Fix application failed: {result.error}")
            return attempt

        # Step 6: Post-validation
        post_validation = self.verify_fix(result, error.to_dict())
        attempt.post_validation = post_validation

        # Step 7: Security notification
        if triage_result.requires_security_notification:
            await self._send_security_notification(attempt)
            attempt.security_notification_sent = True

        return attempt

    async def _validate_with_agent(self, plan: FixPlan) -> dict:
        """Validate a fix plan with an external agent.

        Args:
            plan: Fix plan to validate

        Returns:
            Validation result
        """
        prompt = f"""Review this fix plan and determine if it's safe to apply:

## Error
{plan.diagnosis.error.message}

## Root Cause
{plan.diagnosis.root_cause.value}

## Fix Actions
{json.dumps([a.to_dict() for a in plan.actions], indent=2)}

Respond with JSON:
{{"approved": true/false, "reason": "...", "concerns": [...]}}
"""

        result = self.run(prompt)

        if result.success and result.parsed_output:
            return result.parsed_output

        return {"approved": False, "reason": "Agent validation failed"}

    async def _send_security_notification(self, attempt: FixAttempt) -> None:
        """Send notification for security-related fixes.

        Args:
            attempt: Fix attempt with security fix
        """
        notification = {
            "type": "security_fix_applied",
            "timestamp": datetime.now().isoformat(),
            "error_id": attempt.error_id,
            "category": attempt.triage.category.value if attempt.triage else None,
            "root_cause": attempt.diagnosis.root_cause.value if attempt.diagnosis else None,
            "fix_description": attempt.plan.actions[0].description if attempt.plan and attempt.plan.actions else "Unknown",
            "files_changed": [a.target for a in (attempt.plan.actions if attempt.plan else [])],
            "verification_status": attempt.post_validation.status.value if attempt.post_validation else "unknown",
        }

        # Log to security fixes file
        self.security_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.security_log_file, "a") as f:
            f.write(json.dumps(notification) + "\n")

        # Console output (highlighted)
        logger.warning(
            f"\n{'='*60}\n"
            f"⚠️  SECURITY FIX APPLIED\n"
            f"{'='*60}\n"
            f"Error: {attempt.error_id}\n"
            f"Fix: {notification['fix_description']}\n"
            f"Files: {', '.join(notification['files_changed'])}\n"
            f"{'='*60}\n"
        )

    def _record_successful_fix(self, plan: FixPlan) -> None:
        """Record a successful fix in the known fixes database.

        Args:
            plan: Successfully applied fix plan
        """
        # If this came from a known fix, record success
        # Otherwise, consider adding it as a new known fix
        pass

    def get_status(self) -> dict:
        """Get fixer agent status.

        Returns:
            Status dictionary
        """
        return {
            "enabled": self.enabled,
            "circuit_breaker": self.circuit_breaker.get_status(),
            "known_fixes": self.known_fixes.get_statistics(),
            "validation_agent": self.validation_agent,
        }

    def reset(self) -> None:
        """Reset the fixer agent state."""
        self.circuit_breaker.reset()
        self.triage.reset_session()


def create_fixer_agent(
    project_dir: str | Path,
    config: Optional[dict] = None,
) -> FixerAgent:
    """Factory function to create a configured FixerAgent.

    Args:
        project_dir: Project directory
        config: Optional configuration from .project-config.json

    Returns:
        Configured FixerAgent
    """
    config = config or {}
    fixer_config = config.get("fixer", {})

    return FixerAgent(
        project_dir=project_dir,
        enabled=fixer_config.get("enabled", True),
        max_attempts_per_error=fixer_config.get("max_attempts_per_error", 2),
        max_attempts_per_session=fixer_config.get("max_attempts_per_session", 10),
        validation_agent=fixer_config.get("validation_agent", "cursor"),
        circuit_breaker_threshold=fixer_config.get("circuit_breaker", {}).get("failure_threshold", 5),
        circuit_breaker_timeout=fixer_config.get("circuit_breaker", {}).get("reset_timeout_seconds", 300),
    )
