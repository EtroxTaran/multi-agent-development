"""Audit trail repository.

Provides queryable audit logging that replaces JSONL-based trail.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """Audit log entry for CLI invocations.

    Compatible with existing AuditEntry from audit/trail.py.
    Note: project_name removed in schema v2.0.0 (per-project database isolation).
    """

    id: str
    agent: str
    task_id: str
    session_id: Optional[str] = None
    prompt_hash: str = ""
    prompt_length: int = 0
    command_args: list[str] = field(default_factory=list)
    exit_code: int = 0
    status: str = "pending"
    duration_seconds: float = 0.0
    output_length: int = 0
    error_length: int = 0
    parsed_output_type: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "entry_id": self.id,
            "agent": self.agent,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "prompt_hash": self.prompt_hash,
            "prompt_length": self.prompt_length,
            "command_args": self.command_args,
            "exit_code": self.exit_code,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "output_length": self.output_length,
            "error_length": self.error_length,
            "parsed_output_type": self.parsed_output_type,
            "cost_usd": self.cost_usd,
            "model": self.model,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEntry":
        """Create from database record."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            id=data.get("entry_id", data.get("id", "")),
            agent=data.get("agent", ""),
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id"),
            prompt_hash=data.get("prompt_hash", ""),
            prompt_length=data.get("prompt_length", 0),
            command_args=data.get("command_args", []),
            exit_code=data.get("exit_code", 0),
            status=data.get("status", "pending"),
            duration_seconds=data.get("duration_seconds", 0.0),
            output_length=data.get("output_length", 0),
            error_length=data.get("error_length", 0),
            parsed_output_type=data.get("parsed_output_type"),
            cost_usd=data.get("cost_usd"),
            model=data.get("model"),
            metadata=data.get("metadata", {}),
            timestamp=timestamp,
        )


@dataclass
class AuditStatistics:
    """Audit statistics summary."""

    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    by_agent: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)


