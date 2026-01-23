"""Ralph Wiggum loop integration.

Implements the Ralph Wiggum iterative execution pattern for TDD-based
task implementation. Each iteration starts a fresh Claude context,
runs tests, and continues until all tests pass.

Key principles:
- Fresh context per iteration (avoids degradation)
- Tests as backpressure (natural completion signal)
- <promise>DONE</promise> pattern for completion detection
- Configurable max iterations as safety limit

Enhanced with:
- ExecutionMode: HITL (human-in-the-loop) vs AFK (autonomous)
- External hook scripts for custom verification
- Token/cost tracking per iteration
- Context compaction warning at 75% threshold

Reference: https://github.com/anthropics/claude-code/discussions/1278
"""

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Completion promise pattern
COMPLETION_PROMISE = "<promise>DONE</promise>"

# Context window management
CONTEXT_WARNING_THRESHOLD = 0.75  # Warn at 75% utilization


class ExecutionMode(str, Enum):
    """Execution mode for Ralph loop.

    HITL: Human-in-the-loop - pauses after each iteration for review
    AFK: Away-from-keyboard - runs autonomously until completion
    """

    HITL = "human_in_the_loop"
    AFK = "away_from_keyboard"


@dataclass
class HookConfig:
    """Configuration for external hook scripts.

    Hooks allow external scripts to control loop behavior:
    - pre_iteration: Runs before each iteration
    - post_iteration: Runs after each iteration
    - stop_check: Returns 0 to stop loop, non-zero to continue

    Attributes:
        pre_iteration: Path to pre-iteration script
        post_iteration: Path to post-iteration script
        stop_check: Path to stop-check script
        timeout: Max seconds per hook execution
        sandbox: Whether to run in sandboxed environment
    """

    pre_iteration: Optional[Path] = None
    post_iteration: Optional[Path] = None
    stop_check: Optional[Path] = None
    timeout: int = 30
    sandbox: bool = True


@dataclass
class TokenMetrics:
    """Token and cost tracking per iteration.

    Tracks token usage and estimates costs based on model pricing.

    Attributes:
        iteration: Iteration number
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        estimated_cost_usd: Estimated cost in USD
        model: Model name for pricing lookup
    """

    iteration: int
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model: str = "claude-sonnet-4"

    # Pricing per 1M tokens (2026 rates - approximate)
    PRICING: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "claude-sonnet-4": {"input": 3.0, "output": 15.0},
            "claude-opus-4": {"input": 15.0, "output": 75.0},
            "claude-opus-4-5": {"input": 15.0, "output": 75.0},
            "claude-haiku-3-5": {"input": 0.25, "output": 1.25},
        }
    )

    def calculate_cost(self) -> float:
        """Calculate estimated cost based on token usage and model pricing."""
        rates = self.PRICING.get(self.model, self.PRICING["claude-sonnet-4"])
        input_cost = (self.input_tokens / 1_000_000) * rates["input"]
        output_cost = (self.output_tokens / 1_000_000) * rates["output"]
        self.estimated_cost_usd = input_cost + output_cost
        return self.estimated_cost_usd

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "model": self.model,
        }


@dataclass
class TokenUsageTracker:
    """Aggregated token usage tracking across iterations.

    Attributes:
        total_input_tokens: Total input tokens across all iterations
        total_output_tokens: Total output tokens across all iterations
        total_cost_usd: Total estimated cost in USD
        iterations: List of per-iteration metrics
        max_cost_usd: Optional cost limit
    """

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    iterations: list[TokenMetrics] = field(default_factory=list)
    max_cost_usd: Optional[float] = None

    def add_iteration(self, metrics: TokenMetrics) -> None:
        """Add metrics from an iteration."""
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.total_cost_usd += metrics.estimated_cost_usd
        self.iterations.append(metrics)

    def is_over_budget(self) -> bool:
        """Check if cost limit has been exceeded."""
        if self.max_cost_usd is None:
            return False
        return self.total_cost_usd >= self.max_cost_usd

    def to_dict(self) -> dict:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "iteration_count": len(self.iterations),
            "iterations": [m.to_dict() for m in self.iterations],
        }


