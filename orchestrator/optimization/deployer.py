"""Deployment controller for safe prompt rollout.

Manages the lifecycle of prompt versions through:
draft → shadow → canary → production → retired

Provides automatic rollback on regression.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeploymentResult:
    """Result from a deployment operation.

    Attributes:
        success: Whether deployment succeeded
        version_id: The version being deployed
        from_status: Original status
        to_status: New status
        metrics: Metrics that informed the decision
        error: Error message if failed
        rollback_performed: Whether a rollback was triggered
    """

    success: bool
    version_id: str
    from_status: str
    to_status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    rollback_performed: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "version_id": self.version_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "metrics": self.metrics,
            "error": self.error,
            "rollback_performed": self.rollback_performed,
        }


@dataclass
class DeploymentConfig:
    """Configuration for deployment controller."""

    # Number of shadow test evaluations before promotion
    shadow_test_count: int = 10

    # Percentage of traffic for canary
    canary_percentage: float = 0.1

    # Number of canary evaluations before promotion
    canary_test_count: int = 10

    # Score threshold to maintain (not drop below baseline)
    rollback_threshold: float = -0.5

    # Minimum score for any stage
    minimum_score: float = 5.0

    # Auto-promote on success
    auto_promote: bool = True


class DeploymentController:
    """Controls safe deployment of optimized prompts.

    Lifecycle: draft → shadow → canary → production

    - **draft**: Initial state after optimization
    - **shadow**: Testing alongside production (not affecting output)
    - **canary**: Small percentage of real traffic
    - **production**: Fully deployed

    Automatic rollback occurs if:
    - Score drops significantly below baseline
    - Score falls below minimum threshold
    """

    def __init__(
        self,
        project_name: str,
        config: Optional[DeploymentConfig] = None,
    ):
        """Initialize the deployment controller.

        Args:
            project_name: Project name for DB access
            config: Deployment configuration
        """
        self.project_name = project_name
        self.config = config or DeploymentConfig()

        # Lazy-loaded repositories
        self._prompt_repo = None
        self._eval_repo = None
        self._history_repo = None

    @property
    def prompt_repo(self):
        if self._prompt_repo is None:
            from ..db.repositories import get_prompt_version_repository
            self._prompt_repo = get_prompt_version_repository(self.project_name)
        return self._prompt_repo

    @property
    def eval_repo(self):
        if self._eval_repo is None:
            from ..db.repositories import get_evaluation_repository
            self._eval_repo = get_evaluation_repository(self.project_name)
        return self._eval_repo

    @property
    def history_repo(self):
        if self._history_repo is None:
            from ..db.repositories import get_optimization_history_repository
            self._history_repo = get_optimization_history_repository(self.project_name)
        return self._history_repo

    async def start_shadow_testing(
        self,
        version_id: str,
    ) -> DeploymentResult:
        """Start shadow testing for a draft version.

        Args:
            version_id: Version to test

        Returns:
            DeploymentResult
        """
        version = await self.prompt_repo.find_by_id(version_id)
        if not version:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="unknown",
                to_status="shadow",
                error=f"Version {version_id} not found",
            )

        current_status = version.get("status", "draft")
        if current_status != "draft":
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status=current_status,
                to_status="shadow",
                error=f"Can only shadow test draft versions, got {current_status}",
            )

        # Update status to shadow
        await self.prompt_repo.update_status(version_id, "shadow")

        logger.info(f"Started shadow testing for {version_id}")

        return DeploymentResult(
            success=True,
            version_id=version_id,
            from_status="draft",
            to_status="shadow",
        )

    async def evaluate_shadow_test(
        self,
        version_id: str,
    ) -> DeploymentResult:
        """Evaluate shadow test results and optionally promote to canary.

        Args:
            version_id: Version being tested

        Returns:
            DeploymentResult with promotion decision
        """
        version = await self.prompt_repo.find_by_id(version_id)
        if not version:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="unknown",
                to_status="unknown",
                error=f"Version {version_id} not found",
            )

        if version.get("status") != "shadow":
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status=version.get("status", "unknown"),
                to_status="canary",
                error="Version not in shadow status",
            )

        # Get shadow test evaluations
        agent = version.get("agent")
        prompt_hash = version.get("content", "")[:16]  # Use content prefix as hash

        evaluations = await self.eval_repo.get_by_prompt_hash(prompt_hash)

        if len(evaluations) < self.config.shadow_test_count:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="shadow",
                to_status="shadow",
                error=f"Insufficient shadow tests: {len(evaluations)}/{self.config.shadow_test_count}",
                metrics={"evaluations": len(evaluations)},
            )

        # Calculate metrics
        scores = [e.get("overall_score", 0) for e in evaluations]
        avg_score = sum(scores) / len(scores) if scores else 0

        # Get production baseline
        production = await self.prompt_repo.get_production_version(
            agent, version.get("template_name")
        )
        baseline_score = production.get("metrics", {}).get("avg_score", 7.0) if production else 7.0

        improvement = avg_score - baseline_score

        metrics = {
            "shadow_avg_score": avg_score,
            "baseline_score": baseline_score,
            "improvement": improvement,
            "shadow_count": len(evaluations),
        }

        # Check if ready for canary
        if avg_score < self.config.minimum_score:
            # Reject - too low score
            await self.prompt_repo.update_status(version_id, "draft")  # Back to draft
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="shadow",
                to_status="draft",
                error=f"Shadow score {avg_score:.2f} below minimum {self.config.minimum_score}",
                metrics=metrics,
            )

        if improvement < self.config.rollback_threshold:
            # Reject - regression
            await self.prompt_repo.update_status(version_id, "draft")
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="shadow",
                to_status="draft",
                error=f"Shadow regression: {improvement:.2f}",
                metrics=metrics,
            )

        # Promote to canary
        if self.config.auto_promote:
            await self.prompt_repo.update_status(version_id, "canary")
            await self.prompt_repo.update_metrics(version_id, {
                "shadow_score": avg_score,
                "shadow_count": len(evaluations),
            })

            logger.info(f"Promoted {version_id} to canary (shadow score: {avg_score:.2f})")

            return DeploymentResult(
                success=True,
                version_id=version_id,
                from_status="shadow",
                to_status="canary",
                metrics=metrics,
            )

        return DeploymentResult(
            success=True,
            version_id=version_id,
            from_status="shadow",
            to_status="shadow",  # Not promoted yet
            metrics=metrics,
        )

    async def evaluate_canary(
        self,
        version_id: str,
    ) -> DeploymentResult:
        """Evaluate canary results and optionally promote to production.

        Args:
            version_id: Version in canary

        Returns:
            DeploymentResult with promotion decision
        """
        version = await self.prompt_repo.find_by_id(version_id)
        if not version:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="unknown",
                to_status="unknown",
                error=f"Version {version_id} not found",
            )

        if version.get("status") != "canary":
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status=version.get("status", "unknown"),
                to_status="production",
                error="Version not in canary status",
            )

        # Get canary evaluations
        agent = version.get("agent")
        prompt_hash = version.get("content", "")[:16]

        evaluations = await self.eval_repo.get_by_prompt_hash(prompt_hash)
        # Filter to only canary-period evaluations
        canary_evals = evaluations[:self.config.canary_test_count]

        if len(canary_evals) < self.config.canary_test_count:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="canary",
                to_status="canary",
                error=f"Insufficient canary tests: {len(canary_evals)}/{self.config.canary_test_count}",
                metrics={"evaluations": len(canary_evals)},
            )

        # Calculate metrics
        scores = [e.get("overall_score", 0) for e in canary_evals]
        avg_score = sum(scores) / len(scores) if scores else 0

        # Get baseline from shadow metrics
        shadow_score = version.get("metrics", {}).get("shadow_score", 7.0)

        # Canary should not regress from shadow
        canary_change = avg_score - shadow_score

        metrics = {
            "canary_avg_score": avg_score,
            "shadow_score": shadow_score,
            "canary_change": canary_change,
            "canary_count": len(canary_evals),
        }

        # Check for regression
        if avg_score < self.config.minimum_score:
            # Rollback to draft
            await self.prompt_repo.update_status(version_id, "draft")
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="canary",
                to_status="draft",
                error=f"Canary score {avg_score:.2f} below minimum",
                metrics=metrics,
                rollback_performed=True,
            )

        if canary_change < self.config.rollback_threshold:
            # Rollback to draft
            await self.prompt_repo.update_status(version_id, "draft")
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="canary",
                to_status="draft",
                error=f"Canary regression: {canary_change:.2f}",
                metrics=metrics,
                rollback_performed=True,
            )

        # Promote to production
        if self.config.auto_promote:
            await self.prompt_repo.promote_to_production(version_id)
            await self.prompt_repo.update_metrics(version_id, {
                "canary_score": avg_score,
                "canary_count": len(canary_evals),
                "promoted_at": datetime.now().isoformat(),
            })

            logger.info(f"Promoted {version_id} to production (canary score: {avg_score:.2f})")

            return DeploymentResult(
                success=True,
                version_id=version_id,
                from_status="canary",
                to_status="production",
                metrics=metrics,
            )

        return DeploymentResult(
            success=True,
            version_id=version_id,
            from_status="canary",
            to_status="canary",  # Not promoted yet
            metrics=metrics,
        )

    async def rollback(
        self,
        version_id: str,
        reason: str,
    ) -> DeploymentResult:
        """Rollback a version to draft status.

        Args:
            version_id: Version to rollback
            reason: Reason for rollback

        Returns:
            DeploymentResult
        """
        version = await self.prompt_repo.find_by_id(version_id)
        if not version:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="unknown",
                to_status="draft",
                error=f"Version {version_id} not found",
            )

        current_status = version.get("status")

        if current_status == "production":
            # Can't rollback production directly - need to promote something else
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status=current_status,
                to_status=current_status,
                error="Cannot rollback production version - promote another version instead",
            )

        await self.prompt_repo.update_status(version_id, "draft")
        await self.prompt_repo.update_metrics(version_id, {
            "rollback_reason": reason,
            "rollback_at": datetime.now().isoformat(),
        })

        logger.warning(f"Rolled back {version_id} to draft: {reason}")

        return DeploymentResult(
            success=True,
            version_id=version_id,
            from_status=current_status,
            to_status="draft",
            rollback_performed=True,
        )

    async def get_deployment_status(
        self,
        agent: str,
        template_name: str,
    ) -> dict:
        """Get current deployment status for a template.

        Args:
            agent: Agent name
            template_name: Template name

        Returns:
            Status dictionary
        """
        versions = await self.prompt_repo.get_by_template(agent, template_name)

        status_counts = {
            "draft": 0,
            "shadow": 0,
            "canary": 0,
            "production": 0,
            "retired": 0,
        }

        production_version = None
        canary_version = None
        shadow_version = None

        for v in versions:
            s = v.get("status", "draft")
            status_counts[s] = status_counts.get(s, 0) + 1

            if s == "production":
                production_version = v
            elif s == "canary":
                canary_version = v
            elif s == "shadow":
                shadow_version = v

        return {
            "agent": agent,
            "template": template_name,
            "total_versions": len(versions),
            "status_counts": status_counts,
            "production": production_version.get("version_id") if production_version else None,
            "canary": canary_version.get("version_id") if canary_version else None,
            "shadow": shadow_version.get("version_id") if shadow_version else None,
            "production_metrics": production_version.get("metrics") if production_version else None,
        }

    async def force_promote(
        self,
        version_id: str,
    ) -> DeploymentResult:
        """Force promote a version to production (bypassing tests).

        Use with caution - skips all validation.

        Args:
            version_id: Version to promote

        Returns:
            DeploymentResult
        """
        version = await self.prompt_repo.find_by_id(version_id)
        if not version:
            return DeploymentResult(
                success=False,
                version_id=version_id,
                from_status="unknown",
                to_status="production",
                error=f"Version {version_id} not found",
            )

        current_status = version.get("status")

        await self.prompt_repo.promote_to_production(version_id)
        await self.prompt_repo.update_metrics(version_id, {
            "force_promoted": True,
            "force_promoted_at": datetime.now().isoformat(),
        })

        logger.warning(f"Force promoted {version_id} to production (was {current_status})")

        return DeploymentResult(
            success=True,
            version_id=version_id,
            from_status=current_status,
            to_status="production",
            metrics={"force_promoted": True},
        )
