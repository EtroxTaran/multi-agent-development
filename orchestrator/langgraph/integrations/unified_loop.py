"""Unified loop runner for all agents.

Provides a universal iterative loop pattern that works across all agents
(Claude, Cursor, Gemini). Combines:
- Agent adapters for CLI abstraction
- Verification strategies for validation
- Session management (Claude only)
- Error context for intelligent retries
- Budget control for cost management

Usage:
    from orchestrator.langgraph.integrations.unified_loop import (
        UnifiedLoopRunner,
        UnifiedLoopConfig,
    )

    config = UnifiedLoopConfig(
        agent_type="cursor",
        model="codex-5.2",
        verification="tests",
    )

    runner = UnifiedLoopRunner(project_dir, config)
    result = await runner.run(task_id, prompt, context)
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...agents.adapter import IterationResult, create_adapter, get_agent_for_task
from .verification import VerificationContext, VerificationResult, create_verifier

logger = logging.getLogger(__name__)

# Feature flag for using unified loop (backward compatibility)
USE_UNIFIED_LOOP = os.environ.get("USE_UNIFIED_LOOP", "false").lower() == "true"


@dataclass
class UnifiedLoopConfig:
    """Configuration for unified loop execution.

    Attributes:
        agent_type: Agent to use (claude, cursor, gemini)
        model: Model override for the agent
        max_iterations: Maximum iterations before giving up
        iteration_timeout: Timeout per iteration in seconds
        verification: Verification strategy (tests, lint, security, composite, none)
        enable_session: Enable session continuity (Claude only)
        enable_error_context: Enable error context for retries
        enable_budget: Enable budget tracking
        budget_per_iteration: Budget limit per iteration
        max_budget: Total budget limit
        allowed_tools: List of allowed tools
        max_turns_per_iteration: Max turns per agent invocation
        save_iteration_logs: Save logs for each iteration
        use_plan_mode: Use plan mode for complex tasks (Claude only)
        fallback_model: Fallback model if primary unavailable
    """

    agent_type: str = "claude"
    model: Optional[str] = None
    max_iterations: int = 10
    iteration_timeout: int = 300
    verification: str = "tests"
    enable_session: bool = True
    enable_error_context: bool = True
    enable_budget: bool = True
    budget_per_iteration: float = 0.50
    max_budget: float = 5.00
    allowed_tools: list[str] = field(
        default_factory=lambda: [
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "Bash(npm*)",
            "Bash(pytest*)",
            "Bash(python*)",
            "Bash(pnpm*)",
            "Bash(yarn*)",
            "Bash(bun*)",
            "Bash(cargo*)",
            "Bash(go*)",
        ]
    )
    max_turns_per_iteration: int = 15
    save_iteration_logs: bool = True
    use_plan_mode: bool = False
    fallback_model: str = "sonnet"

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "agent_type": self.agent_type,
            "model": self.model,
            "max_iterations": self.max_iterations,
            "iteration_timeout": self.iteration_timeout,
            "verification": self.verification,
            "enable_session": self.enable_session,
            "enable_error_context": self.enable_error_context,
            "enable_budget": self.enable_budget,
            "budget_per_iteration": self.budget_per_iteration,
            "max_budget": self.max_budget,
            "max_turns_per_iteration": self.max_turns_per_iteration,
            "use_plan_mode": self.use_plan_mode,
        }


@dataclass
class UnifiedLoopResult:
    """Result from unified loop execution.

    Attributes:
        success: Whether the loop completed successfully
        iterations: Number of iterations taken
        agent_type: Agent type used
        model: Model used
        final_output: Output from final successful iteration
        verification_results: Results from each verification
        total_time_seconds: Total execution time
        total_cost_usd: Total estimated cost
        completion_reason: Why the loop stopped
        error: Error message if failed
        iteration_results: Results from each iteration
    """

    success: bool
    iterations: int
    agent_type: str = ""
    model: Optional[str] = None
    final_output: Optional[dict] = None
    verification_results: list[dict] = field(default_factory=list)
    total_time_seconds: float = 0.0
    total_cost_usd: float = 0.0
    completion_reason: str = ""
    error: Optional[str] = None
    iteration_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "success": self.success,
            "iterations": self.iterations,
            "agent_type": self.agent_type,
            "model": self.model,
            "final_output": self.final_output,
            "verification_results": self.verification_results,
            "total_time_seconds": self.total_time_seconds,
            "total_cost_usd": self.total_cost_usd,
            "completion_reason": self.completion_reason,
            "error": self.error,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class LoopContext:
    """Context for loop execution.

    Attributes:
        task_id: Task identifier
        title: Task title
        user_story: User story description
        acceptance_criteria: Acceptance criteria
        files_to_create: Files to create
        files_to_modify: Files to modify
        test_files: Test files to pass
        previous_failures: Failures from previous runs
    """

    task_id: str
    title: str = ""
    user_story: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    previous_failures: list[str] = field(default_factory=list)


# Prompt template for unified loop iterations
UNIFIED_ITERATION_PROMPT = """You are implementing a task using TDD (Test-Driven Development).

