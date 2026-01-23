"""Verify task node.

Verifies that a completed task meets its acceptance criteria
by running tests and checking file changes.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import (
    WorkflowState,
    Task,
    TaskStatus,
    get_task_by_id,
)
from ..integrations import (
    create_linear_adapter,
    load_issue_mapping,
    create_markdown_tracker,
)
from ..integrations.board_sync import sync_board
from orchestrator.utils.uat_generator import UATGenerator, create_uat_generator

logger = logging.getLogger(__name__)

# Configuration
TEST_TIMEOUT = 120  # 2 minutes for task tests


async def verify_task_node(state: WorkflowState) -> dict[str, Any]:
    """Verify the current task implementation.

    Verification steps:
    1. Run task-specific tests
    2. Check that required files exist
    3. Mark task as completed or failed
    4. Update completed_task_ids

    Args:
        state: Current workflow state

    Returns:
        State updates with verification result
    """
    task_id = state.get("current_task_id")
    if not task_id:
        return {
            "errors": [{
                "type": "verify_task_error",
                "message": "No task selected for verification",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    task = get_task_by_id(state, task_id)
    if not task:
        return {
            "errors": [{
                "type": "verify_task_error",
                "message": f"Task {task_id} not found",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    logger.info(f"Verifying task: {task_id} - {task.get('title', 'Unknown')}")

    project_dir = Path(state["project_dir"])
    updated_task = dict(task)

    try:
        # 1. Check file creation
        files_check = _verify_files_created(project_dir, task)

        # 2. Run task tests
        test_result = await _run_task_tests(project_dir, task)

        # 3. Evaluate overall result
        if not files_check["success"]:
            return _handle_verification_failure(
                updated_task,
                f"Missing files: {files_check.get('missing', [])}",
                project_dir,
            )

        if not test_result["success"]:
            if test_result.get("no_tests"):
                logger.warning(f"No tests for task {task_id} - accepting implementation")
            else:
                return _handle_verification_failure(
                    updated_task,
                    f"Tests failed: {test_result.get('error', 'Unknown')}",
                    project_dir,
                )

        # Task verified successfully
        updated_task["status"] = TaskStatus.COMPLETED

        # Save verification result
        _save_verification_result(project_dir, task_id, {
            "files_check": files_check,
            "test_result": test_result,
            "verified_at": datetime.now().isoformat(),
        }, state["project_name"])

        # Generate UAT document (GSD pattern)
        _generate_task_uat(
            project_dir=project_dir,
            task=task,
            phase=state.get("current_phase", 3),
            test_output=test_result.get("output", ""),
            project_name=state["project_name"],
        )

        # Update task status in trackers
        completion_notes = "Task verified successfully - all tests passed"
        _update_task_trackers_on_completion(
            project_dir, task_id, TaskStatus.COMPLETED, completion_notes
        )

        logger.info(f"Task {task_id} verified successfully")

        # Sync to Kanban board
        try:
            tasks = state.get("tasks", [])
            updated_tasks_list = [t for t in tasks if t["id"] != task_id] + [updated_task]
            sync_state = dict(state)
            sync_state["tasks"] = updated_tasks_list
            sync_board(sync_state)
        except Exception as e:
            logger.warning(f"Failed to sync board in verify task: {e}")

        return {
            "tasks": [updated_task],
            "completed_task_ids": [task_id],
            "current_task_id": None,  # Clear current task
            "current_task_ids": [],
            "in_flight_task_ids": [],
            "next_decision": "continue",  # Loop back to select_task
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Verification error for task {task_id}: {e}")
        return _handle_verification_failure(updated_task, str(e), project_dir)


async def verify_tasks_parallel_node(state: WorkflowState) -> dict[str, Any]:
    """Verify a batch of task implementations.

    Args:
        state: Current workflow state

    Returns:
        State updates with verification results
    """
    task_ids = state.get("current_task_ids", [])
    if not task_ids:
        return {
            "errors": [{
                "type": "verify_task_error",
                "message": "No task batch selected for verification",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    project_dir = Path(state["project_dir"])
    updated_tasks_map = {}
    errors: list[dict] = []
    failed_task_ids: list[str] = []
    completed_task_ids: list[str] = []
    retry_task_ids: list[str] = []
    should_escalate = False

    for task_id in task_ids:
        task = get_task_by_id(state, task_id)
        if not task:
            errors.append({
                "type": "verify_task_error",
                "message": f"Task {task_id} not found",
                "timestamp": datetime.now().isoformat(),
            })
            should_escalate = True
            continue

        updated_task = dict(task)
        try:
            files_check = _verify_files_created(project_dir, task)
            test_result = await _run_task_tests(project_dir, task)

            if not files_check["success"]:
                failure = _handle_verification_failure(
                    updated_task,
                    f"Missing files: {files_check.get('missing', [])}",
                    project_dir,
                )
                updated_task = failure["tasks"][0]
                errors.extend(failure.get("errors", []))
                failed_task_ids.extend(failure.get("failed_task_ids", []))
                if failure.get("next_decision") == "retry":
                    retry_task_ids.append(task_id)
                else:
                    should_escalate = True
                updated_tasks_map[task_id] = updated_task
                continue

            if not test_result["success"]:
                if not test_result.get("no_tests"):
                    failure = _handle_verification_failure(
                        updated_task,
                        f"Tests failed: {test_result.get('error', 'Unknown')}",
                        project_dir,
                    )
                    updated_task = failure["tasks"][0]
                    errors.extend(failure.get("errors", []))
                    failed_task_ids.extend(failure.get("failed_task_ids", []))
                    if failure.get("next_decision") == "retry":
                        retry_task_ids.append(task_id)
                    else:
                        should_escalate = True
                    updated_tasks_map[task_id] = updated_task
                    continue

            # Task verified successfully
            updated_task["status"] = TaskStatus.COMPLETED
            completed_task_ids.append(task_id)

            _save_verification_result(project_dir, task_id, {
                "files_check": files_check,
                "test_result": test_result,
                "verified_at": datetime.now().isoformat(),
            }, state["project_name"])

            # Generate UAT document (GSD pattern)
            _generate_task_uat(
                project_dir=project_dir,
                task=task,
                phase=state.get("current_phase", 3),
                test_output=test_result.get("output", ""),
                project_name=state["project_name"],
            )

            completion_notes = "Task verified successfully - all tests passed"
            _update_task_trackers_on_completion(
                project_dir, task_id, TaskStatus.COMPLETED, completion_notes
            )

            updated_tasks_map[task_id] = updated_task

        except Exception as e:
            failure = _handle_verification_failure(updated_task, str(e), project_dir)
            updated_task = failure["tasks"][0]
            errors.extend(failure.get("errors", []))
            failed_task_ids.extend(failure.get("failed_task_ids", []))
            if failure.get("next_decision") == "retry":
                retry_task_ids.append(task_id)
            else:
                should_escalate = True
            updated_tasks_map[task_id] = updated_task

    # Sync to Kanban board
    try:
        tasks = state.get("tasks", [])
        updated_task_ids = set(updated_tasks_map.keys())
        updated_tasks_list = [t for t in tasks if t["id"] not in updated_task_ids] + list(updated_tasks_map.values())
        sync_state = dict(state)
        sync_state["tasks"] = updated_tasks_list
        sync_board(sync_state)
    except Exception as e:
        logger.warning(f"Failed to sync board in parallel verify: {e}")

    next_decision = "continue"
    current_task_ids = []
    in_flight_task_ids = []
    current_task_id = None

    if should_escalate:
        next_decision = "escalate"
    elif retry_task_ids:
        next_decision = "retry"
        current_task_ids = retry_task_ids
        in_flight_task_ids = retry_task_ids
        current_task_id = retry_task_ids[0]

    return {
        "tasks": list(updated_tasks_map.values()),
        "completed_task_ids": completed_task_ids,
        "failed_task_ids": failed_task_ids,
        "errors": errors,
        "current_task_id": current_task_id,
        "current_task_ids": current_task_ids,
        "in_flight_task_ids": in_flight_task_ids,
        "next_decision": next_decision,
        "updated_at": datetime.now().isoformat(),
    }


def _verify_files_created(project_dir: Path, task: Task) -> dict:
    """Verify that files to create exist.

    Args:
        project_dir: Project directory
        task: Task with files_to_create

    Returns:
        Result dict with success flag and missing files
    """
    files_to_create = task.get("files_to_create", [])

    if not files_to_create:
        return {"success": True, "checked": 0}

    missing = []
    for file_path in files_to_create:
        full_path = project_dir / file_path
        if not full_path.exists():
            missing.append(file_path)

    return {
        "success": len(missing) == 0,
        "checked": len(files_to_create),
        "missing": missing,
    }


async def _run_task_tests(project_dir: Path, task: Task) -> dict:
    """Run tests for the specific task.

    Args:
        project_dir: Project directory
        task: Task with test_files

    Returns:
        Result dict with success flag
    """
    test_files = task.get("test_files", [])

    if not test_files:
        # Check if test files exist anyway
        test_files = _find_task_test_files(project_dir, task)
        if not test_files:
            return {"success": True, "no_tests": True}

    # Detect test command
    test_cmd = _detect_test_command(project_dir)
    if not test_cmd:
        logger.warning("Could not detect test command")
        return {"success": True, "no_tests": True}

    # Build test command for specific files
    try:
        if "pytest" in test_cmd:
            # Run only specific test files
            existing_tests = [f for f in test_files if (project_dir / f).exists()]
            if not existing_tests:
                return {"success": True, "no_tests": True}
            cmd_parts = ["pytest", "-v"] + existing_tests

        elif "npm test" in test_cmd or "jest" in test_cmd:
            # For Jest/npm, use pattern matching
            patterns = [Path(f).stem for f in test_files]
            pattern = "|".join(patterns)
            cmd_parts = ["npm", "test", "--", f"--testPathPattern={pattern}"]

        elif "cargo test" in test_cmd:
            # For Rust, run specific tests
            cmd_parts = ["cargo", "test"]

        elif "go test" in test_cmd:
            # For Go, run tests in directory
            cmd_parts = ["go", "test", "-v", "./..."]

        else:
            cmd_parts = test_cmd.split()

        result = await asyncio.wait_for(
            _run_command(project_dir, cmd_parts),
            timeout=TEST_TIMEOUT,
        )

        return {
            "success": result["returncode"] == 0,
            "output": result.get("stdout", ""),
            "error": result.get("stderr", "") if result["returncode"] != 0 else None,
        }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Tests timed out after {TEST_TIMEOUT}s",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _find_task_test_files(project_dir: Path, task: Task) -> list[str]:
    """Find test files related to task's source files.

    Args:
        project_dir: Project directory
        task: Task with files

    Returns:
        List of test file paths
    """
    test_files = []
    all_files = task.get("files_to_create", []) + task.get("files_to_modify", [])

    for file_path in all_files:
        path = Path(file_path)
        ext = path.suffix
        name = path.stem

        # Common test file patterns
        patterns = [
            f"test_{name}{ext}",
            f"{name}_test{ext}",
            f"{name}.test{ext}",
            f"{name}.spec{ext}",
        ]

        for pattern in patterns:
            test_path = path.parent / pattern
            full_path = project_dir / test_path
            if full_path.exists():
                test_files.append(str(test_path))

    return test_files


def _detect_test_command(project_dir: Path) -> Optional[str]:
    """Detect the test command for the project.

    Args:
        project_dir: Project directory

    Returns:
        Test command string or None
    """
    # Check package.json
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text())
            if "scripts" in pkg and "test" in pkg["scripts"]:
                return "npm test"
        except json.JSONDecodeError:
            pass

    # Check for Python
    if (project_dir / "pyproject.toml").exists() or (project_dir / "pytest.ini").exists():
        return "pytest"

    # Check for Rust
    if (project_dir / "Cargo.toml").exists():
        return "cargo test"

    # Check for Go
    if (project_dir / "go.mod").exists():
        return "go test ./..."

    return None


async def _run_command(project_dir: Path, cmd_parts: list[str]) -> dict:
    """Run a command asynchronously.

    Args:
        project_dir: Working directory
        cmd_parts: Command parts

    Returns:
        Result dict with returncode, stdout, stderr
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
        }

    except FileNotFoundError:
        return {
            "returncode": 1,
            "stderr": f"Command not found: {cmd_parts[0]}",
        }


