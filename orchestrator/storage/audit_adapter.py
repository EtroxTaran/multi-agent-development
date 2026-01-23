"""Audit storage adapter.

Provides unified interface for audit logging using SurrealDB.
This is the DB-only version - no file fallback.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .async_utils import run_async
from .base import AuditEntryData, AuditStatisticsData, AuditStorageProtocol

logger = logging.getLogger(__name__)


class AuditRecordContext:
    """Context manager for recording audit entries.

    Tracks timing and commits entry on exit.
    """

    def __init__(
        self,
        adapter: "AuditStorageAdapter",
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command_args: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ):
        self._adapter = adapter
        self._agent = agent
        self._task_id = task_id
        self._prompt = prompt
        self._session_id = session_id
        self._command_args = command_args or []
        self._metadata = metadata or {}

        self._start_time: Optional[datetime] = None
        self._entry_id: Optional[str] = None

        # Result tracking
        self._success: bool = False
        self._exit_code: int = 0
        self._output_length: int = 0
        self._error_length: int = 0
        self._cost_usd: Optional[float] = None
        self._model: Optional[str] = None
        self._parsed_output_type: Optional[str] = None

    def set_result(
        self,
        success: bool,
        exit_code: int = 0,
        output_length: int = 0,
        error_length: int = 0,
        cost_usd: Optional[float] = None,
        model: Optional[str] = None,
        parsed_output_type: Optional[str] = None,
    ) -> None:
        """Set the result of the invocation.

        Args:
            success: Whether the invocation succeeded
            exit_code: Process exit code
            output_length: Length of stdout
            error_length: Length of stderr
            cost_usd: Cost in USD if available
            model: Model used if specified
            parsed_output_type: Type of parsed output
        """
        self._success = success
        self._exit_code = exit_code
        self._output_length = output_length
        self._error_length = error_length
        self._cost_usd = cost_usd
        self._model = model
        self._parsed_output_type = parsed_output_type

    def set_timeout(self, timeout_seconds: float) -> None:
        """Mark the invocation as timed out."""
        self._success = False
        self._exit_code = -1

    def set_error(self, error_message: str) -> None:
        """Mark the invocation as errored."""
        self._success = False


class AuditStorageAdapter(AuditStorageProtocol):
    """Storage adapter for audit logging.

    Uses SurrealDB as the only storage backend. No file fallback.

    Usage:
        adapter = AuditStorageAdapter(project_dir)

        # Record an invocation (context manager)
        with adapter.record("claude", "T1", prompt) as entry:
            result = run_cli_command(...)
            entry.set_result(result.success, result.exit_code)

        # Query history
        history = adapter.get_task_history("T1")

        # Get statistics
        stats = adapter.get_statistics()
    """

    def __init__(
        self,
        project_dir: Path,
        project_name: Optional[str] = None,
    ):
        """Initialize audit storage adapter.

        Args:
            project_dir: Project directory
            project_name: Project name (defaults to directory name)
        """
        self.project_dir = Path(project_dir)
        self.project_name = project_name or self.project_dir.name
        self._db_backend: Optional[Any] = None

    def _get_db_backend(self) -> Any:
        """Get or create database backend."""
        if self._db_backend is None:
            from orchestrator.db.repositories.audit import get_audit_repository

            self._db_backend = get_audit_repository(self.project_name)
        return self._db_backend

    @contextmanager
    def record(
        self,
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command_args: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Generator[AuditRecordContext, None, None]:
        """Start recording an audit entry.

        Returns a context manager that tracks the invocation.

        Args:
            agent: Agent identifier (claude, cursor, gemini)
            task_id: Task this invocation belongs to
            prompt: The prompt being sent
            session_id: Session ID if using session continuity
            command_args: CLI arguments
            metadata: Additional metadata

        Yields:
            Context for recording the invocation result
        """
        ctx = AuditRecordContext(
            adapter=self,
            agent=agent,
            task_id=task_id,
            prompt=prompt,
            session_id=session_id,
            command_args=command_args,
            metadata=metadata,
        )

        ctx._start_time = datetime.now()

        # Create entry in database
        db = self._get_db_backend()
        entry = run_async(
            db.create_entry(
                agent=agent,
                task_id=task_id,
                prompt=prompt,
                session_id=session_id,
                command_args=command_args,
                metadata=metadata,
            )
        )
        ctx._entry_id = entry.id

        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e))
            raise
        finally:
            # Commit the entry
            self._commit_entry(ctx)

    def _commit_entry(self, ctx: AuditRecordContext) -> None:
        """Commit a completed audit entry."""
        duration = 0.0
        if ctx._start_time:
            duration = (datetime.now() - ctx._start_time).total_seconds()

        if ctx._entry_id:
            db = self._get_db_backend()
            run_async(
                db.update_result(
                    entry_id=ctx._entry_id,
                    success=ctx._success,
                    exit_code=ctx._exit_code,
                    duration_seconds=duration,
                    output_length=ctx._output_length,
                    error_length=ctx._error_length,
                    cost_usd=ctx._cost_usd,
                    model=ctx._model,
                    parsed_output_type=ctx._parsed_output_type,
                )
            )

    def get_task_history(self, task_id: str, limit: int = 100) -> list[AuditEntryData]:
        """Get audit history for a task.

        Args:
            task_id: Task identifier
            limit: Maximum entries to return

        Returns:
            List of audit entries, chronologically ordered
        """
        db = self._get_db_backend()
        entries = run_async(db.find_by_task(task_id, limit=limit))
        return [self._db_entry_to_data(e) for e in entries]

    def get_statistics(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AuditStatisticsData:
        """Get audit statistics.

        Args:
            since: Start of time range
            until: End of time range

        Returns:
            Statistics summary
        """
        db = self._get_db_backend()
        stats = run_async(db.get_statistics(since=since, until=until))
        return AuditStatisticsData(
            total=stats.total,
            success_count=stats.success_count,
            failed_count=stats.failed_count,
            timeout_count=stats.timeout_count,
            success_rate=stats.success_rate,
            total_cost_usd=stats.total_cost_usd,
            total_duration_seconds=stats.total_duration_seconds,
            avg_duration_seconds=stats.avg_duration_seconds,
            by_agent=stats.by_agent,
            by_status=stats.by_status,
        )

    def query(
        self,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditEntryData]:
        """Query audit entries with filters.

        Args:
            agent: Filter by agent
            task_id: Filter by task ID
            status: Filter by status
            since: Filter entries after this time
            limit: Maximum entries to return

        Returns:
            List of matching entries
        """
        db = self._get_db_backend()

        # Use appropriate query method based on filters
        if task_id:
            entries = run_async(db.find_by_task(task_id, limit=limit))
        elif agent:
            entries = run_async(db.find_by_agent(agent, limit=limit))
        elif status:
            entries = run_async(db.find_by_status(status, limit=limit))
        elif since:
            entries = run_async(db.find_since(since, limit=limit))
        else:
            entries = run_async(db.find_all(limit=limit))

        return [self._db_entry_to_data(e) for e in entries]

    @staticmethod
    def _db_entry_to_data(entry: Any) -> AuditEntryData:
        """Convert database entry to data class."""
        return AuditEntryData(
            id=entry.id,
            agent=entry.agent,
            task_id=entry.task_id,
            session_id=entry.session_id,
            prompt_hash=entry.prompt_hash,
            prompt_length=entry.prompt_length,
            command_args=entry.command_args,
            exit_code=entry.exit_code,
            status=entry.status,
            duration_seconds=entry.duration_seconds,
            output_length=entry.output_length,
            error_length=entry.error_length,
            parsed_output_type=entry.parsed_output_type,
            cost_usd=entry.cost_usd,
            model=entry.model,
            metadata=entry.metadata,
            timestamp=entry.timestamp,
        )


# Cache of adapters per project
_audit_adapters: dict[str, AuditStorageAdapter] = {}


def get_audit_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> AuditStorageAdapter:
    """Get or create audit storage adapter for a project.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        AuditStorageAdapter instance
    """
    key = str(Path(project_dir).resolve())

    if key not in _audit_adapters:
        _audit_adapters[key] = AuditStorageAdapter(project_dir, project_name)
    return _audit_adapters[key]
