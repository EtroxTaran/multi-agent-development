"""Repository for prompt versions.

Provides CRUD operations for versioned prompts with performance tracking.
"""

import logging
from datetime import datetime
from typing import Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


class PromptStatus:
    """Prompt version status constants."""

    DRAFT = "draft"
    SHADOW = "shadow"  # Testing in shadow mode
    CANARY = "canary"  # Testing with small traffic percentage
    PRODUCTION = "production"  # Active in production
    RETIRED = "retired"  # No longer used


class OptimizationMethod:
    """Optimization method constants."""

    MANUAL = "manual"
    OPRO = "opro"  # OPRO-style optimization
    BOOTSTRAP = "bootstrap"  # Few-shot bootstrapping
    INSTRUCTION = "instruction"  # Instruction refinement


class PromptVersionRepository(BaseRepository[dict]):
    """Repository for prompt_versions table."""

    table_name = "prompt_versions"

    async def save_version(
        self,
        agent: str,
        template_name: str,
        content: str,
        version: int,
        parent_version: Optional[str] = None,
        optimization_method: str = OptimizationMethod.MANUAL,
        status: str = PromptStatus.DRAFT,
        metrics: Optional[dict] = None,
    ) -> dict:
        """Save a new prompt version.

        Args:
            agent: Agent name
            template_name: Template identifier
            content: Prompt content
            version: Version number
            parent_version: Parent version ID if optimized
            optimization_method: How this version was created
            status: Initial status
            metrics: Initial metrics

        Returns:
            Saved record
        """
        version_id = f"pv-{agent}-{template_name}-v{version}"

        data = {
            "version_id": version_id,
            "agent": agent,
            "template_name": template_name,
            "content": content,
            "version": version,
            "parent_version": parent_version,
            "optimization_method": optimization_method,
            "status": status,
            "metrics": metrics or {},
        }

        return await self.create(data, version_id)

    async def get_by_template(
        self,
        agent: str,
        template_name: str,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Get all versions for a template.

        Args:
            agent: Agent name
            template_name: Template identifier
            status: Filter by status

        Returns:
            List of versions ordered by version number
        """
        status_filter = "AND status = $status" if status else ""
        params = {"agent": agent, "template_name": template_name}
        if status:
            params["status"] = status

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent AND template_name = $template_name {status_filter}
                ORDER BY version DESC
                """,
                params,
            )
            return results

    async def get_production_version(
        self,
        agent: str,
        template_name: str,
    ) -> Optional[dict]:
        """Get the current production version for a template.

        Args:
            agent: Agent name
            template_name: Template identifier

        Returns:
            Production version or None
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent
                  AND template_name = $template_name
                  AND status = $status
                ORDER BY version DESC
                LIMIT 1
                """,
                {
                    "agent": agent,
                    "template_name": template_name,
                    "status": PromptStatus.PRODUCTION,
                },
            )
            return results[0] if results else None

    async def get_latest_version(
        self,
        agent: str,
        template_name: str,
    ) -> Optional[dict]:
        """Get the latest version for a template regardless of status.

        Args:
            agent: Agent name
            template_name: Template identifier

        Returns:
            Latest version or None
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent AND template_name = $template_name
                ORDER BY version DESC
                LIMIT 1
                """,
                {"agent": agent, "template_name": template_name},
            )
            return results[0] if results else None

    async def get_next_version_number(
        self,
        agent: str,
        template_name: str,
    ) -> int:
        """Get the next version number for a template.

        Args:
            agent: Agent name
            template_name: Template identifier

        Returns:
            Next version number
        """
        latest = await self.get_latest_version(agent, template_name)
        if latest:
            return latest.get("version", 0) + 1
        return 1

    async def update_status(
        self,
        version_id: str,
        status: str,
    ) -> Optional[dict]:
        """Update the status of a version.

        Args:
            version_id: Version identifier
            status: New status

        Returns:
            Updated record or None
        """
        return await self.update(version_id, {"status": status})

    async def update_metrics(
        self,
        version_id: str,
        metrics: dict,
    ) -> Optional[dict]:
        """Update the metrics for a version.

        Args:
            version_id: Version identifier
            metrics: New metrics (merged with existing)

        Returns:
            Updated record or None
        """
        # Get current metrics
        record = await self.find_by_id(version_id)
        if not record:
            return None

        current_metrics = record.get("metrics", {})
        merged_metrics = {**current_metrics, **metrics}

        return await self.update(version_id, {"metrics": merged_metrics})

    async def promote_to_production(
        self,
        version_id: str,
    ) -> Optional[dict]:
        """Promote a version to production.

        Retires the current production version first.

        Args:
            version_id: Version to promote

        Returns:
            Promoted record or None
        """
        # Get the version being promoted
        version = await self.find_by_id(version_id)
        if not version:
            return None

        # Retire current production version for this template
        agent = version["agent"]
        template_name = version["template_name"]

        current_prod = await self.get_production_version(agent, template_name)
        if current_prod:
            prod_id = current_prod.get("version_id", "").replace("pv-", "")
            await self.update(prod_id, {"status": PromptStatus.RETIRED})

        # Promote the new version
        return await self.update(version_id, {"status": PromptStatus.PRODUCTION})

    async def get_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[dict]:
        """Get all versions with a specific status.

        Args:
            status: Status to filter by
            limit: Maximum results

        Returns:
            List of versions
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE status = $status
                ORDER BY updated_at DESC
                LIMIT $limit
                """,
                {"status": status, "limit": limit},
            )
            return results

    async def get_lineage(self, version_id: str) -> list[dict]:
        """Get the lineage of a version (all ancestors).

        Args:
            version_id: Starting version

        Returns:
            List of versions in lineage order (oldest first)
        """
        lineage = []
        current_id = version_id

        while current_id:
            record = await self.find_by_id(current_id)
            if not record:
                break
            lineage.append(record)
            current_id = record.get("parent_version")

        lineage.reverse()  # Oldest first
        return lineage