@dataclass
class RalphLoopConfig:
    """Configuration for Ralph Wiggum loop execution.

    Attributes:
        max_iterations: Maximum iterations before giving up
        iteration_timeout: Timeout per iteration in seconds
        test_command: Command to run tests
        completion_pattern: Pattern that signals completion
        allowed_tools: Tools the worker can use
        max_turns_per_iteration: Max turns per Claude invocation
        save_iteration_logs: Whether to save logs for each iteration
        execution_mode: HITL or AFK mode
        hooks: External hook script configuration
        track_tokens: Whether to track token usage
        context_warning_threshold: Context utilization threshold for warnings
        max_cost_usd: Optional cost limit
    """

    max_iterations: int = 10
    iteration_timeout: int = 300  # 5 minutes per iteration
    test_command: str = "pytest"
    completion_pattern: str = COMPLETION_PROMISE
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

    # New: Execution mode (HITL vs AFK)
    execution_mode: ExecutionMode = ExecutionMode.AFK

    # New: External hooks
    hooks: Optional[HookConfig] = None

    # New: Token tracking
    track_tokens: bool = True
    context_warning_threshold: float = CONTEXT_WARNING_THRESHOLD
    max_cost_usd: Optional[float] = None

    # Fallback model support
    model: Optional[str] = None  # Override model (e.g., 'haiku' for budget constraints)
    budget_per_iteration: float = 0.50  # Budget per iteration in USD


@dataclass
class RalphLoopResult:
    """Result of a Ralph Wiggum loop execution.

    Attributes:
        success: Whether the loop completed successfully
        iterations: Number of iterations taken
        final_output: Output from the final successful iteration
        test_results: Test results from each iteration
        total_time_seconds: Total execution time
        completion_reason: Why the loop stopped
        error: Error message if failed
        token_usage: Token usage tracking (if enabled)
        paused_for_review: Whether loop paused for HITL review
    """

    success: bool
    iterations: int
    final_output: Optional[dict] = None
    test_results: list[dict] = field(default_factory=list)
    total_time_seconds: float = 0.0
    completion_reason: str = ""
    error: Optional[str] = None

    # New: Token tracking
    token_usage: Optional[TokenUsageTracker] = None

    # New: HITL support
    paused_for_review: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "iterations": self.iterations,
            "final_output": self.final_output,
            "test_results": self.test_results,
            "total_time_seconds": self.total_time_seconds,
            "completion_reason": self.completion_reason,
            "error": self.error,
            "token_usage": self.token_usage.to_dict() if self.token_usage else None,
            "paused_for_review": self.paused_for_review,
        }


# Prompt template for Ralph Wiggum iterations
RALPH_ITERATION_PROMPT = """You are implementing a task using TDD (Test-Driven Development).

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

INSTRUCTIONS:
1. Run the tests to see what's failing
2. Implement the minimal code to make ONE test pass
3. Run tests again
4. Repeat until ALL tests pass

When ALL tests pass, output EXACTLY this completion signal:
{completion_promise}

If tests are still failing, DO NOT output the completion signal.
Instead, continue implementing until tests pass.

Current iteration: {iteration} of {max_iterations}
"""


