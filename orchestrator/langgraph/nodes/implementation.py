"""Implementation node for Phase 3.

Spawns a worker Claude to implement the approved plan
following TDD practices.

Optimized for production with:
- Proper async subprocess handling with asyncio
- Timeout protection with asyncio.wait_for
- Graceful degradation on partial failures
- Idempotent test verification
"""

import asyncio
import json
import logging
import subprocess
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import WorkflowState, PhaseStatus, PhaseState

logger = logging.getLogger(__name__)

# Configuration
IMPLEMENTATION_TIMEOUT = 1800  # 30 minutes
TEST_TIMEOUT = 300  # 5 minutes
MAX_CONCURRENT_OPERATIONS = 3

IMPLEMENTATION_PROMPT = """You are implementing a software feature based on an approved plan.

IMPLEMENTATION PLAN:
{plan}

{feedback_section}

INSTRUCTIONS:
1. Write tests FIRST (TDD approach)
2. Implement the code to make tests pass
3. Follow the task order and dependencies
4. Follow existing code patterns in the project

For each task you complete, output a JSON object:
{{
    "task_id": "T1",
    "status": "completed",
    "files_created": ["list of new files"],
    "files_modified": ["list of modified files"],
    "tests_written": ["list of test files"],
    "tests_passed": true,
    "notes": "Any implementation notes"
}}

IF YOU NEED CLARIFICATION:
If you encounter an ambiguous requirement, unclear specification, or need guidance that isn't covered in the plan or validation feedback, output:
{{
    "task_id": "T1",
    "status": "needs_clarification",
    "question": "Specific question that needs human input",
    "context": "What you've tried and why you're blocked",
    "options": ["Option A description", "Option B description"],
    "recommendation": "Your recommended approach if you had to choose"
}}
Then STOP and wait. Do NOT make assumptions on critical decisions.

WHEN TO ASK VS PROCEED:
- Minor style choices: Proceed with your best judgment
- Security-related decisions: ASK for clarification
- Architectural choices not in plan: ASK for clarification
- Missing dependency/configuration: ASK for clarification

At the end, provide a summary:
{{
    "implementation_complete": true,
    "all_tests_pass": true,
    "total_files_created": 5,
    "total_files_modified": 3,
    "test_results": {{
        "passed": 10,
        "failed": 0,
        "skipped": 0
    }},
    "clarifications_needed": []
}}"""