def _save_verification_result(project_dir: Path, task_id: str, result: dict, project_name: str) -> None:
    """Save task verification result to database.

    Args:
        project_dir: Project directory (unused - DB storage)
        task_id: Task ID
        result: Verification result
        project_name: Project name for DB storage
    """
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(project_name)
    run_async(repo.save_output(phase=4, output_type="task_verification", content=result, task_id=task_id))


def _handle_verification_failure(
    task: Task,
    error_message: str,
    project_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Handle task verification failure.

    Args:
        task: Task that failed verification
        error_message: Error message
        project_dir: Optional project directory for tracker updates

    Returns:
        State update with error and retry/escalate decision
    """
    task_id = task.get("id", "unknown")
    max_attempts = task.get("max_attempts", 3)
    attempts = task.get("attempts", 1)

    task["error"] = error_message

    if attempts >= max_attempts:
        # Max retries exceeded
        task["status"] = TaskStatus.FAILED
        logger.error(f"Task {task_id} failed verification after {attempts} attempts")

        # Update trackers with failure status
        if project_dir:
            _update_task_trackers_on_completion(
                project_dir, task_id, TaskStatus.FAILED, error_message
            )

        return {
            "tasks": [task],
            "failed_task_ids": [task_id],
            "current_task_id": None,
            "errors": [{
                "type": "task_verification_failed",
                "task_id": task_id,
                "message": f"Task failed after {attempts} attempts: {error_message}",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Can retry - go back to implement_task
        task["status"] = TaskStatus.PENDING
        logger.warning(f"Task {task_id} verification failed, will retry (attempt {attempts}/{max_attempts})")

        return {
            "tasks": [task],
            "errors": [{
                "type": "task_verification_failed",
                "task_id": task_id,
                "message": error_message,
                "attempt": attempts,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "retry",  # Retry the same task
            "updated_at": datetime.now().isoformat(),
        }


def _update_task_trackers_on_completion(
    project_dir: Path,
    task_id: str,
    status: TaskStatus,
    notes: Optional[str] = None,
) -> None:
    """Update task status in markdown tracker and Linear on completion.

    Args:
        project_dir: Project directory
        task_id: Task ID
        status: Final status (COMPLETED or FAILED)
        notes: Completion/failure notes
    """
    try:
        # Update markdown tracker
        markdown_tracker = create_markdown_tracker(project_dir)
        markdown_tracker.update_task_status(task_id, status, notes)
    except Exception as e:
        logger.warning(f"Failed to update markdown tracker for task {task_id}: {e}")

    try:
        # Update Linear (if configured and issue exists)
        linear_adapter = create_linear_adapter(project_dir)
        if linear_adapter.enabled:
            # Load issue mapping to populate cache
            issue_mapping = load_issue_mapping(project_dir)
            linear_adapter._issue_cache.update(issue_mapping)

            # Update status
            linear_adapter.update_issue_status(task_id, status)

            # Add completion comment
            if status == TaskStatus.COMPLETED and notes:
                linear_adapter.add_completion_comment(task_id, notes)
            elif status == TaskStatus.FAILED and notes:
                linear_adapter.add_blocker_comment(task_id, notes)

    except Exception as e:
        logger.warning(f"Failed to update Linear for task {task_id}: {e}")


def _generate_task_uat(
    project_dir: Path,
    task: Task,
    phase: int,
    test_output: str = "",
    git_diff: str = "",
    project_name: str = "",
) -> None:
    """Generate UAT document for a completed task.

    Args:
        project_dir: Project directory
        task: Completed task
        phase: Current phase number
        test_output: Test command output
        git_diff: Git diff output
        project_name: Project name for DB storage
    """
    try:
        uat_generator = create_uat_generator(project_dir)

        # Get git diff for the task files if not provided
        if not git_diff:
            git_diff = _get_task_git_diff(project_dir, task)

        uat = uat_generator.generate_from_task(
            task=task,
            phase=phase,
            test_output=test_output,
            git_diff=git_diff,
        )

        # Save to database
        from ...db.repositories.logs import get_logs_repository
        from ...storage.async_utils import run_async

        task_id = task.get("id", "unknown")
        repo = get_logs_repository(project_name or project_dir.name)
        run_async(repo.create_log(log_type="uat_document", task_id=task_id, content=uat.to_dict() if hasattr(uat, "to_dict") else uat))

        logger.info(f"Generated UAT document for task {task_id} saved to database")

    except Exception as e:
        logger.warning(f"Failed to generate UAT for task {task.get('id')}: {e}")


def _get_task_git_diff(project_dir: Path, task: Task) -> str:
    """Get git diff for task files.

    Args:
        project_dir: Project directory
        task: Task with file information

    Returns:
        Git diff output string
    """
    try:
        import subprocess

        # Get all task-related files
        files = (
            task.get("files_to_create", [])
            + task.get("files_to_modify", [])
            + task.get("test_files", [])
        )

        if not files:
            return ""

        # Run git diff for staged and unstaged changes
        result = subprocess.run(
            ["git", "diff", "HEAD", "--"] + files,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        return result.stdout if result.returncode == 0 else ""

    except Exception as e:
        logger.warning(f"Failed to get git diff for task: {e}")
        return ""