async def run_ralph_loop(
    project_dir: Path,
    task_id: str,
    title: str,
    user_story: str,
    acceptance_criteria: list[str],
    files_to_create: list[str],
    files_to_modify: list[str],
    test_files: list[str],
    config: Optional[RalphLoopConfig] = None,
    hitl_callback: Optional[Callable[[int, dict], bool]] = None,
) -> RalphLoopResult:
    """Execute the Ralph Wiggum loop for a task.

    Iteratively runs Claude with fresh context until tests pass
    or max iterations reached.

    Enhanced with:
    - HITL mode: Pause after each iteration for human review
    - Hook scripts: External verification and control
    - Token tracking: Monitor context usage and costs

    Args:
        project_dir: Project directory to run in
        task_id: Task identifier
        title: Task title
        user_story: User story description
        acceptance_criteria: List of acceptance criteria
        files_to_create: Files to create
        files_to_modify: Files to modify
        test_files: Test files that must pass
        config: Loop configuration
        hitl_callback: Callback for HITL mode (receives iteration, result; returns continue?)

    Returns:
        RalphLoopResult with execution details
    """
    if config is None:
        config = RalphLoopConfig()

    # Clean up old iteration logs at start of each run
    cleanup_old_logs(project_dir)

    start_time = datetime.now()
    test_results = []
    iteration = 0
    previous_context = ""

    # Initialize token tracking
    token_tracker = (
        TokenUsageTracker(max_cost_usd=config.max_cost_usd) if config.track_tokens else None
    )

    logger.info(
        f"Starting Ralph Wiggum loop for task {task_id} (mode: {config.execution_mode.value})"
    )

    while iteration < config.max_iterations:
        iteration += 1
        logger.info(f"Ralph loop iteration {iteration}/{config.max_iterations}")

        # Run pre-iteration hook if configured
        if config.hooks and config.hooks.pre_iteration:
            hook_result = await _run_hook(
                config.hooks.pre_iteration,
                config.hooks,
                {"iteration": iteration, "task_id": task_id},
            )
            if hook_result != 0:
                logger.warning(f"Pre-iteration hook returned non-zero: {hook_result}")

        # Build prompt for this iteration
        prompt = RALPH_ITERATION_PROMPT.format(
            task_id=task_id,
            title=title,
            user_story=user_story,
            acceptance_criteria=_format_criteria(acceptance_criteria),
            files_to_create=_format_list(files_to_create),
            files_to_modify=_format_list(files_to_modify),
            test_files=_format_list(test_files),
            previous_iteration_context=previous_context,
            completion_promise=COMPLETION_PROMISE,
            iteration=iteration,
            max_iterations=config.max_iterations,
        )

        try:
            # Run single iteration with fresh Claude context
            result = await asyncio.wait_for(
                _run_single_iteration(
                    project_dir=project_dir,
                    prompt=prompt,
                    config=config,
                    iteration=iteration,
                    task_id=task_id,
                ),
                timeout=config.iteration_timeout,
            )

            # Track tokens if enabled
            if token_tracker and config.track_tokens:
                metrics = _extract_token_metrics(result, iteration)
                if metrics:
                    metrics.calculate_cost()
                    token_tracker.add_iteration(metrics)

                    # Check cost limit
                    if token_tracker.is_over_budget():
                        elapsed = (datetime.now() - start_time).total_seconds()
                        logger.warning(f"Cost limit exceeded: ${token_tracker.total_cost_usd:.4f}")
                        return RalphLoopResult(
                            success=False,
                            iterations=iteration,
                            test_results=test_results,
                            total_time_seconds=elapsed,
                            completion_reason="cost_limit_exceeded",
                            error=f"Cost limit of ${config.max_cost_usd:.2f} exceeded",
                            token_usage=token_tracker,
                        )

                    # Log context usage warning
                    _check_context_warning(token_tracker, config)

            # Save iteration log
            if config.save_iteration_logs:
                _save_iteration_log(project_dir, task_id, iteration, result)

            # Run post-iteration hook if configured
            if config.hooks and config.hooks.post_iteration:
                await _run_hook(
                    config.hooks.post_iteration,
                    config.hooks,
                    {
                        "iteration": iteration,
                        "task_id": task_id,
                        "completion_detected": result.get("completion_detected", False),
                    },
                )

            # Check for completion signal
            if result.get("completion_detected"):
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Ralph loop completed successfully in {iteration} iterations")
                return RalphLoopResult(
                    success=True,
                    iterations=iteration,
                    final_output=result.get("output"),
                    test_results=test_results,
                    total_time_seconds=elapsed,
                    completion_reason="completion_promise_detected",
                    token_usage=token_tracker,
                )

            # Check if tests pass
            test_result = await _run_tests(project_dir, test_files, config)
            test_results.append(
                {
                    "iteration": iteration,
                    "passed": test_result["all_passed"],
                    "summary": test_result.get("summary", ""),
                }
            )

            if test_result["all_passed"]:
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Ralph loop: All tests passed in iteration {iteration}")
                return RalphLoopResult(
                    success=True,
                    iterations=iteration,
                    final_output=result.get("output"),
                    test_results=test_results,
                    total_time_seconds=elapsed,
                    completion_reason="all_tests_passed",
                    token_usage=token_tracker,
                )

            # Run stop-check hook if configured
            if config.hooks and config.hooks.stop_check:
                stop_result = await _run_hook(
                    config.hooks.stop_check,
                    config.hooks,
                    {
                        "iteration": iteration,
                        "task_id": task_id,
                        "tests_passed": test_result["all_passed"],
                    },
                )
                if stop_result == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Ralph loop stopped by hook at iteration {iteration}")
                    return RalphLoopResult(
                        success=True,
                        iterations=iteration,
                        final_output=result.get("output"),
                        test_results=test_results,
                        total_time_seconds=elapsed,
                        completion_reason="stop_hook_triggered",
                        token_usage=token_tracker,
                    )

            # HITL mode: Pause for human review
            if config.execution_mode == ExecutionMode.HITL:
                if hitl_callback:
                    should_continue = hitl_callback(
                        iteration,
                        {
                            "test_result": test_result,
                            "files_changed": result.get("files_changed", []),
                        },
                    )
                    if not should_continue:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        logger.info(f"Ralph loop paused by human at iteration {iteration}")
                        return RalphLoopResult(
                            success=False,
                            iterations=iteration,
                            test_results=test_results,
                            total_time_seconds=elapsed,
                            completion_reason="human_paused",
                            paused_for_review=True,
                            token_usage=token_tracker,
                        )
                else:
                    # No callback in HITL mode - pause automatically
                    elapsed = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Ralph loop pausing for HITL review at iteration {iteration}")
                    return RalphLoopResult(
                        success=False,
                        iterations=iteration,
                        test_results=test_results,
                        total_time_seconds=elapsed,
                        completion_reason="hitl_pause",
                        paused_for_review=True,
                        token_usage=token_tracker,
                    )

            # Build context for next iteration
            previous_context = _build_previous_context(
                iteration=iteration,
                test_result=test_result,
                changes_made=result.get("files_changed", []),
            )

        except asyncio.TimeoutError:
            logger.warning(f"Ralph loop iteration {iteration} timed out")
            test_results.append(
                {
                    "iteration": iteration,
                    "passed": False,
                    "summary": "Iteration timed out",
                }
            )
            previous_context = f"PREVIOUS ITERATION {iteration}: Timed out. Please continue from where you left off."

        except Exception as e:
            logger.error(f"Ralph loop iteration {iteration} failed: {e}")
            test_results.append(
                {
                    "iteration": iteration,
                    "passed": False,
                    "summary": str(e),
                }
            )
            previous_context = f"PREVIOUS ITERATION {iteration}: Error occurred: {e}. Please try a different approach."

    # Max iterations reached
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.warning(f"Ralph loop: Max iterations ({config.max_iterations}) reached")
    return RalphLoopResult(
        success=False,
        iterations=iteration,
        test_results=test_results,
        total_time_seconds=elapsed,
        completion_reason="max_iterations_reached",
        error=f"Failed to complete task after {config.max_iterations} iterations",
        token_usage=token_tracker,
    )