async def implementation_node(state: WorkflowState) -> dict[str, Any]:
    """Implement the approved plan.

    Spawns a worker Claude in the project directory to write
    code following the plan and TDD practices.

    Features:
    - Async subprocess execution with timeout protection
    - Graceful degradation if tests don't exist yet
    - Proper error categorization for retry decisions

    Args:
        state: Current workflow state

    Returns:
        State updates with implementation results
    """
    logger.info(f"Starting implementation for: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_3 = phase_status.get("3", PhaseState())
    phase_3.status = PhaseStatus.IN_PROGRESS
    phase_3.started_at = phase_3.started_at or datetime.now().isoformat()
    phase_3.attempts += 1
    phase_status["3"] = phase_3

    if not plan:
        return {
            "phase_status": phase_status,
            "errors": [{
                "type": "implementation_error",
                "message": "No plan to implement",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "abort",
        }

    # Get validation feedback for context
    feedback_section = _build_feedback_section(state)

    # Check for clarification answers from human
    clarification_answers = _load_clarification_answers(project_dir)
    if clarification_answers:
        feedback_section += f"\n\nCLARIFICATION ANSWERS FROM HUMAN:\n{json.dumps(clarification_answers, indent=2)}"
        logger.info(f"Including {len(clarification_answers)} clarification answers")

    prompt = IMPLEMENTATION_PROMPT.format(
        plan=json.dumps(plan, indent=2),
        feedback_section=feedback_section,
    )

    try:
        # Spawn worker Claude with timeout protection
        result = await asyncio.wait_for(
            _run_worker_claude(
                project_dir=project_dir,
                prompt=prompt,
                max_turns=50,
            ),
            timeout=IMPLEMENTATION_TIMEOUT,
        )

        if not result["success"]:
            raise Exception(result.get("error", "Implementation failed"))

        implementation_result = result.get("output", {})

        # Check if worker needs clarification
        clarifications = _extract_clarifications(implementation_result)
        if clarifications:
            logger.info(f"Worker needs clarification on {len(clarifications)} items")
            # Save partial progress and escalate
            impl_dir = project_dir / ".workflow" / "phases" / "implementation"
            impl_dir.mkdir(parents=True, exist_ok=True)
            (impl_dir / "partial_result.json").write_text(json.dumps(implementation_result, indent=2))
            (impl_dir / "clarifications_needed.json").write_text(json.dumps(clarifications, indent=2))

            phase_3.status = PhaseStatus.BLOCKED
            phase_status["3"] = phase_3

            return {
                "phase_status": phase_status,
                "implementation_result": implementation_result,
                "errors": [{
                    "type": "implementation_error",
                    "message": f"Worker needs clarification: {clarifications[0].get('question', 'Unknown')}",
                    "clarifications": clarifications,
                    "timestamp": datetime.now().isoformat(),
                }],
                "next_decision": "escalate",
            }

        # Verify tests pass with graceful degradation
        test_result = await _verify_tests_with_fallback(project_dir, plan)

        if not test_result["success"]:
            if test_result.get("no_tests"):
                # No tests found - this might be OK for initial scaffold
                logger.warning("No tests found, but implementation may still be valid")
                implementation_result["tests_skipped"] = True
            else:
                raise Exception(f"Tests failed: {test_result.get('error', 'Unknown error')}")

        # Save implementation result
        impl_dir = project_dir / ".workflow" / "phases" / "implementation"
        impl_dir.mkdir(parents=True, exist_ok=True)
        (impl_dir / "result.json").write_text(json.dumps(implementation_result, indent=2))

        # Update phase status
        phase_3.status = PhaseStatus.COMPLETED
        phase_3.completed_at = datetime.now().isoformat()
        phase_3.output = implementation_result
        phase_status["3"] = phase_3

        logger.info("Implementation completed successfully")

        return {
            "implementation_result": implementation_result,
            "phase_status": phase_status,
            "current_phase": 4,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }

    except asyncio.TimeoutError:
        logger.error(f"Implementation timed out after {IMPLEMENTATION_TIMEOUT}s")
        return _handle_implementation_error(
            phase_status, phase_3,
            f"Implementation timed out after {IMPLEMENTATION_TIMEOUT // 60} minutes",
            is_transient=False,  # Timeout is not retryable
        )

    except Exception as e:
        logger.error(f"Implementation failed: {e}")
        # Categorize error for retry decision
        is_transient = _is_transient_error(e)
        return _handle_implementation_error(
            phase_status, phase_3,
            str(e),
            is_transient=is_transient,
        )


def _build_feedback_section(state: WorkflowState) -> str:
    """Build feedback section from validation results."""
    feedback_section = ""
    validation_feedback = state.get("validation_feedback", {})
    if validation_feedback:
        concerns = []
        for agent, feedback in validation_feedback.items():
            if hasattr(feedback, "concerns"):
                concerns.extend(feedback.concerns)
        if concerns:
            feedback_section = f"\nVALIDATION FEEDBACK TO ADDRESS:\n{json.dumps(concerns, indent=2)}"
    return feedback_section


def _extract_clarifications(result: dict) -> list[dict]:
    """Extract any clarification requests from implementation result.

    Checks both the raw_output and parsed JSON for tasks with
    status='needs_clarification'.

    Args:
        result: Implementation result from worker Claude

    Returns:
        List of clarification requests, empty if none found
    """
    clarifications = []

    # Check for explicit clarifications_needed array
    if "clarifications_needed" in result and result["clarifications_needed"]:
        clarifications.extend(result["clarifications_needed"])

    # Check raw_output for needs_clarification status
    raw = result.get("raw_output", "")
    if isinstance(raw, str) and "needs_clarification" in raw:
        import re
        # Find JSON blocks with needs_clarification status
        json_blocks = re.findall(r"\{[^{}]*\"status\"[^{}]*\"needs_clarification\"[^{}]*\}", raw)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if parsed.get("status") == "needs_clarification":
                    clarifications.append({
                        "task_id": parsed.get("task_id", "unknown"),
                        "question": parsed.get("question", "Clarification needed"),
                        "context": parsed.get("context", ""),
                        "options": parsed.get("options", []),
                        "recommendation": parsed.get("recommendation", ""),
                    })
            except json.JSONDecodeError:
                continue

    return clarifications


def _load_clarification_answers(project_dir: Path) -> dict:
    """Load any clarification answers from human escalation.

    Args:
        project_dir: Project directory

    Returns:
        Dict of clarification answers, empty if none found
    """
    answers_file = project_dir / ".workflow" / "clarification_answers.json"
    if answers_file.exists():
        try:
            answers = json.loads(answers_file.read_text())
            # Remove timestamp from answers dict for cleaner prompt
            answers.pop("timestamp", None)
            return answers
        except json.JSONDecodeError:
            return {}
    return {}


def _is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and worth retrying."""
    error_str = str(error).lower()
    transient_indicators = [
        "timeout", "connection", "rate limit", "503", "502",
        "temporarily unavailable", "retry", "overloaded"
    ]
    return any(indicator in error_str for indicator in transient_indicators)


def _handle_implementation_error(
    phase_status: dict,
    phase_3: PhaseState,
    error_message: str,
    is_transient: bool = True,
) -> dict[str, Any]:
    """Handle implementation error with proper phase status update."""
    phase_3.error = error_message

    # Check if we can retry (only for transient errors)
    if is_transient and phase_3.attempts < phase_3.max_attempts:
        phase_status["3"] = phase_3
        return {
            "phase_status": phase_status,
            "next_decision": "retry",
            "errors": [{
                "type": "implementation_error",
                "message": error_message,
                "phase": 3,
                "attempt": phase_3.attempts,
                "transient": is_transient,
                "timestamp": datetime.now().isoformat(),
            }],
        }
    else:
        phase_3.status = PhaseStatus.FAILED
        phase_status["3"] = phase_3
        return {
            "phase_status": phase_status,
            "next_decision": "escalate",
            "errors": [{
                "type": "implementation_error",
                "message": f"Implementation failed after {phase_3.attempts} attempts: {error_message}",
                "phase": 3,
                "transient": is_transient,
                "timestamp": datetime.now().isoformat(),
            }],
        }


async def _run_worker_claude(
    project_dir: Path,
    prompt: str,
    max_turns: int = 50,
) -> dict:
    """Run a worker Claude in the project directory.

    Uses asyncio subprocess for proper async execution.

    Args:
        project_dir: Project directory
        prompt: Implementation prompt
        max_turns: Maximum agentic turns

    Returns:
        Result dictionary with success flag and output
    """
    # Build command
    allowed_tools = ",".join([
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

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--allowedTools",
        allowed_tools,
        "--max-turns",
        str(max_turns),
    ]

    try:
        # Use asyncio subprocess for proper async execution
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "dumb"},
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode() if stderr else f"Exit code: {process.returncode}",
            }

        # Try to parse JSON output
        output = _parse_worker_output(stdout.decode() if stdout else "")

        return {
            "success": True,
            "output": output,
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "Claude CLI not found. Ensure 'claude' is installed and in PATH.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _parse_worker_output(stdout: str) -> dict:
    """Parse worker Claude output, handling various formats."""
    if not stdout:
        return {"raw_output": ""}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from text
    import re
    json_match = re.search(r"\{[\s\S]*\}", stdout)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw_output": stdout}


async def _verify_tests_with_fallback(
    project_dir: Path,
    plan: dict,
) -> dict[str, Any]:
    """Verify tests with graceful degradation.

    Args:
        project_dir: Project directory
        plan: Implementation plan with test commands

    Returns:
        Dict with success flag and details
    """
    test_strategy = plan.get("test_strategy", {})
    test_commands = test_strategy.get("test_commands", [])

    if not test_commands:
        # Detect test framework from project
        test_commands = _detect_test_commands(project_dir)

    if not test_commands:
        # Check if any test files exist
        test_files = _find_test_files(project_dir)
        if not test_files:
            logger.info("No test files found - skipping test verification")
            return {"success": True, "no_tests": True}
        # Default to pytest if test files exist
        test_commands = ["pytest"]

    # Try each test command with timeout
    for cmd in test_commands:
        try:
            result = await asyncio.wait_for(
                _run_test_command(project_dir, cmd),
                timeout=TEST_TIMEOUT,
            )
            if result["success"]:
                logger.info(f"Tests passed: {cmd}")
                return {"success": True, "command": cmd, "output": result.get("output")}
        except asyncio.TimeoutError:
            logger.warning(f"Test command timed out: {cmd}")
            continue
        except Exception as e:
            logger.warning(f"Test command failed: {cmd} - {e}")
            continue

    # All test commands failed
    return {
        "success": False,
        "error": f"All test commands failed: {test_commands}",
    }


def _detect_test_commands(project_dir: Path) -> list[str]:
    """Detect test commands from project configuration."""
    commands = []

    # Check for package.json (Node.js)
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text())
            if "scripts" in pkg and "test" in pkg["scripts"]:
                commands.append("npm test")
        except json.JSONDecodeError:
            pass

    # Check for pyproject.toml (Python)
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        commands.append("pytest")

    # Check for Cargo.toml (Rust)
    cargo_toml = project_dir / "Cargo.toml"
    if cargo_toml.exists():
        commands.append("cargo test")

    # Check for go.mod (Go)
    go_mod = project_dir / "go.mod"
    if go_mod.exists():
        commands.append("go test ./...")

    return commands


def _find_test_files(project_dir: Path) -> list[Path]:
    """Find test files in project."""
    patterns = [
        "test_*.py", "*_test.py", "*.test.ts", "*.test.js",
        "*.spec.ts", "*.spec.js", "*_test.go", "*_test.rs"
    ]
    test_files = []
    for pattern in patterns:
        test_files.extend(project_dir.rglob(pattern))
    return test_files


async def _run_test_command(project_dir: Path, cmd: str) -> dict:
    """Run a test command asynchronously."""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd.split(),
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "output": stdout.decode() if stdout else "",
            "error": stderr.decode() if stderr else "",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": f"Command not found: {cmd}",
        }
