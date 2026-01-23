"""Task management API routes."""

import json

# Import orchestrator modules
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_settings
from ..deps import get_audit_adapter, get_project_dir
from ..models import AuditEntry, ErrorResponse, TaskInfo, TaskListResponse, TaskStatus

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.storage.audit_adapter import AuditStorageAdapter

router = APIRouter(prefix="/projects/{project_name}/tasks", tags=["tasks"])


def _load_tasks_from_workflow(project_dir: Path) -> list[dict]:
    """Load tasks from workflow state.

    Args:
        project_dir: Project directory

    Returns:
        List of task dictionaries
    """
    # Try to load from plan.json
    plan_path = project_dir / ".workflow" / "phases" / "planning" / "plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text())
            tasks = plan.get("tasks", [])
            if tasks:
                return tasks
        except (json.JSONDecodeError, OSError):
            pass

    # Try to load from state.json
    state_path = project_dir / ".workflow" / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            tasks = state.get("tasks", [])
            if tasks:
                return tasks
        except (json.JSONDecodeError, OSError):
            pass

    return []


def _get_task_status(task: dict) -> TaskStatus:
    """Convert task status string to enum."""
    status_str = task.get("status", "pending").lower()
    try:
        return TaskStatus(status_str)
    except ValueError:
        return TaskStatus.PENDING


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
    description="Get all tasks for a project.",
    responses={404: {"model": ErrorResponse}},
)
async def list_tasks(
    project_dir: Path = Depends(get_project_dir),
    status: Optional[str] = Query(default=None, description="Filter by status"),
) -> TaskListResponse:
    """List all tasks."""
    tasks_data = _load_tasks_from_workflow(project_dir)

    # Convert to TaskInfo
    tasks = []
    for t in tasks_data:
        task_status = _get_task_status(t)
        if status and task_status.value != status:
            continue

        tasks.append(
            TaskInfo(
                id=t.get("id", ""),
                title=t.get("title", t.get("name", "")),
                description=t.get("description"),
                status=task_status,
                priority=t.get("priority", 0),
                dependencies=t.get("dependencies", t.get("depends_on", [])),
                files_to_create=t.get("files_to_create", []),
                files_to_modify=t.get("files_to_modify", []),
                acceptance_criteria=t.get("acceptance_criteria", []),
                complexity_score=t.get("complexity_score"),
                created_at=t.get("created_at"),
                started_at=t.get("started_at"),
                completed_at=t.get("completed_at"),
                error=t.get("error"),
            )
        )

    # Calculate counts
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

    return TaskListResponse(
        tasks=tasks,
        total=len(tasks),
        completed=completed,
        in_progress=in_progress,
        pending=pending,
        failed=failed,
    )


@router.get(
    "/{task_id}",
    response_model=TaskInfo,
    summary="Get task details",
    description="Get detailed information about a specific task.",
    responses={404: {"model": ErrorResponse}},
)
async def get_task(
    task_id: str,
    project_dir: Path = Depends(get_project_dir),
) -> TaskInfo:
    """Get task details."""
    tasks_data = _load_tasks_from_workflow(project_dir)

    for t in tasks_data:
        if t.get("id") == task_id:
            return TaskInfo(
                id=t.get("id", ""),
                title=t.get("title", t.get("name", "")),
                description=t.get("description"),
                status=_get_task_status(t),
                priority=t.get("priority", 0),
                dependencies=t.get("dependencies", t.get("depends_on", [])),
                files_to_create=t.get("files_to_create", []),
                files_to_modify=t.get("files_to_modify", []),
                acceptance_criteria=t.get("acceptance_criteria", []),
                complexity_score=t.get("complexity_score"),
                created_at=t.get("created_at"),
                started_at=t.get("started_at"),
                completed_at=t.get("completed_at"),
                error=t.get("error"),
            )

    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")


@router.get(
    "/{task_id}/history",
    response_model=list[AuditEntry],
    summary="Get task history",
    description="Get audit history for a specific task.",
    responses={404: {"model": ErrorResponse}},
)
async def get_task_history(
    task_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    audit_adapter: AuditStorageAdapter = Depends(get_audit_adapter),
) -> list[AuditEntry]:
    """Get task audit history."""
    history = audit_adapter.get_task_history(task_id, limit=limit)
    return [
        AuditEntry(
            id=entry.id,
            agent=entry.agent,
            task_id=entry.task_id,
            session_id=entry.session_id,
            prompt_hash=entry.prompt_hash,
            prompt_length=entry.prompt_length,
            command_args=entry.command_args or [],
            exit_code=entry.exit_code,
            status=entry.status,
            duration_seconds=entry.duration_seconds,
            output_length=entry.output_length,
            error_length=entry.error_length,
            parsed_output_type=entry.parsed_output_type,
            cost_usd=entry.cost_usd,
            model=entry.model,
            metadata=entry.metadata or {},
            timestamp=entry.timestamp,
        )
        for entry in history
    ]