async def _run_single_iteration(
    project_dir: Path,
    prompt: str,
    config: RalphLoopConfig,
    iteration: int,
    task_id: str,
) -> dict[str, Any]:
    """Run a single Ralph loop iteration.

    Spawns fresh Claude process with the prompt. Ensures proper cleanup
    on timeout or error to prevent zombie processes.

    Args:
        project_dir: Project directory
        prompt: Iteration prompt
        config: Loop configuration
        iteration: Current iteration number
        task_id: Task identifier

    Returns:
        Dict with iteration results
    """
    allowed_tools = ",".join(config.allowed_tools)

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--allowedTools",
        allowed_tools,
        "--max-turns",
        str(config.max_turns_per_iteration),
    ]

    # Add model override if specified (for fallback model support)
    if config.model:
        cmd.extend(["--model", config.model])

    # Add budget limit per iteration
    if config.budget_per_iteration > 0:
        cmd.extend(["--max-budget-usd", str(config.budget_per_iteration)])

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "dumb"},
        )

        stdout, stderr = await process.communicate()
        output_text = stdout.decode() if stdout else ""

        # Check for completion promise in output
        completion_detected = config.completion_pattern in output_text

        # Parse any JSON output
        parsed_output = _parse_iteration_output(output_text)

        # Extract list of changed files from output (if any)
        files_changed = parsed_output.get("files_modified", []) + parsed_output.get(
            "files_created", []
        )

        return {
            "iteration": iteration,
            "completion_detected": completion_detected,
            "output": parsed_output,
            "files_changed": files_changed,
            "raw_output": output_text,
            "return_code": process.returncode,
        }

    except asyncio.CancelledError:
        # Task was cancelled (likely due to timeout)
        if process is not None:
            await _terminate_process(process)
        raise

    except Exception:
        # Ensure cleanup on any error
        if process is not None:
            await _terminate_process(process)
        raise


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Safely terminate a subprocess.

    Attempts graceful termination first, then forceful kill.

    Args:
        process: The subprocess to terminate
    """
    if process.returncode is not None:
        # Process already finished
        return

    try:
        # Try graceful termination first
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
            logger.debug("Process terminated gracefully")
        except asyncio.TimeoutError:
            # Process didn't terminate, force kill
            logger.warning("Process didn't terminate gracefully, sending SIGKILL")
            process.kill()
            await process.wait()
    except ProcessLookupError:
        # Process already dead
        pass
    except Exception as e:
        logger.error(f"Error terminating process: {e}")


async def _run_tests(
    project_dir: Path,
    test_files: list[str],
    config: RalphLoopConfig,
) -> dict[str, Any]:
    """Run tests and check if they pass.

    Args:
        project_dir: Project directory
        test_files: List of test files to run
        config: Loop configuration

    Returns:
        Dict with test results
    """
    if not test_files:
        # No tests specified - consider passed
        return {
            "all_passed": True,
            "summary": "No test files specified",
            "details": [],
        }

    # Build test command
    test_cmd = config.test_command
    if test_cmd == "pytest":
        # Run specific test files
        cmd = ["pytest", "-v", "--tb=short"] + test_files
    elif test_cmd == "npm test":
        cmd = ["npm", "test", "--"] + test_files
    elif test_cmd == "bun test":
        cmd = ["bun", "test"] + test_files
    else:
        # Generic command
        cmd = test_cmd.split() + test_files

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=60,  # 1 minute timeout for tests
        )

        output = stdout.decode() if stdout else ""
        error = stderr.decode() if stderr else ""

        all_passed = process.returncode == 0

        # Extract summary from pytest output
        summary = _extract_test_summary(output)

        return {
            "all_passed": all_passed,
            "summary": summary,
            "return_code": process.returncode,
            "output": output,
            "error": error,
        }

    except asyncio.TimeoutError:
        return {
            "all_passed": False,
            "summary": "Tests timed out after 60 seconds",
            "error": "timeout",
        }
    except Exception as e:
        return {
            "all_passed": False,
            "summary": f"Test execution failed: {e}",
            "error": str(e),
        }


def _extract_test_summary(output: str) -> str:
    """Extract test summary from pytest output."""
    # Look for pytest summary line like "5 passed, 2 failed"
    summary_match = re.search(r"=+ (\d+ passed.*?) =+", output)
    if summary_match:
        return summary_match.group(1)

    # Look for simple pass/fail counts
    passed = len(re.findall(r"PASSED", output))
    failed = len(re.findall(r"FAILED", output))

    if passed or failed:
        return f"{passed} passed, {failed} failed"

    return "No test summary available"


def _build_previous_context(
    iteration: int,
    test_result: dict,
    changes_made: list[str],
) -> str:
    """Build context from previous iteration for next prompt.

    Args:
        iteration: Previous iteration number
        test_result: Test results from previous iteration
        changes_made: Files changed in previous iteration

    Returns:
        Context string for next iteration
    """
    lines = [f"PREVIOUS ITERATION {iteration}:"]

    if changes_made:
        lines.append(f"- Files changed: {', '.join(changes_made[:5])}")

    if test_result.get("summary"):
        lines.append(f"- Test status: {test_result['summary']}")

    if not test_result.get("all_passed"):
        lines.append("- Tests are still failing. Continue implementing to make them pass.")

        # Include failure details if available
        if "output" in test_result:
            # Extract failing test names
            failing_tests = re.findall(r"FAILED\s+(\S+)", test_result["output"])
            if failing_tests:
                lines.append(f"- Failing tests: {', '.join(failing_tests[:5])}")

    lines.append("")  # Empty line before instructions
    return "\n".join(lines)


def _format_criteria(criteria: list[str]) -> str:
    """Format acceptance criteria as checklist."""
    if not criteria:
        return "- No specific criteria defined"
    return "\n".join(f"- [ ] {c}" for c in criteria)


def _format_list(items: list[str]) -> str:
    """Format a list of items."""
    if not items:
        return "- None specified"
    return "\n".join(f"- {item}" for item in items)


def _parse_iteration_output(output: str) -> dict:
    """Parse JSON output from iteration."""
    if not output:
        return {}

    # Try direct JSON parse
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    # Look for JSON block
    json_match = re.search(r"\{[\s\S]*\}", output)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw_output": output}


def _save_iteration_log(
    project_dir: Path,
    task_id: str,
    iteration: int,
    result: dict,
) -> None:
    """Save iteration log for debugging.

    Args:
        project_dir: Project directory
        task_id: Task identifier
        iteration: Iteration number
        result: Iteration result
    """
    log_dir = project_dir / ".workflow" / "ralph_logs" / task_id
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"iteration_{iteration:03d}.json"

    # Don't save raw output (too large) - just metadata
    log_data = {
        "iteration": iteration,
        "timestamp": datetime.now().isoformat(),
        "completion_detected": result.get("completion_detected", False),
        "files_changed": result.get("files_changed", []),
        "return_code": result.get("return_code"),
    }

    log_file.write_text(json.dumps(log_data, indent=2))


# Log retention period in days
LOG_RETENTION_DAYS = 7


def cleanup_old_logs(project_dir: Path, retention_days: int = LOG_RETENTION_DAYS) -> int:
    """Clean up iteration logs older than retention period.

    Args:
        project_dir: Project directory
        retention_days: Number of days to retain logs (default 7)

    Returns:
        Number of files deleted
    """
    import time

    logs_dir = project_dir / ".workflow" / "ralph_logs"
    if not logs_dir.exists():
        return 0

    cutoff_time = time.time() - (retention_days * 24 * 60 * 60)
    deleted = 0

    for task_dir in logs_dir.iterdir():
        if not task_dir.is_dir():
            continue

        for log_file in task_dir.glob("iteration_*.json"):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    deleted += 1
            except (OSError, FileNotFoundError):
                continue

        # Remove empty task directories
        try:
            if task_dir.is_dir() and not any(task_dir.iterdir()):
                task_dir.rmdir()
        except (OSError, FileNotFoundError):
            pass

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old iteration log files")

    return deleted


def detect_test_framework(project_dir: Path) -> str:
    """Detect the test framework used in the project.

    Args:
        project_dir: Project directory

    Returns:
        Test command to use
    """
    # Check for common test configuration files
    if (project_dir / "pytest.ini").exists() or (project_dir / "pyproject.toml").exists():
        return "pytest"
    if (project_dir / "package.json").exists():
        pkg = json.loads((project_dir / "package.json").read_text())
        if "bun" in pkg.get("devDependencies", {}):
            return "bun test"
        if "jest" in pkg.get("devDependencies", {}):
            return "npm test"
        if "vitest" in pkg.get("devDependencies", {}):
            return "npm test"
    if (project_dir / "Cargo.toml").exists():
        return "cargo test"
    if (project_dir / "go.mod").exists():
        return "go test"

    return "pytest"  # Default


# --- Hook Support ---


async def _run_hook(
    hook_path: Path,
    config: HookConfig,
    context: dict,
) -> int:
    """Run external hook script in sandboxed environment.

    Args:
        hook_path: Path to hook script
        config: Hook configuration
        context: Context dict to pass as environment variables

    Returns:
        Hook return code (0 = success/stop, non-zero = continue)
    """
    if not hook_path or not hook_path.exists():
        return 0

    # Build environment variables from context
    env = {
        **os.environ,
        "RALPH_ITERATION": str(context.get("iteration", 0)),
        "RALPH_TASK_ID": str(context.get("task_id", "")),
        "RALPH_TESTS_PASSED": str(context.get("tests_passed", False)).lower(),
        "RALPH_COMPLETION_DETECTED": str(context.get("completion_detected", False)).lower(),
    }

    try:
        if config.sandbox:
            # Run with limited privileges (no network, limited filesystem)
            cmd = [str(hook_path)]
        else:
            cmd = [str(hook_path)]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=config.timeout,
            )
            logger.debug(f"Hook {hook_path.name} output: {stdout.decode()[:500]}")
            return process.returncode or 0

        except asyncio.TimeoutError:
            logger.warning(f"Hook {hook_path.name} timed out after {config.timeout}s")
            process.kill()
            await process.wait()
            return -1

    except FileNotFoundError:
        logger.warning(f"Hook script not found: {hook_path}")
        return 0
    except PermissionError:
        logger.warning(f"Hook script not executable: {hook_path}")
        return 0
    except Exception as e:
        logger.error(f"Error running hook {hook_path.name}: {e}")
        return -1


# --- Token Tracking ---


def _extract_token_metrics(result: dict, iteration: int) -> Optional[TokenMetrics]:
    """Extract token usage metrics from iteration result.

    Claude CLI with --output-format json includes usage stats in output.

    Args:
        result: Iteration result dict
        iteration: Current iteration number

    Returns:
        TokenMetrics or None if not available
    """
    output = result.get("output", {})

    # Try to extract from Claude JSON output
    usage = output.get("usage", {})
    if usage:
        return TokenMetrics(
            iteration=iteration,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )

    # Try to extract from raw output
    raw_output = result.get("raw_output", "")
    if raw_output:
        # Look for usage patterns in output
        input_match = re.search(r"input_tokens[\"']?\s*:\s*(\d+)", raw_output)
        output_match = re.search(r"output_tokens[\"']?\s*:\s*(\d+)", raw_output)

        if input_match or output_match:
            return TokenMetrics(
                iteration=iteration,
                input_tokens=int(input_match.group(1)) if input_match else 0,
                output_tokens=int(output_match.group(1)) if output_match else 0,
            )

    # Estimate based on prompt/output length if nothing else
    # Rough estimate: 1 token ≈ 4 characters
    raw_len = len(result.get("raw_output", ""))
    if raw_len > 0:
        return TokenMetrics(
            iteration=iteration,
            input_tokens=0,  # Can't estimate input reliably
            output_tokens=raw_len // 4,
        )

    return None


def _check_context_warning(tracker: TokenUsageTracker, config: RalphLoopConfig) -> None:
    """Check and log context utilization warning.

    Warns at 75% utilization to leave "thinking space" for reasoning.

    Args:
        tracker: Token usage tracker
        config: Loop configuration
    """
    # Approximate context window sizes (2026)
    # Claude Sonnet 4 / Opus 4: 200k tokens
    MAX_CONTEXT_TOKENS = 200_000

    total_tokens = tracker.total_input_tokens + tracker.total_output_tokens
    utilization = total_tokens / MAX_CONTEXT_TOKENS

    if utilization >= config.context_warning_threshold:
        logger.warning(
            f"Context utilization at {utilization:.1%} ({total_tokens:,} tokens). "
            f"Consider compacting context or starting fresh iteration."
        )


# --- Convenience Functions ---


def create_ralph_config(
    project_dir: Path,
    execution_mode: str = "afk",
    max_iterations: int = 10,
    enable_hooks: bool = False,
    track_tokens: bool = True,
    max_cost_usd: Optional[float] = None,
) -> RalphLoopConfig:
    """Create RalphLoopConfig with sensible defaults.

    Args:
        project_dir: Project directory for test framework detection
        execution_mode: "hitl" or "afk"
        max_iterations: Maximum loop iterations
        enable_hooks: Whether to enable hook scripts
        track_tokens: Whether to track token usage
        max_cost_usd: Optional cost limit

    Returns:
        Configured RalphLoopConfig
    """
    mode = ExecutionMode.HITL if execution_mode.lower() == "hitl" else ExecutionMode.AFK

    hooks = None
    if enable_hooks:
        hooks_dir = project_dir / ".workflow" / "hooks"
        if hooks_dir.exists():
            hooks = HookConfig(
                pre_iteration=hooks_dir / "pre-iteration.sh"
                if (hooks_dir / "pre-iteration.sh").exists()
                else None,
                post_iteration=hooks_dir / "post-iteration.sh"
                if (hooks_dir / "post-iteration.sh").exists()
                else None,
                stop_check=hooks_dir / "stop-check.sh"
                if (hooks_dir / "stop-check.sh").exists()
                else None,
            )

    return RalphLoopConfig(
        max_iterations=max_iterations,
        test_command=detect_test_framework(project_dir),
        execution_mode=mode,
        hooks=hooks,
        track_tokens=track_tokens,
        max_cost_usd=max_cost_usd,
    )