class GoldenExampleRepository(BaseRepository[dict]):
    """Repository for golden_examples table."""

    table_name = "golden_examples"

    async def save_example(
        self,
        agent: str,
        template_name: str,
        input_prompt: str,
        output: str,
        score: float,
        evaluation_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Save a golden example.

        Args:
            agent: Agent name
            template_name: Template identifier
            input_prompt: The input prompt
            output: The high-quality output
            score: Evaluation score
            evaluation_id: Source evaluation ID
            metadata: Additional metadata

        Returns:
            Saved record
        """
        example_id = f"ge-{agent}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        data = {
            "example_id": example_id,
            "agent": agent,
            "template_name": template_name,
            "input_prompt": input_prompt,
            "output": output,
            "score": score,
            "evaluation_id": evaluation_id,
            "metadata": metadata or {},
        }

        return await self.create(data, example_id)

    async def get_by_template(
        self,
        agent: str,
        template_name: str,
        limit: int = 10,
        min_score: float = 9.0,
    ) -> list[dict]:
        """Get golden examples for a template.

        Args:
            agent: Agent name
            template_name: Template identifier
            limit: Maximum results
            min_score: Minimum score

        Returns:
            List of examples ordered by score
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent
                  AND template_name = $template_name
                  AND score >= $min_score
                ORDER BY score DESC
                LIMIT $limit
                """,
                {
                    "agent": agent,
                    "template_name": template_name,
                    "min_score": min_score,
                    "limit": limit,
                },
            )
            return results

    async def get_top_examples(
        self,
        agent: str,
        k: int = 5,
    ) -> list[dict]:
        """Get top K examples for an agent across all templates.

        Args:
            agent: Agent name
            k: Number of examples

        Returns:
            List of top examples
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent
                ORDER BY score DESC
                LIMIT $k
                """,
                {"agent": agent, "k": k},
            )
            return results

    async def count_by_template(
        self,
        agent: str,
        template_name: str,
    ) -> int:
        """Count examples for a template.

        Args:
            agent: Agent name
            template_name: Template identifier

        Returns:
            Count
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT count() as total FROM {self.table_name}
                WHERE agent = $agent AND template_name = $template_name
                GROUP ALL
                """,
                {"agent": agent, "template_name": template_name},
            )
            return results[0].get("total", 0) if results else 0


class OptimizationHistoryRepository(BaseRepository[dict]):
    """Repository for optimization_history table."""

    table_name = "optimization_history"

    async def record_attempt(
        self,
        agent: str,
        template_name: str,
        method: str,
        source_version: Optional[str] = None,
        target_version: Optional[str] = None,
        success: bool = False,
        source_score: Optional[float] = None,
        target_score: Optional[float] = None,
        samples_used: int = 0,
        validation_results: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> dict:
        """Record an optimization attempt.

        Args:
            agent: Agent name
            template_name: Template identifier
            method: Optimization method
            source_version: Source prompt version
            target_version: Target prompt version
            success: Whether optimization succeeded
            source_score: Score before optimization
            target_score: Score after optimization
            samples_used: Number of samples used
            validation_results: Validation test results
            error: Error message if failed

        Returns:
            Saved record
        """
        optimization_id = f"opt-{agent}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        improvement = None
        if source_score is not None and target_score is not None:
            improvement = target_score - source_score

        data = {
            "optimization_id": optimization_id,
            "agent": agent,
            "template_name": template_name,
            "method": method,
            "source_version": source_version,
            "target_version": target_version,
            "success": success,
            "source_score": source_score,
            "target_score": target_score,
            "improvement": improvement,
            "samples_used": samples_used,
            "validation_results": validation_results or {},
            "error": error,
        }

        return await self.create(data, optimization_id)

    async def get_by_template(
        self,
        agent: str,
        template_name: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get optimization history for a template.

        Args:
            agent: Agent name
            template_name: Template identifier
            limit: Maximum results

        Returns:
            List of optimization attempts
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE agent = $agent AND template_name = $template_name
                ORDER BY created_at DESC
                LIMIT $limit
                """,
                {"agent": agent, "template_name": template_name, "limit": limit},
            )
            return results

    async def get_successful(
        self,
        agent: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get successful optimizations.

        Args:
            agent: Filter by agent
            limit: Maximum results

        Returns:
            List of successful optimizations
        """
        agent_filter = "AND agent = $agent" if agent else ""
        params = {"limit": limit}
        if agent:
            params["agent"] = agent

        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                f"""
                SELECT * FROM {self.table_name}
                WHERE success = true {agent_filter}
                ORDER BY improvement DESC
                LIMIT $limit
                """,
                params,
            )
            return results

    async def get_statistics(self) -> dict:
        """Get optimization statistics.

        Returns:
            Statistics dictionary
        """
        async with get_connection(self.project_name) as conn:
            # Overall stats
            overall = await conn.query(
                f"""
                SELECT
                    count() as total,
                    count(success = true) as successful,
                    math::mean(improvement) as avg_improvement
                FROM {self.table_name}
                GROUP ALL
                """,
            )

            # By method
            by_method = await conn.query(
                f"""
                SELECT
                    method,
                    count() as total,
                    count(success = true) as successful
                FROM {self.table_name}
                GROUP BY method
                """,
            )

            return {
                "overall": overall[0] if overall else {},
                "by_method": by_method,
            }


# Repository caches
_prompt_repos: dict[str, PromptVersionRepository] = {}
_golden_repos: dict[str, GoldenExampleRepository] = {}
_opt_repos: dict[str, OptimizationHistoryRepository] = {}


def get_prompt_version_repository(project_name: str) -> PromptVersionRepository:
    """Get or create cached prompt version repository.

    Args:
        project_name: Project name

    Returns:
        PromptVersionRepository instance
    """
    if project_name not in _prompt_repos:
        _prompt_repos[project_name] = PromptVersionRepository(project_name)
    return _prompt_repos[project_name]


def get_golden_example_repository(project_name: str) -> GoldenExampleRepository:
    """Get or create cached golden example repository.

    Args:
        project_name: Project name

    Returns:
        GoldenExampleRepository instance
    """
    if project_name not in _golden_repos:
        _golden_repos[project_name] = GoldenExampleRepository(project_name)
    return _golden_repos[project_name]


def get_optimization_history_repository(project_name: str) -> OptimizationHistoryRepository:
    """Get or create cached optimization history repository.

    Args:
        project_name: Project name

    Returns:
        OptimizationHistoryRepository instance
    """
    if project_name not in _opt_repos:
        _opt_repos[project_name] = OptimizationHistoryRepository(project_name)
    return _opt_repos[project_name]
