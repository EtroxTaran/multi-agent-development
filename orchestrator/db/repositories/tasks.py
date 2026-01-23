"""Task repository.

Provides task management with dependency tracking and status queries.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Task representation.

    Compatible with existing Task TypedDict.
    Note: project_name removed in schema v2.0.0 (per-project database isolation).
    """

    id: str
    title: str = ""
    user_story: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    priority: str = "medium"
    milestone_id: Optional[str] = None
    estimated_complexity: str = "medium"
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    linear_issue_id: Optional[str] = None
    implementation_notes: str = ""
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.id,
            "title": self.title,
            "user_story": self.user_story,
            "acceptance_criteria": self.acceptance_criteria,
            "dependencies": self.dependencies,
            "status": self.status,
            "priority": self.priority,
            "milestone_id": self.milestone_id,
            "estimated_complexity": self.estimated_complexity,
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "test_files": self.test_files,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "linear_issue_id": self.linear_issue_id,
            "implementation_notes": self.implementation_notes,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary."""

        def parse_datetime(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            return None

        return cls(
            id=data.get("task_id", data.get("id", "")),
            title=data.get("title", ""),
            user_story=data.get("user_story", ""),
            acceptance_criteria=data.get("acceptance_criteria", []),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
            milestone_id=data.get("milestone_id"),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            files_to_create=data.get("files_to_create", []),
            files_to_modify=data.get("files_to_modify", []),
            test_files=data.get("test_files", []),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
            linear_issue_id=data.get("linear_issue_id"),
            implementation_notes=data.get("implementation_notes", ""),
            error=data.get("error"),
            created_at=parse_datetime(data.get("created_at")),
            updated_at=parse_datetime(data.get("updated_at")),
        )


class TaskRepository(BaseRepository[Task]):
    """Repository for tasks.

    Provides task CRUD and status tracking with dependency resolution.
    """

    table_name = "tasks"

    def _to_record(self, data: dict[str, Any]) -> Task:
        return Task.from_dict(data)

    def _from_record(self, task: Task) -> dict[str, Any]:
        return task.to_dict()

    async def create_task(
        self,
        task_id: str,
        title: str,
        user_story: str = "",
        acceptance_criteria: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        priority: str = "medium",
        milestone_id: Optional[str] = None,
        estimated_complexity: str = "medium",
        files_to_create: Optional[list[str]] = None,
        files_to_modify: Optional[list[str]] = None,
        test_files: Optional[list[str]] = None,
        max_attempts: int = 3,
    ) -> Task:
        """Create a new task.

        Note: Database is already scoped to project (schema v2.0.0).

        Args:
            task_id: Unique task identifier
            title: Task title
            user_story: User story description
            acceptance_criteria: List of acceptance criteria
            dependencies: Task IDs this depends on
            priority: Task priority
            milestone_id: Milestone this belongs to
            estimated_complexity: Complexity estimate
            files_to_create: Files to create
            files_to_modify: Files to modify
            test_files: Test files for this task
            max_attempts: Maximum implementation attempts

        Returns:
            Created Task
        """
        now = datetime.now()
        task = Task(
            id=task_id,
            title=title,
            user_story=user_story,
            acceptance_criteria=acceptance_criteria or [],
            dependencies=dependencies or [],
            priority=priority,
            milestone_id=milestone_id,
            estimated_complexity=estimated_complexity,
            files_to_create=files_to_create or [],
            files_to_modify=files_to_modify or [],
            test_files=test_files or [],
            max_attempts=max_attempts,
            created_at=now,
            updated_at=now,
        )

        # Use task_id as record ID (database is already project-scoped)
        await self.create(task.to_dict(), task_id)

        logger.debug(f"Created task {task_id} in project {self.project_name}")
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task if found
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM tasks
                WHERE task_id = $task_id
                LIMIT 1
                """,
                {"task_id": task_id},
            )
            if results:
                return self._to_record(results[0])
            return None

    async def update_task(self, task_id: str, **updates: Any) -> Optional[Task]:
        """Update task fields.

        Args:
            task_id: Task identifier
            **updates: Fields to update

        Returns:
            Updated task
        """
        updates["updated_at"] = datetime.now().isoformat()

        async with get_connection(self.project_name) as conn:
            result = await conn.query(
                """
                UPDATE tasks
                MERGE $updates
                WHERE task_id = $task_id
                RETURN AFTER
                """,
                {
                    "task_id": task_id,
                    "updates": updates,
                },
            )
            if result:
                return self._to_record(result[0])
            return None

    async def set_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> Optional[Task]:
        """Set task status.

        Args:
            task_id: Task identifier
            status: New status (pending, in_progress, completed, failed)
            error: Error message if failed

        Returns:
            Updated task
        """
        updates: dict[str, Any] = {"status": status}
        if error:
            updates["error"] = error

        return await self.update_task(task_id, **updates)

    async def increment_attempts(self, task_id: str) -> Optional[Task]:
        """Increment task attempt counter.

        Args:
            task_id: Task identifier

        Returns:
            Updated task
        """
        async with get_connection(self.project_name) as conn:
            result = await conn.query(
                """
                UPDATE tasks
                SET attempts += 1, updated_at = time::now()
                WHERE task_id = $task_id
                RETURN AFTER
                """,
                {"task_id": task_id},
            )
            if result:
                return self._to_record(result[0])
            return None

    async def get_by_status(self, status: str) -> list[Task]:
        """Get all tasks with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of tasks
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM tasks
                WHERE status = $status
                ORDER BY priority DESC, created_at ASC
                """,
                {"status": status},
            )
            return [self._to_record(r) for r in results]

    async def get_pending_tasks(self) -> list[Task]:
        """Get all pending tasks.

        Returns:
            List of pending tasks
        """
        return await self.get_by_status("pending")

    async def get_completed_tasks(self) -> list[Task]:
        """Get all completed tasks.

        Returns:
            List of completed tasks
        """
        return await self.get_by_status("completed")

    async def get_failed_tasks(self) -> list[Task]:
        """Get all failed tasks.

        Returns:
            List of failed tasks
        """
        return await self.get_by_status("failed")

    async def get_available_tasks(self) -> list[Task]:
        """Get tasks ready to execute (pending with satisfied dependencies).

        Returns:
            List of available tasks
        """
        async with get_connection(self.project_name) as conn:
            # Get completed task IDs
            completed_results = await conn.query(
                """
                SELECT task_id FROM tasks
                WHERE status = "completed"
                """,
            )
            completed_ids = {r["task_id"] for r in completed_results}

            # Get pending tasks
            pending_results = await conn.query(
                """
                SELECT * FROM tasks
                WHERE status = "pending"
                ORDER BY priority DESC, created_at ASC
                """,
            )

            available = []
            for record in pending_results:
                dependencies = record.get("dependencies", [])
                if all(dep in completed_ids for dep in dependencies):
                    available.append(self._to_record(record))

            return available

    async def get_by_milestone(self, milestone_id: str) -> list[Task]:
        """Get all tasks for a milestone.

        Args:
            milestone_id: Milestone identifier

        Returns:
            List of tasks
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM tasks
                WHERE milestone_id = $milestone_id
                ORDER BY created_at ASC
                """,
                {"milestone_id": milestone_id},
            )
            return [self._to_record(r) for r in results]

    async def get_progress(self) -> dict[str, Any]:
        """Get task progress summary.

        Returns:
            Progress dictionary
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT status, count() as count
                FROM tasks
                GROUP BY status
                """,
            )

            progress = {
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "failed": 0,
            }

            for row in results:
                status = row.get("status", "unknown")
                count = row.get("count", 0)
                progress["total"] += count
                if status in progress:
                    progress[status] = count

            if progress["total"] > 0:
                progress["completion_rate"] = progress["completed"] / progress["total"]
            else:
                progress["completion_rate"] = 0.0

            return progress

    async def bulk_create(self, tasks: list[dict[str, Any]]) -> list[Task]:
        """Create multiple tasks at once.

        Args:
            tasks: List of task data dictionaries

        Returns:
            List of created tasks
        """
        created = []
        for task_data in tasks:
            task = await self.create_task(
                task_id=task_data["id"],
                title=task_data.get("title", ""),
                user_story=task_data.get("user_story", ""),
                acceptance_criteria=task_data.get("acceptance_criteria", []),
                dependencies=task_data.get("dependencies", []),
                priority=task_data.get("priority", "medium"),
                milestone_id=task_data.get("milestone_id"),
                estimated_complexity=task_data.get("estimated_complexity", "medium"),
                files_to_create=task_data.get("files_to_create", []),
                files_to_modify=task_data.get("files_to_modify", []),
                test_files=task_data.get("test_files", []),
                max_attempts=task_data.get("max_attempts", 3),
            )
            created.append(task)

        logger.info(f"Created {len(created)} tasks for {self.project_name}")
        return created

    async def watch_tasks(
        self,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """Subscribe to task changes via Live Query.

        Args:
            callback: Function to call on task changes

        Returns:
            Live query UUID
        """
        async with get_connection(self.project_name) as conn:
            return await conn.live(self.table_name, callback)


# Global repository cache
_task_repos: dict[str, TaskRepository] = {}


def get_task_repository(project_name: str) -> TaskRepository:
    """Get or create task repository for a project.

    Args:
        project_name: Project name

    Returns:
        TaskRepository instance
    """
    if project_name not in _task_repos:
        _task_repos[project_name] = TaskRepository(project_name)
    return _task_repos[project_name]
