"""Task management API routes."""

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
from orchestrator.db.repositories.tasks import Task, get_task_repository
from orchestrator.storage.audit_adapter import AuditStorageAdapter

router = APIRouter(prefix="/projects/{project_name}/tasks", tags=["tasks"])


def _priority_to_int(priority: str) -> int:
    """Convert priority string to integer for sorting.

    Args:
        priority: Priority string (low, medium, high, critical)

    Returns:
        Integer priority value (0-3)
    """
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(priority.lower(), 1)


def _complexity_to_score(complexity: str) -> Optional[float]:
    """Convert complexity string to numeric score.

    Args:
        complexity: Complexity string (low, medium, high)

    Returns:
        Numeric complexity score or None
    """
    return {"low": 2.0, "medium": 5.0, "high": 8.0}.get(complexity.lower())


def _task_to_task_info(task: Task) -> TaskInfo:
    """Convert repository Task to API TaskInfo.

    Args:
        task: Task from repository

    Returns:
        TaskInfo for API response
    """
    # Map status string to TaskStatus enum
    status_str = task.status.lower() if task.status else "pending"
    try:
        status = TaskStatus(status_str)
    except ValueError:
        status = TaskStatus.PENDING

    return TaskInfo(
        id=task.id,
        title=task.title,
        description=task.user_story or None,
        status=status,
        priority=_priority_to_int(task.priority),
        dependencies=task.dependencies,
        files_to_create=task.files_to_create,
        files_to_modify=task.files_to_modify,
        acceptance_criteria=task.acceptance_criteria,
        complexity_score=_complexity_to_score(task.estimated_complexity),
        created_at=task.created_at.isoformat() if task.created_at else None,
        started_at=None,  # Not tracked in repository yet
        completed_at=None,  # Not tracked in repository yet
        error=task.error,
    )


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
    description="Get all tasks for a project.",
    responses={404: {"model": ErrorResponse}},
)
async def list_tasks(
    project_name: str,
    project_dir: Path = Depends(get_project_dir),
    status: Optional[str] = Query(default=None, description="Filter by status"),
) -> TaskListResponse:
    """List all tasks from SurrealDB."""
    repo = get_task_repository(project_name)

    try:
        # Fetch tasks from database
        if status:
            db_tasks = await repo.get_by_status(status)
        else:
            db_tasks = await repo.find_all(limit=1000)

        # Convert to TaskInfo
        tasks = [_task_to_task_info(t) for t in db_tasks]

        # Get progress summary from database
        progress = await repo.get_progress()

        return TaskListResponse(
            tasks=tasks,
            total=progress.get("total", len(tasks)),
            completed=progress.get("completed", 0),
            in_progress=progress.get("in_progress", 0),
            pending=progress.get("pending", 0),
            failed=progress.get("failed", 0),
        )
    except Exception as e:
        # Log error but return empty response rather than failing
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to fetch tasks from database: {e}")
        return TaskListResponse(
            tasks=[],
            total=0,
            completed=0,
            in_progress=0,
            pending=0,
            failed=0,
        )


@router.get(
    "/{task_id}",
    response_model=TaskInfo,
    summary="Get task details",
    description="Get detailed information about a specific task.",
    responses={404: {"model": ErrorResponse}},
)
async def get_task(
    project_name: str,
    task_id: str,
    project_dir: Path = Depends(get_project_dir),
) -> TaskInfo:
    """Get task details from SurrealDB."""
    repo = get_task_repository(project_name)

    try:
        task = await repo.get_task(task_id)
        if task:
            return _task_to_task_info(task)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to fetch task {task_id} from database: {e}")

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
