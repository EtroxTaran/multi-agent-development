"""Test pass gate node.

Final verification that ALL tests pass before marking a project complete.
This node blocks completion if any tests fail and routes back to implementation
for fixes.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...config import load_project_config
from ...validators import EnvironmentChecker
from ..state import WorkflowState, create_error_context

logger = logging.getLogger(__name__)

# Maximum retry attempts before escalating to human
MAX_TEST_GATE_ATTEMPTS = 3


async def test_pass_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Final verification that all tests pass before completion.

    This node:
    1. Runs all project tests using the detected test framework
    2. Blocks completion if any tests fail
    3. Routes back to task_subgraph for fixes if failures occur
    4. Tracks retry attempts to prevent infinite loops
    5. Escalates to human after MAX_TEST_GATE_ATTEMPTS

    Args:
        state: Current workflow state

    Returns:
        State updates with test results and routing decision
    """
    project_dir = Path(state["project_dir"])
    project_name = state["project_name"]
    logger.info(f"Running test pass gate for: {project_name}")

    # Track attempts
    current_attempts = state.get("test_gate_attempts", 0) + 1
    logger.info(f"Test gate attempt {current_attempts}/{MAX_TEST_GATE_ATTEMPTS}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if test gate is enabled (default: True)
    if hasattr(config.workflow.features, "test_pass_gate"):
        if not config.workflow.features.test_pass_gate:
            logger.info("Test pass gate disabled in config, skipping")
            return {
                "test_gate_attempts": current_attempts,
                "updated_at": datetime.now().isoformat(),
                "next_decision": "continue",
            }

    # Get test command from environment check or implementation result
    test_command = _get_test_command(state, project_dir)

    if not test_command:
        logger.warning("No test command detected - allowing completion with warning")
        test_results = {
            "status": "skipped",
            "reason": "no_test_command_detected",
            "timestamp": datetime.now().isoformat(),
        }
        return {
            "test_gate_attempts": current_attempts,
            "test_gate_results": test_results,
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Run tests
    test_results = _run_tests(project_dir, test_command)

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(project_name)
    run_async(
        repo.save_output(
            phase=4,
            output_type="test_pass_gate",
            content={
                "attempt": current_attempts,
                **test_results,
            },
        )
    )

    # Check results
    if test_results["status"] == "passed":
        logger.info(
            f"All tests passed: {test_results.get('passed', 0)} passed, "
            f"{test_results.get('failed', 0)} failed"
        )
        return {
            "test_gate_attempts": current_attempts,
            "test_gate_results": test_results,
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Tests failed
    failed_count = test_results.get("failed", 0)
    total_count = test_results.get("total", 0)
    logger.warning(f"Test gate failed: {failed_count}/{total_count} tests failing")

    # Check if we've exceeded max attempts
    if current_attempts >= MAX_TEST_GATE_ATTEMPTS:
        logger.error(f"Test gate failed after {current_attempts} attempts - escalating to human")

        # Create error context for escalation
        error_ctx = create_error_context(
            source_node="test_pass_gate",
            exception=Exception(
                f"Tests still failing after {current_attempts} attempts: "
                f"{failed_count} failing tests"
            ),
            state=dict(state),  # Cast TypedDict to dict for compatibility
            recoverable=False,
            suggested_actions=[
                "Review failing tests manually",
                "Check for flaky tests",
                "Verify test environment setup",
                "Consider disabling blocking tests temporarily",
            ],
        )

        return {
            "test_gate_attempts": current_attempts,
            "test_gate_results": test_results,
            "errors": [error_ctx],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Route back to implementation for fixes
    logger.info(f"Routing back to task_subgraph for test fixes (attempt {current_attempts})")

    return {
        "test_gate_attempts": current_attempts,
        "test_gate_results": test_results,
        "errors": [
            {
                "type": "tests_failing",
                "message": f"{failed_count} tests failing - routing back to implementation",
                "failed_tests": test_results.get("failed_tests", [])[:20],
                "output": test_results.get("output", "")[:2000],
                "timestamp": datetime.now().isoformat(),
            }
        ],
        "next_decision": "retry",
        "updated_at": datetime.now().isoformat(),
    }


def _get_test_command(state: WorkflowState, project_dir: Path) -> Optional[str]:
    """Get the test command for the project.

    Checks in order:
    1. Implementation result from pre_implementation check
    2. Run environment detection

    Args:
        state: Current workflow state
        project_dir: Project directory

    Returns:
        Test command string or None
    """
    # Check if we already have it from pre_implementation
    impl_result = state.get("implementation_result")
    if isinstance(impl_result, dict):
        env_info = impl_result.get("environment")
        if isinstance(env_info, dict):
            test_cmd = env_info.get("test_command")
            if isinstance(test_cmd, str):
                return test_cmd

    # Run environment detection
    checker = EnvironmentChecker(project_dir)
    result = checker.check()

    return result.test_command if result.test_command else None


def _run_tests(project_dir: Path, test_command: str) -> dict[str, Any]:
    """Run tests and parse results.

    Args:
        project_dir: Project directory
        test_command: Test command to run

    Returns:
        Dictionary with test results
    """
    logger.info(f"Running tests: {test_command}")

    try:
        # Run tests with timeout (5 minutes for large test suites)
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes
        )

        output = result.stdout + result.stderr
        exit_code = result.returncode

        # Parse test results
        test_info = _parse_test_output(output, test_command)

        if exit_code == 0:
            return {
                "status": "passed",
                "exit_code": exit_code,
                "passed": test_info.get("passed", 0),
                "failed": 0,
                "skipped": test_info.get("skipped", 0),
                "total": test_info.get("total", 0),
                "output": output[-5000:],  # Last 5000 chars
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "status": "failed",
                "exit_code": exit_code,
                "passed": test_info.get("passed", 0),
                "failed": test_info.get("failed", 1),  # At least 1 failed
                "skipped": test_info.get("skipped", 0),
                "total": test_info.get("total", 0),
                "failed_tests": test_info.get("failed_tests", []),
                "output": output[-5000:],  # Last 5000 chars
                "timestamp": datetime.now().isoformat(),
            }

    except subprocess.TimeoutExpired:
        logger.error(f"Test command timed out after 5 minutes: {test_command}")
        return {
            "status": "timeout",
            "exit_code": -1,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "error": "Test command timed out after 5 minutes",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return {
            "status": "error",
            "exit_code": -1,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def _parse_test_output(output: str, test_command: str) -> dict[str, Any]:
    """Parse test output to extract pass/fail counts.

    Supports multiple test frameworks:
    - Jest/Vitest: "Tests: X passed, Y failed, Z total"
    - pytest: "X passed, Y failed, Z skipped"
    - Go: "PASS/FAIL"
    - Generic: exit code only

    Args:
        output: Test command output
        test_command: Test command that was run

    Returns:
        Dictionary with parsed counts
    """
    import re

    result: dict[str, Any] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "failed_tests": [],
    }

    # Jest/Vitest style: "Tests:       5 passed, 2 failed, 7 total"
    jest_match = re.search(
        r"Tests:\s*(\d+)\s*passed,?\s*(\d+)?\s*failed?,?\s*(\d+)?\s*skipped?,?\s*(\d+)\s*total",
        output,
        re.IGNORECASE,
    )
    if jest_match:
        result["passed"] = int(jest_match.group(1) or 0)
        result["failed"] = int(jest_match.group(2) or 0)
        result["skipped"] = int(jest_match.group(3) or 0)
        result["total"] = int(jest_match.group(4) or 0)
        return result

    # Alternative Jest format: "5 passed, 2 failed"
    alt_jest_match = re.search(
        r"(\d+)\s*passed,?\s*(\d+)\s*failed",
        output,
        re.IGNORECASE,
    )
    if alt_jest_match:
        result["passed"] = int(alt_jest_match.group(1))
        result["failed"] = int(alt_jest_match.group(2))
        result["total"] = result["passed"] + result["failed"]
        return result

    # pytest style: "5 passed, 2 failed, 1 skipped in 1.23s"
    pytest_match = re.search(
        r"(\d+)\s*passed(?:,\s*(\d+)\s*failed)?(?:,\s*(\d+)\s*skipped)?",
        output,
        re.IGNORECASE,
    )
    if pytest_match:
        result["passed"] = int(pytest_match.group(1) or 0)
        result["failed"] = int(pytest_match.group(2) or 0)
        result["skipped"] = int(pytest_match.group(3) or 0)
        result["total"] = result["passed"] + result["failed"] + result["skipped"]
        return result

    # Go test style: "ok" or "FAIL"
    if "go test" in test_command:
        ok_count = len(re.findall(r"^ok\s+", output, re.MULTILINE))
        fail_count = len(re.findall(r"^FAIL\s+", output, re.MULTILINE))
        result["passed"] = ok_count
        result["failed"] = fail_count
        result["total"] = ok_count + fail_count
        return result

    # Rust cargo test: "X passed; Y failed"
    rust_match = re.search(r"(\d+)\s*passed;\s*(\d+)\s*failed", output)
    if rust_match:
        result["passed"] = int(rust_match.group(1))
        result["failed"] = int(rust_match.group(2))
        result["total"] = result["passed"] + result["failed"]
        return result

    # Extract failed test names (common patterns)
    failed_patterns = [
        r"FAIL\s+([^\s]+)",  # Jest/Vitest
        r"FAILED\s+([^\s]+)",  # pytest
        r"--- FAIL:\s+(\S+)",  # Go
    ]
    for pattern in failed_patterns:
        matches = re.findall(pattern, output)
        if matches:
            result["failed_tests"].extend(matches[:20])  # Limit to 20

    return result
