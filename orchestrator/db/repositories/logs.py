"""Logs repository for storing workflow artifacts.

Stores various workflow artifacts that don't fit in phase_outputs:
- uat_document: User Acceptance Test documents per task
- handoff_brief: Session resume documents
- discussion: Discussion phase notes
- research: Research findings
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


# Log type constants
class LogType:
    """Log type constants."""

    UAT_DOCUMENT = "uat_document"
    HANDOFF_BRIEF = "handoff_brief"
    DISCUSSION = "discussion"
    RESEARCH = "research"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class LogEntry:
    """Log entry record."""

    log_type: str
    content: dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        # Remove None values and id (managed by SurrealDB)
        return {k: v for k, v in data.items() if v is not None and k != "id"}


class LogsRepository(BaseRepository[LogEntry]):
    """Repository for log entries."""

    table_name = "logs"

    def _to_record(self, data: dict[str, Any]) -> LogEntry:
        """Convert database record to LogEntry."""
        return LogEntry(
            id=str(data.get("id", "")),
            log_type=data.get("log_type", ""),
            content=data.get("content", {}),
            task_id=data.get("task_id"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
        )

    async def create_log(
        self,
        log_type: str,
        content: dict[str, Any],
        task_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Create a new log entry.

        Args:
            log_type: Type of log (see LogType constants)
            content: Log content as dictionary
            task_id: Optional associated task ID
            metadata: Optional additional metadata

        Returns:
            Created LogEntry record
        """
        async with get_connection(self.project_name) as conn:
            data = {
                "log_type": log_type,
                "content": content,
                "task_id": task_id,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat(),
            }
            result = await conn.create(self.table_name, data)
            return self._to_record(result)

    async def get_by_type(
        self,
        log_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """Get logs by type.

        Args:
            log_type: Type of logs to retrieve
            limit: Maximum records to return
            offset: Number of records to skip

        Returns:
            List of log entries
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM logs
                WHERE log_type = $log_type
                ORDER BY created_at DESC
                LIMIT $limit START $offset
                """,
                {"log_type": log_type, "limit": limit, "offset": offset},
            )
            return [self._to_record(r) for r in results]

    async def get_by_task(
        self,
        task_id: str,
        log_type: Optional[str] = None,
    ) -> list[LogEntry]:
        """Get logs for a specific task.

        Args:
            task_id: Task identifier
            log_type: Optional type filter

        Returns:
            List of log entries for the task
        """
        async with get_connection(self.project_name) as conn:
            if log_type:
                results = await conn.query(
                    """
                    SELECT * FROM logs
                    WHERE task_id = $task_id AND log_type = $log_type
                    ORDER BY created_at DESC
                    """,
                    {"task_id": task_id, "log_type": log_type},
                )
            else:
                results = await conn.query(
                    """
                    SELECT * FROM logs
                    WHERE task_id = $task_id
                    ORDER BY created_at DESC
                    """,
                    {"task_id": task_id},
                )
            return [self._to_record(r) for r in results]

    async def get_latest(
        self,
        log_type: str,
        task_id: Optional[str] = None,
    ) -> Optional[LogEntry]:
        """Get the most recent log of a specific type.

        Args:
            log_type: Type of log
            task_id: Optional task filter

        Returns:
            Most recent LogEntry or None
        """
        async with get_connection(self.project_name) as conn:
            if task_id:
                results = await conn.query(
                    """
                    SELECT * FROM logs
                    WHERE log_type = $log_type AND task_id = $task_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    {"log_type": log_type, "task_id": task_id},
                )
            else:
                results = await conn.query(
                    """
                    SELECT * FROM logs
                    WHERE log_type = $log_type
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    {"log_type": log_type},
                )

            if results:
                return self._to_record(results[0])
            return None

    # Convenience methods for common log types

    async def save_uat_document(
        self,
        task_id: str,
        document: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Save a UAT document for a task.

        Args:
            task_id: Task identifier
            document: UAT document content
            metadata: Optional metadata

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.UAT_DOCUMENT,
            document,
            task_id=task_id,
            metadata=metadata,
        )

    async def get_uat_document(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get the UAT document for a task.

        Args:
            task_id: Task identifier

        Returns:
            UAT document content or None
        """
        entry = await self.get_latest(LogType.UAT_DOCUMENT, task_id)
        return entry.content if entry else None

    async def save_handoff_brief(
        self,
        brief: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Save a handoff brief for session resume.

        Args:
            brief: Handoff brief content
            metadata: Optional metadata

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.HANDOFF_BRIEF,
            brief,
            metadata=metadata,
        )

    async def get_latest_handoff_brief(self) -> Optional[dict[str, Any]]:
        """Get the most recent handoff brief.

        Returns:
            Handoff brief content or None
        """
        entry = await self.get_latest(LogType.HANDOFF_BRIEF)
        return entry.content if entry else None

    async def save_discussion(
        self,
        discussion: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Save discussion phase notes.

        Args:
            discussion: Discussion content
            metadata: Optional metadata

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.DISCUSSION,
            discussion,
            metadata=metadata,
        )

    async def save_research(
        self,
        findings: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Save research findings.

        Args:
            findings: Research findings content
            metadata: Optional metadata

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.RESEARCH,
            findings,
            metadata=metadata,
        )

    async def log_error(
        self,
        error_message: str,
        task_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> LogEntry:
        """Log an error.

        Args:
            error_message: Error message
            task_id: Optional associated task
            context: Optional error context

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.ERROR,
            {"message": error_message, "context": context or {}},
            task_id=task_id,
        )

    async def log_debug(
        self,
        message: str,
        data: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> LogEntry:
        """Log debug information.

        Args:
            message: Debug message
            data: Optional debug data
            task_id: Optional associated task

        Returns:
            Created log entry
        """
        return await self.create_log(
            LogType.DEBUG,
            {"message": message, "data": data or {}},
            task_id=task_id,
        )

    async def clear_by_type(self, log_type: str) -> int:
        """Clear all logs of a specific type.

        Args:
            log_type: Type of logs to clear

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                DELETE FROM logs
                WHERE log_type = $log_type
                RETURN BEFORE
                """,
                {"log_type": log_type},
            )
            return len(results)

    async def clear_by_task(self, task_id: str) -> int:
        """Clear all logs for a specific task.

        Args:
            task_id: Task identifier

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                DELETE FROM logs
                WHERE task_id = $task_id
                RETURN BEFORE
                """,
                {"task_id": task_id},
            )
            return len(results)

    async def prune_old_logs(self, days: int = 30) -> int:
        """Delete logs older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                DELETE FROM logs
                WHERE created_at < time::now() - $days * 1d
                RETURN BEFORE
                """,
                {"days": days},
            )
            return len(results)


# Global repository cache
_repos: dict[str, LogsRepository] = {}


def get_logs_repository(project_name: str) -> LogsRepository:
    """Get or create a logs repository for a project.

    Args:
        project_name: Project name

    Returns:
        LogsRepository instance
    """
    if project_name not in _repos:
        _repos[project_name] = LogsRepository(project_name)
    return _repos[project_name]