class AuditRepository(BaseRepository[AuditEntry]):
    """Repository for audit entries.

    Provides queryable audit logging with full SQL support.
    """

    table_name = "audit_entries"

    def _to_record(self, data: dict[str, Any]) -> AuditEntry:
        return AuditEntry.from_dict(data)

    def _from_record(self, entry: AuditEntry) -> dict[str, Any]:
        return entry.to_dict()

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        """Create SHA-256 hash of prompt for privacy."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    async def create_entry(
        self,
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command_args: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> AuditEntry:
        """Create a new audit entry.

        Note: Database is already scoped to project (schema v2.0.0).

        Args:
            agent: Agent identifier (claude, cursor, gemini)
            task_id: Task this invocation belongs to
            prompt: The prompt being sent
            session_id: Session ID if using continuity
            command_args: CLI arguments
            metadata: Additional metadata

        Returns:
            Created AuditEntry
        """
        timestamp = datetime.now()
        entry_id = f"audit-{timestamp.strftime('%Y%m%d%H%M%S')}-{agent}-{task_id}"

        entry = AuditEntry(
            id=entry_id,
            agent=agent,
            task_id=task_id,
            session_id=session_id,
            prompt_hash=self._hash_prompt(prompt),
            prompt_length=len(prompt),
            command_args=command_args or [],
            metadata=metadata or {},
            timestamp=timestamp,
        )

        await self.create(entry.to_dict(), entry_id)
        return entry

    async def update_result(
        self,
        entry_id: str,
        success: bool,
        exit_code: int,
        duration_seconds: float,
        output_length: int = 0,
        error_length: int = 0,
        cost_usd: Optional[float] = None,
        model: Optional[str] = None,
        parsed_output_type: Optional[str] = None,
    ) -> Optional[AuditEntry]:
        """Update entry with execution result.

        Args:
            entry_id: Entry identifier
            success: Whether invocation succeeded
            exit_code: Process exit code
            duration_seconds: Execution duration
            output_length: Length of stdout
            error_length: Length of stderr
            cost_usd: Cost if available
            model: Model used
            parsed_output_type: Type of parsed output

        Returns:
            Updated entry
        """
        data = {
            "status": "success" if success else "failed",
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "output_length": output_length,
            "error_length": error_length,
        }

        if cost_usd is not None:
            data["cost_usd"] = cost_usd
        if model:
            data["model"] = model
        if parsed_output_type:
            data["parsed_output_type"] = parsed_output_type

        return await self.update(entry_id, data)

    async def mark_timeout(self, entry_id: str, timeout_seconds: float) -> Optional[AuditEntry]:
        """Mark entry as timed out.

        Args:
            entry_id: Entry identifier
            timeout_seconds: Timeout duration

        Returns:
            Updated entry
        """
        return await self.update(
            entry_id,
            {
                "status": "timeout",
                "duration_seconds": timeout_seconds,
                "exit_code": -1,
            },
        )

    async def mark_error(self, entry_id: str, error_message: str) -> Optional[AuditEntry]:
        """Mark entry as errored.

        Args:
            entry_id: Entry identifier
            error_message: Error description

        Returns:
            Updated entry
        """
        async with get_connection(self.project_name) as conn:
            # Get current entry to preserve metadata
            results = await conn.select(f"{self.table_name}:{entry_id}")
            if not results:
                return None

            current = results[0]
            metadata = current.get("metadata", {})
            metadata["error_message"] = error_message

            return await self.update(
                entry_id,
                {
                    "status": "error",
                    "metadata": metadata,
                },
            )

    async def find_by_task(
        self,
        task_id: str,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Find all entries for a task.

        Args:
            task_id: Task identifier
            limit: Maximum entries

        Returns:
            List of entries, chronologically ordered
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM audit_entries
                WHERE task_id = $task_id
                ORDER BY timestamp ASC
                LIMIT $limit
                """,
                {
                    "task_id": task_id,
                    "limit": limit,
                },
            )
            return [self._to_record(r) for r in results]

    async def find_by_agent(
        self,
        agent: str,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Find all entries for an agent.

        Args:
            agent: Agent identifier
            limit: Maximum entries

        Returns:
            List of entries
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM audit_entries
                WHERE agent = $agent
                ORDER BY timestamp DESC
                LIMIT $limit
                """,
                {
                    "agent": agent,
                    "limit": limit,
                },
            )
            return [self._to_record(r) for r in results]

    async def find_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Find entries by status.

        Args:
            status: Status to filter (success, failed, timeout, error)
            limit: Maximum entries

        Returns:
            List of entries
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM audit_entries
                WHERE status = $status
                ORDER BY timestamp DESC
                LIMIT $limit
                """,
                {
                    "status": status,
                    "limit": limit,
                },
            )
            return [self._to_record(r) for r in results]

    async def find_since(
        self,
        since: datetime,
        until: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """Find entries in a time range.

        Args:
            since: Start time (inclusive)
            until: End time (exclusive, default now)
            limit: Maximum entries

        Returns:
            List of entries
        """
        until = until or datetime.now()

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM audit_entries
                WHERE timestamp >= $since
                    AND timestamp < $until
                ORDER BY timestamp ASC
                LIMIT $limit
                """,
                {
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "limit": limit,
                },
            )
            return [self._to_record(r) for r in results]

    async def find_failures(
        self,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Find recent failures for debugging.

        Args:
            since: Start time (default last 24 hours)
            limit: Maximum entries

        Returns:
            List of failed entries
        """
        since = since or (datetime.now() - timedelta(days=1))

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM audit_entries
                WHERE timestamp >= $since
                    AND status IN ["failed", "timeout", "error"]
                ORDER BY timestamp DESC
                LIMIT $limit
                """,
                {
                    "since": since.isoformat(),
                    "limit": limit,
                },
            )
            return [self._to_record(r) for r in results]

    async def get_statistics(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AuditStatistics:
        """Get audit statistics.

        Args:
            since: Start time (default all time)
            until: End time (default now)

        Returns:
            AuditStatistics summary
        """
        time_filter = ""
        params: dict[str, Any] = {}

        if since:
            time_filter += (
                " AND timestamp >= $since" if time_filter else "WHERE timestamp >= $since"
            )
            params["since"] = since.isoformat()
        if until:
            time_filter += " AND timestamp < $until" if time_filter else "WHERE timestamp < $until"
            params["until"] = until.isoformat()

        async with get_connection(self.project_name) as conn:
            # Get counts by status
            base_query = f"""
                SELECT
                    count() as total,
                    status,
                    math::sum(duration_seconds) as total_duration,
                    math::sum(cost_usd) as total_cost
                FROM audit_entries
                {time_filter}
                GROUP BY status
            """
            results = await conn.query(base_query, params)

            stats = AuditStatistics()

            for row in results:
                status = row.get("status", "unknown")
                count = row.get("total", 0)
                duration = row.get("total_duration", 0) or 0
                cost = row.get("total_cost", 0) or 0

                stats.total += count
                stats.total_duration_seconds += duration
                stats.total_cost_usd += cost
                stats.by_status[status] = count

                if status == "success":
                    stats.success_count = count
                elif status == "failed":
                    stats.failed_count = count
                elif status == "timeout":
                    stats.timeout_count = count

            if stats.total > 0:
                stats.success_rate = stats.success_count / stats.total
                stats.avg_duration_seconds = stats.total_duration_seconds / stats.total

            # Get counts by agent
            agent_query = f"""
                SELECT agent, count() as total
                FROM audit_entries
                {time_filter}
                GROUP BY agent
            """
            agent_results = await conn.query(agent_query, params)

            for row in agent_results:
                agent = row.get("agent", "unknown")
                count = row.get("total", 0)
                stats.by_agent[agent] = count

            return stats

    async def get_cost_by_task(self) -> dict[str, float]:
        """Get total cost per task.

        Returns:
            Dictionary mapping task_id to total cost
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT task_id, math::sum(cost_usd) as total_cost
                FROM audit_entries
                WHERE cost_usd != NONE
                GROUP BY task_id
                """,
            )

            return {row.get("task_id", ""): row.get("total_cost", 0) or 0 for row in results}

    async def cleanup_old_entries(self, days: int = 30) -> int:
        """Remove entries older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of entries deleted
        """
        cutoff = datetime.now() - timedelta(days=days)

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                DELETE FROM audit_entries
                WHERE timestamp < $cutoff
                RETURN BEFORE
                """,
                {"cutoff": cutoff.isoformat()},
            )
            count = len(results)
            if count > 0:
                logger.info(f"Cleaned up {count} old audit entries")
            return count


# Global repository cache
_audit_repos: dict[str, AuditRepository] = {}


def get_audit_repository(project_name: str) -> AuditRepository:
    """Get or create audit repository for a project.

    Args:
        project_name: Project name

    Returns:
        AuditRepository instance
    """
    if project_name not in _audit_repos:
        _audit_repos[project_name] = AuditRepository(project_name)
    return _audit_repos[project_name]
