"""Database service for SurrealDB integration.

Provides database access for complex queries and live subscriptions.
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for SurrealDB database operations.

    Provides:
    - Query execution
    - Live query subscriptions
    - Data aggregation
    """

    def __init__(self, project_name: Optional[str] = None):
        """Initialize database service.

        Args:
            project_name: Optional project name for database selection
        """
        self.project_name = project_name
        self.settings = get_settings()
        self._connection = None

    @property
    def is_enabled(self) -> bool:
        """Check if SurrealDB is enabled."""
        return self.settings.use_surrealdb

    async def get_connection(self):
        """Get database connection.

        Returns:
            Database connection
        """
        if not self.is_enabled:
            raise RuntimeError("SurrealDB is not enabled")

        if self._connection is None:
            try:
                from orchestrator.db import get_connection

                self._connection = await get_connection()
            except ImportError:
                raise RuntimeError("SurrealDB module not available")

        return self._connection

    async def query(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a query.

        Args:
            sql: SurrealQL query
            params: Query parameters

        Returns:
            Query results
        """
        conn = await self.get_connection()
        result = await conn.query(sql, params or {})
        return result

    async def get_workflow_state(self, project_dir: Path) -> Optional[dict]:
        """Get workflow state from database.

        Args:
            project_dir: Project directory

        Returns:
            Workflow state or None
        """
        result = await self.query(
            "SELECT * FROM workflow_state WHERE project_dir = $dir LIMIT 1",
            {"dir": str(project_dir)},
        )
        return result[0] if result else None

    async def get_tasks(
        self,
        project_name: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get tasks from database.

        Args:
            project_name: Project name
            status: Optional status filter
            limit: Maximum tasks to return

        Returns:
            List of tasks
        """
        if status:
            result = await self.query(
                "SELECT * FROM tasks WHERE project = $project AND status = $status ORDER BY created_at DESC LIMIT $limit",
                {"project": project_name, "status": status, "limit": limit},
            )
        else:
            result = await self.query(
                "SELECT * FROM tasks WHERE project = $project ORDER BY created_at DESC LIMIT $limit",
                {"project": project_name, "limit": limit},
            )
        return result

    async def get_audit_entries(
        self,
        project_name: str,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get audit entries from database.

        Args:
            project_name: Project name
            agent: Optional agent filter
            task_id: Optional task ID filter
            since: Optional time filter
            limit: Maximum entries to return

        Returns:
            List of audit entries
        """
        conditions = ["project = $project"]
        params = {"project": project_name, "limit": limit}

        if agent:
            conditions.append("agent = $agent")
            params["agent"] = agent

        if task_id:
            conditions.append("task_id = $task_id")
            params["task_id"] = task_id

        if since:
            conditions.append("timestamp >= $since")
            params["since"] = since.isoformat()

        where_clause = " AND ".join(conditions)
        result = await self.query(
            f"SELECT * FROM audit_entries WHERE {where_clause} ORDER BY timestamp DESC LIMIT $limit",
            params,
        )
        return result

    async def get_audit_statistics(
        self,
        project_name: str,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get audit statistics from database.

        Args:
            project_name: Project name
            since: Optional time filter

        Returns:
            Statistics dictionary
        """
        time_filter = ""
        params = {"project": project_name}

        if since:
            time_filter = "AND timestamp >= $since"
            params["since"] = since.isoformat()

        result = await self.query(
            f"""
            SELECT
                count() as total,
                count() FILTER WHERE status = 'success' as success_count,
                count() FILTER WHERE status = 'failed' as failed_count,
                count() FILTER WHERE status = 'timeout' as timeout_count,
                math::sum(cost_usd) as total_cost_usd,
                math::sum(duration_seconds) as total_duration_seconds,
                math::mean(duration_seconds) as avg_duration_seconds
            FROM audit_entries
            WHERE project = $project {time_filter}
            """,
            params,
        )

        if result:
            stats = result[0]
            total = stats.get("total", 0)
            return {
                "total": total,
                "success_count": stats.get("success_count", 0),
                "failed_count": stats.get("failed_count", 0),
                "timeout_count": stats.get("timeout_count", 0),
                "success_rate": stats.get("success_count", 0) / total if total > 0 else 0,
                "total_cost_usd": stats.get("total_cost_usd", 0) or 0,
                "total_duration_seconds": stats.get("total_duration_seconds", 0) or 0,
                "avg_duration_seconds": stats.get("avg_duration_seconds", 0) or 0,
            }

        return {
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "timeout_count": 0,
            "success_rate": 0,
            "total_cost_usd": 0,
            "total_duration_seconds": 0,
            "avg_duration_seconds": 0,
        }

    async def subscribe_to_changes(
        self,
        table: str,
        filter_clause: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Subscribe to table changes.

        Args:
            table: Table name
            filter_clause: Optional WHERE clause

        Yields:
            Change events
        """
        conn = await self.get_connection()

        query = f"LIVE SELECT * FROM {table}"
        if filter_clause:
            query += f" WHERE {filter_clause}"

        async for change in conn.live_query(query):
            yield change