TASK: {task_id} - {title}

USER STORY:
{user_story}

ACCEPTANCE CRITERIA:
{acceptance_criteria}

FILES TO CREATE:
{files_to_create}

FILES TO MODIFY:
{files_to_modify}

TEST FILES TO PASS:
{test_files}

{previous_iteration_context}

{error_context}

INSTRUCTIONS:
1. Run the tests to see what's failing
2. Implement the minimal code to make ONE test pass
3. Run tests again
4. Repeat until ALL tests pass

When ALL tests pass, output:
- For Claude: <promise>DONE</promise>
- For Cursor/Gemini: {{"status": "done"}}

If tests are still failing, continue implementing.

Current iteration: {iteration} of {max_iterations}
"""


class UnifiedLoopRunner:
    """Universal loop runner that works with any agent.

    Combines agent adapters, verification strategies, session management,
    error context, and budget control for a unified execution experience.
    """

    def __init__(
        self,
        project_dir: Path,
        config: Optional[UnifiedLoopConfig] = None,
    ):
        """Initialize the unified loop runner.

        Args:
            project_dir: Project directory to run in
            config: Loop configuration
        """
        self.project_dir = Path(project_dir)
        self.config = config or UnifiedLoopConfig()

        # Initialize adapter
        self.adapter = create_adapter(
            agent_type=self.config.agent_type,
            project_dir=self.project_dir,
            model=self.config.model,
            timeout=self.config.iteration_timeout,
        )

        # Initialize verifier
        self.verifier = create_verifier(
            verification_type=self.config.verification,
            project_dir=self.project_dir,
        )

        # Initialize managers (lazy loading)
        self._error_context = None
        self._budget_manager = None
        self._session_manager = None

    @property
    def error_context(self):
        """Get or create error context manager."""
        if self._error_context is None and self.config.enable_error_context:
            try:
                from ...agents.error_context import ErrorContextManager

                self._error_context = ErrorContextManager(self.project_dir)
            except ImportError:
                logger.debug("ErrorContextManager not available")
        return self._error_context

    @property
    def budget_manager(self):
        """Get or create budget storage adapter."""
        if self._budget_manager is None and self.config.enable_budget:
            try:
                from ...storage import get_budget_storage

                self._budget_manager = get_budget_storage(self.project_dir)
            except ImportError:
                logger.debug("BudgetStorageAdapter not available")
        return self._budget_manager

    @property
    def session_manager(self):
        """Get or create session storage adapter (Claude only)."""
        if self._session_manager is None and self.config.enable_session:
            if self.adapter.capabilities.supports_session:
                try:
                    from ...storage import get_session_storage

                    self._session_manager = get_session_storage(self.project_dir)
                except ImportError:
                    logger.debug("SessionStorageAdapter not available")
        return self._session_manager

    async def run(
        self,
        task_id: str,
        prompt: Optional[str] = None,
        context: Optional[LoopContext] = None,
        hitl_callback: Optional[Callable[[int, dict], bool]] = None,
    ) -> UnifiedLoopResult:
        """Run the unified loop for a task.

        Args:
            task_id: Task identifier
            prompt: Optional custom prompt (overrides context-built prompt)
            context: Loop context with task details
            hitl_callback: Optional callback for human-in-the-loop mode

        Returns:
            UnifiedLoopResult with execution details
        """
        start_time = datetime.now()
        iteration = 0
        total_cost = 0.0
        verification_results: list[dict] = []
        iteration_results: list[dict] = []
        previous_context = ""
        session_id = None

        # Build context if not provided
        if context is None:
            context = LoopContext(task_id=task_id)

        logger.info(
            f"Starting unified loop for task {task_id} "
            f"(agent: {self.config.agent_type}, model: {self.config.model or 'default'})"
        )

        while iteration < self.config.max_iterations:
            iteration += 1
            logger.info(f"Unified loop iteration {iteration}/{self.config.max_iterations}")

            # Check budget before iteration
            if self.budget_manager and self.config.enable_budget:
                if not self.budget_manager.can_spend(task_id, self.config.budget_per_iteration):
                    return UnifiedLoopResult(
                        success=False,
                        iterations=iteration,
                        agent_type=self.config.agent_type,
                        model=self.config.model,
                        verification_results=verification_results,
                        total_time_seconds=(datetime.now() - start_time).total_seconds(),
                        total_cost_usd=total_cost,
                        completion_reason="budget_exceeded",
                        error=f"Budget exceeded: ${self.config.max_budget:.2f} limit",
                        iteration_results=iteration_results,
                    )

                if total_cost >= self.config.max_budget:
                    return UnifiedLoopResult(
                        success=False,
                        iterations=iteration,
                        agent_type=self.config.agent_type,
                        model=self.config.model,
                        verification_results=verification_results,
                        total_time_seconds=(datetime.now() - start_time).total_seconds(),
                        total_cost_usd=total_cost,
                        completion_reason="max_budget_reached",
                        error=f"Total budget of ${self.config.max_budget:.2f} reached",
                        iteration_results=iteration_results,
                    )

            # Build prompt with error context if available
            iteration_prompt = prompt or self._build_iteration_prompt(
                context=context,
                iteration=iteration,
                previous_context=previous_context,
            )

            # Enhance with error context from previous failures
            if self.error_context and self.config.enable_error_context:
                iteration_prompt = self.error_context.build_retry_prompt(
                    task_id,
                    iteration_prompt,
                )

            # Get session args (Claude only)
            if self.session_manager and iteration > 1 and session_id:
                resume_session = True
            else:
                resume_session = False
                if self.session_manager and iteration == 1:
                    session = self.session_manager.get_or_create_session(task_id)
                    session_id = session.id if session else None

            try:
                # Run iteration
                result = await self.adapter.run_iteration(
                    prompt=iteration_prompt,
                    timeout=self.config.iteration_timeout,
                    model=self.config.model,
                    max_turns=self.config.max_turns_per_iteration,
                    allowed_tools=self.config.allowed_tools,
                    session_id=session_id,
                    budget_usd=self.config.budget_per_iteration,
                    use_plan_mode=self.config.use_plan_mode,
                    resume_session=resume_session,
                    fallback_model=self.config.fallback_model,
                )

                # Track cost
                if result.cost_usd:
                    total_cost += result.cost_usd
                    if self.budget_manager:
                        self.budget_manager.record_spend(
                            task_id=task_id,
                            agent=self.config.agent_type,
                            cost_usd=result.cost_usd,
                            model=result.model or self.config.model,
                        )

                # Update session ID if returned
                if result.session_id:
                    session_id = result.session_id

                # Save iteration log
                if self.config.save_iteration_logs:
                    self._save_iteration_log(task_id, iteration, result)

                iteration_results.append(result.to_dict())

                # Check for completion signal
                if result.completion_detected:
                    # Clear error context on success
                    if self.error_context:
                        self.error_context.clear_task_errors(task_id)

                    # Close session
                    if self.session_manager:
                        self.session_manager.close_session(task_id)

                    return UnifiedLoopResult(
                        success=True,
                        iterations=iteration,
                        agent_type=self.config.agent_type,
                        model=result.model or self.config.model,
                        final_output=result.parsed_output,
                        verification_results=verification_results,
                        total_time_seconds=(datetime.now() - start_time).total_seconds(),
                        total_cost_usd=total_cost,
                        completion_reason="completion_signal_detected",
                        iteration_results=iteration_results,
                    )

                # Run verification
                verification_context = VerificationContext(
                    project_dir=self.project_dir,
                    test_files=context.test_files,
                    source_files=result.files_changed,
                    task_id=task_id,
                    iteration=iteration,
                    timeout=60,
                )

                verification_result = await self.verifier.verify(verification_context)
                verification_results.append(verification_result.to_dict())

                if verification_result.passed:
                    # Clear error context on success
                    if self.error_context:
                        self.error_context.clear_task_errors(task_id)

                    # Close session
                    if self.session_manager:
                        self.session_manager.close_session(task_id)

                    return UnifiedLoopResult(
                        success=True,
                        iterations=iteration,
                        agent_type=self.config.agent_type,
                        model=result.model or self.config.model,
                        final_output=result.parsed_output,
                        verification_results=verification_results,
                        total_time_seconds=(datetime.now() - start_time).total_seconds(),
                        total_cost_usd=total_cost,
                        completion_reason="verification_passed",
                        iteration_results=iteration_results,
                    )

                # Record error for next iteration
                if self.error_context and verification_result.failures:
                    self.error_context.record_error(
                        task_id=task_id,
                        error_message="; ".join(verification_result.failures[:3]),
                        attempt=iteration,
                        stderr=verification_result.command_output,
                    )

                # Build context for next iteration
                previous_context = self._build_previous_context(
                    iteration=iteration,
                    verification_result=verification_result,
                    changes_made=result.files_changed,
                )

                # HITL callback
                if hitl_callback:
                    should_continue = hitl_callback(
                        iteration,
                        {
                            "verification_result": verification_result.to_dict(),
                            "files_changed": result.files_changed,
                        },
                    )
                    if not should_continue:
                        return UnifiedLoopResult(
                            success=False,
                            iterations=iteration,
                            agent_type=self.config.agent_type,
                            model=self.config.model,
                            verification_results=verification_results,
                            total_time_seconds=(datetime.now() - start_time).total_seconds(),
                            total_cost_usd=total_cost,
                            completion_reason="human_paused",
                            iteration_results=iteration_results,
                        )

            except asyncio.TimeoutError:
                logger.warning(f"Iteration {iteration} timed out")
                iteration_results.append(
                    {
                        "iteration": iteration,
                        "success": False,
                        "error": "timeout",
                    }
                )
                previous_context = (
                    f"PREVIOUS ITERATION {iteration}: Timed out. Continue from where you left off."
                )

            except asyncio.CancelledError:
                logger.info("Loop cancelled")
                raise

            except Exception as e:
                logger.error(f"Iteration {iteration} failed: {e}")
                iteration_results.append(
                    {
                        "iteration": iteration,
                        "success": False,
                        "error": str(e),
                    }
                )

                if self.error_context:
                    self.error_context.record_error(
                        task_id=task_id,
                        error_message=str(e),
                        attempt=iteration,
                    )

                previous_context = f"PREVIOUS ITERATION {iteration}: Error occurred: {e}. Try a different approach."

        # Max iterations reached
        return UnifiedLoopResult(
            success=False,
            iterations=iteration,
            agent_type=self.config.agent_type,
            model=self.config.model,
            verification_results=verification_results,
            total_time_seconds=(datetime.now() - start_time).total_seconds(),
            total_cost_usd=total_cost,
            completion_reason="max_iterations_reached",
            error=f"Failed to complete after {self.config.max_iterations} iterations",
            iteration_results=iteration_results,
        )

    def _build_iteration_prompt(
        self,
        context: LoopContext,
        iteration: int,
        previous_context: str,
    ) -> str:
        """Build prompt for this iteration."""
        return UNIFIED_ITERATION_PROMPT.format(
            task_id=context.task_id,
            title=context.title,
            user_story=context.user_story or "No user story provided",
            acceptance_criteria=self._format_list(context.acceptance_criteria),
            files_to_create=self._format_list(context.files_to_create),
            files_to_modify=self._format_list(context.files_to_modify),
            test_files=self._format_list(context.test_files),
            previous_iteration_context=previous_context,
            error_context="",  # Error context added by error_context.build_retry_prompt()
            iteration=iteration,
            max_iterations=self.config.max_iterations,
        )

    def _build_previous_context(
        self,
        iteration: int,
        verification_result: VerificationResult,
        changes_made: list[str],
    ) -> str:
        """Build context from previous iteration."""
        lines = [f"PREVIOUS ITERATION {iteration}:"]

        if changes_made:
            lines.append(f"- Files changed: {', '.join(changes_made[:5])}")

        if verification_result.summary:
            lines.append(f"- Verification: {verification_result.summary}")

        if not verification_result.passed:
            lines.append("- Verification failed. Continue implementing to make it pass.")

            if verification_result.failures:
                lines.append(f"- Failures: {', '.join(verification_result.failures[:3])}")

        return "\n".join(lines)

    def _format_list(self, items: list[str]) -> str:
        """Format a list of items."""
        if not items:
            return "- None specified"
        return "\n".join(f"- {item}" for item in items)

    def _save_iteration_log(
        self,
        task_id: str,
        iteration: int,
        result: IterationResult,
    ) -> None:
        """Save iteration log for debugging."""
        log_dir = self.project_dir / ".workflow" / "unified_logs" / task_id
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"iteration_{iteration:03d}.json"

        log_data = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "agent_type": self.config.agent_type,
            "model": result.model,
            "success": result.success,
            "completion_detected": result.completion_detected,
            "files_changed": result.files_changed,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "cost_usd": result.cost_usd,
            "error": result.error,
        }

        log_file.write_text(json.dumps(log_data, indent=2))


def create_unified_runner(
    project_dir: Path,
    agent_type: str = "claude",
    model: Optional[str] = None,
    verification: str = "tests",
    **kwargs,
) -> UnifiedLoopRunner:
    """Convenience function to create a unified loop runner.

    Args:
        project_dir: Project directory
        agent_type: Agent to use
        model: Model override
        verification: Verification strategy
        **kwargs: Additional config options

    Returns:
        Configured UnifiedLoopRunner
    """
    config = UnifiedLoopConfig(
        agent_type=agent_type,
        model=model,
        verification=verification,
        **kwargs,
    )

    return UnifiedLoopRunner(project_dir, config)


def create_runner_from_task(
    project_dir: Path,
    task: dict,
    verification: str = "tests",
    **kwargs,
) -> UnifiedLoopRunner:
    """Create a runner configured for a specific task.

    Uses task metadata and environment variables to determine
    agent and model selection.

    Args:
        project_dir: Project directory
        task: Task dictionary
        verification: Verification strategy
        **kwargs: Additional config options

    Returns:
        Configured UnifiedLoopRunner
    """
    agent_type, model = get_agent_for_task(task)

    config = UnifiedLoopConfig(
        agent_type=agent_type.value,
        model=model,
        verification=verification,
        **kwargs,
    )

    return UnifiedLoopRunner(project_dir, config)


def should_use_unified_loop() -> bool:
    """Check if unified loop should be used (feature flag)."""
    return USE_UNIFIED_LOOP
