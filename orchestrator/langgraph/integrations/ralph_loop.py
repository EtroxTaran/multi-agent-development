"""Ralph Wiggum loop integration.

Implements the Ralph Wiggum iterative execution pattern for TDD-based
task implementation. Each iteration starts a fresh Claude context,
runs tests, and continues until all tests pass.

Key principles:
- Fresh context per iteration (avoids degradation)
- Tests as backpressure (natural completion signal)
- <promise>DONE</promise> pattern for completion detection
- Configurable max iterations as safety limit

Reference: https://github.com/anthropics/claude-code/discussions/1278
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Completion promise pattern
COMPLETION_PROMISE = "<promise>DONE</promise>"


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
    """

    max_iterations: int = 10
    iteration_timeout: int = 300  # 5 minutes per iteration
    test_command: str = "pytest"
    completion_pattern: str = COMPLETION_PROMISE
    allowed_tools: list[str] = field(default_factory=lambda: [
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
    ])
    max_turns_per_iteration: int = 15
    save_iteration_logs: bool = True


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
    """

    success: bool
    iterations: int
    final_output: Optional[dict] = None
    test_results: list[dict] = field(default_factory=list)
    total_time_seconds: float = 0.0
    completion_reason: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "iterations": self.iterations,
            "final_output": self.final_output,
            "test_results": self.test_results,
            "total_time_seconds": self.total_time_seconds,
            "completion_reason": self.completion_reason,
            "error": self.error,
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
) -> RalphLoopResult:
    """Execute the Ralph Wiggum loop for a task.

    Iteratively runs Claude with fresh context until tests pass
    or max iterations reached.

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

    logger.info(f"Starting Ralph Wiggum loop for task {task_id}")

    while iteration < config.max_iterations:
        iteration += 1
        logger.info(f"Ralph loop iteration {iteration}/{config.max_iterations}")

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

            # Save iteration log
            if config.save_iteration_logs:
                _save_iteration_log(project_dir, task_id, iteration, result)

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
                )

            # Check if tests pass
            test_result = await _run_tests(project_dir, test_files, config)
            test_results.append({
                "iteration": iteration,
                "passed": test_result["all_passed"],
                "summary": test_result.get("summary", ""),
            })

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
                )

            # Build context for next iteration
            previous_context = _build_previous_context(
                iteration=iteration,
                test_result=test_result,
                changes_made=result.get("files_changed", []),
            )

        except asyncio.TimeoutError:
            logger.warning(f"Ralph loop iteration {iteration} timed out")
            test_results.append({
                "iteration": iteration,
                "passed": False,
                "summary": "Iteration timed out",
            })
            previous_context = f"PREVIOUS ITERATION {iteration}: Timed out. Please continue from where you left off."

        except Exception as e:
            logger.error(f"Ralph loop iteration {iteration} failed: {e}")
            test_results.append({
                "iteration": iteration,
                "passed": False,
                "summary": str(e),
            })
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
        files_changed = parsed_output.get("files_modified", []) + parsed_output.get("files_created", [])

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

    except Exception as e:
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
