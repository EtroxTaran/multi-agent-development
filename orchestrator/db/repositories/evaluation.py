"""Repository for agent evaluations.

Provides CRUD operations for G-Eval evaluation results.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


class EvaluationRepository(BaseRepository[dict]):
    """Repository for agent_evaluations table."""

    table_name = "agent_evaluations"

    async def save(self, evaluation) -> dict:
        """Save an evaluation result.

        Args:
            evaluation: EvaluationResult from the evaluator

        Returns:
            Saved record
        """
        data = evaluation.to_dict() if hasattr(evaluation, 'to_dict') else dict(evaluation)
        record_id = data.get("evaluation_id", "").replace("eval-", "")

        return await self.create(data, record_id)

    async def get_by_agent(
        self,
        agent: str,
        limit: int = 100,
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """Get evaluations for a specific agent.

        Args:
            agent: Agent name (claude, cursor, gemini)
            limit: Maximum results
            min_score: Minimum score filter

        Returns:
            List of evaluations
        """
        params = {"agent": agent, "limit": limit}
        if min_score is not None:
            score_filter = "AND overall_score >= $min_score"
            params["min_score"] = min_score
        else:
            score_filter = ""

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent {score_filter}
                ORDER BY created_at DESC
                LIMIT $limit
                """,
                params,
            )
            return results

    async def get_by_node(
        self,
        node: str,
        limit: int = 100,
    ) -> list[dict]:
        """Get evaluations for a specific node.

        Args:
            node: LangGraph node name
            limit: Maximum results

        Returns:
            List of evaluations
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE node = $node
                ORDER BY created_at DESC
                LIMIT $limit
                """,
                {"node": node, "limit": limit},
            )
            return results

    async def get_by_task(self, task_id: str) -> list[dict]:
        """Get evaluations for a specific task.

        Args:
            task_id: Task ID

        Returns:
            List of evaluations
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE task_id = $task_id
                ORDER BY created_at DESC
                """,
                {"task_id": task_id},
            )
            return results

    async def get_by_prompt_hash(self, prompt_hash: str) -> list[dict]:
        """Get evaluations for a specific prompt hash.

        Args:
            prompt_hash: Hash of the prompt

        Returns:
            List of evaluations
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE prompt_hash = $prompt_hash
                ORDER BY created_at DESC
                """,
                {"prompt_hash": prompt_hash},
            )
            return results

    async def get_history(
        self,
        agent: Optional[str] = None,
        node: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get historical evaluations with optional filters.

        Args:
            agent: Filter by agent
            node: Filter by node
            task_id: Filter by task ID
            limit: Maximum results

        Returns:
            List of evaluations
        """
        filters = []
        params = {"limit": limit}

        if agent:
            filters.append("agent = $agent")
            params["agent"] = agent
        if node:
            filters.append("node = $node")
            params["node"] = node
        if task_id:
            filters.append("task_id = $task_id")
            params["task_id"] = task_id

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                {where_clause}
                ORDER BY created_at DESC
                LIMIT $limit
                """,
                params,
            )
            return results

    async def get_low_scoring(
        self,
        threshold: float = 7.0,
        limit: int = 50,
    ) -> list[dict]:
        """Get evaluations below a score threshold.

        Args:
            threshold: Score threshold
            limit: Maximum results

        Returns:
            List of low-scoring evaluations
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE overall_score < $threshold
                ORDER BY overall_score ASC
                LIMIT $limit
                """,
                {"threshold": threshold, "limit": limit},
            )
            return results

    async def get_high_scoring(
        self,
        threshold: float = 9.0,
        limit: int = 50,
    ) -> list[dict]:
        """Get evaluations above a score threshold.

        Args:
            threshold: Score threshold
            limit: Maximum results

        Returns:
            List of high-scoring evaluations
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE overall_score >= $threshold
                ORDER BY overall_score DESC
                LIMIT $limit
                """,
                {"threshold": threshold, "limit": limit},
            )
            return results

    async def get_statistics(
        self,
        agent: Optional[str] = None,
        days: int = 30,
    ) -> dict:
        """Get evaluation statistics.

        Args:
            agent: Filter by agent
            days: Number of days to include

        Returns:
            Statistics dictionary
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        agent_filter = "AND agent = $agent" if agent else ""
        params = {"cutoff": cutoff}
        if agent:
            params["agent"] = agent

        async with get_connection(self.project_name) as conn:
            # Get overall stats
            stats = await conn.query(
                f"""
                SELECT
                    count() as total,
                    math::mean(overall_score) as avg_score,
                    math::min(overall_score) as min_score,
                    math::max(overall_score) as max_score
                FROM {self.table_name}
                WHERE created_at >= $cutoff {agent_filter}
                GROUP ALL
                """,
                params,
            )

            # Get per-agent breakdown
            by_agent = await conn.query(
                f"""
                SELECT
                    agent,
                    count() as total,
                    math::mean(overall_score) as avg_score
                FROM {self.table_name}
                WHERE created_at >= $cutoff
                GROUP BY agent
                """,
                {"cutoff": cutoff},
            )

            return {
                "overall": stats[0] if stats else {},
                "by_agent": by_agent,
                "period_days": days,
            }

    async def cleanup_old_evaluations(self, retention_days: int = 90) -> int:
        """Delete evaluations older than retention period.

        Args:
            retention_days: Days to retain

        Returns:
            Number of deleted records
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                DELETE FROM {self.table_name}
                WHERE created_at < $cutoff
                RETURN BEFORE
                """,
                {"cutoff": cutoff},
            )
            return len(results)


# Repository cache
_repos: dict[str, EvaluationRepository] = {}


def get_evaluation_repository(project_name: str) -> EvaluationRepository:
    """Get or create cached repository.

    Args:
        project_name: Project name

    Returns:
        EvaluationRepository instance
    """
    if project_name not in _repos:
        _repos[project_name] = EvaluationRepository(project_name)
    return _repos[project_name]
