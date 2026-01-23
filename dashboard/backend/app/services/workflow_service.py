"""Workflow management service.

Wraps Orchestrator with additional functionality for the dashboard.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings
from ..websocket import get_connection_manager

logger = logging.getLogger(__name__)

# Add orchestrator to path
import sys

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))

from orchestrator.orchestrator import Orchestrator


class WorkflowService:
    """Service for workflow management operations.

    Provides a high-level interface over Orchestrator with
    real-time event broadcasting.
    """

    def __init__(self, project_dir: Path):
        """Initialize workflow service.

        Args:
            project_dir: Project directory
        """
        self.project_dir = project_dir
        self.project_name = project_dir.name
        self._orchestrator: Optional[Orchestrator] = None

    @property
    def orchestrator(self) -> Orchestrator:
        """Get or create orchestrator."""
        if self._orchestrator is None:
            self._orchestrator = Orchestrator(
                self.project_dir,
                console_output=False,
            )
        return self._orchestrator

    async def get_status(self) -> dict[str, Any]:
        """Get workflow status.

        Returns:
            Status dictionary
        """
        try:
            return await self.orchestrator.status_langgraph()
        except Exception as e:
            logger.warning(f"LangGraph status failed, using basic: {e}")
            return self.orchestrator.status()

    def get_health(self) -> dict[str, Any]:
        """Get workflow health status.

        Returns:
            Health dictionary
        """
        return self.orchestrator.health_check()

    def check_prerequisites(self) -> tuple[bool, list[str]]:
        """Check workflow prerequisites.

        Returns:
            Tuple of (success, list of errors)
        """
        return self.orchestrator.check_prerequisites()

    async def start(
        self,
        start_phase: int = 1,
        end_phase: int = 5,
        skip_validation: bool = False,
        autonomous: bool = False,
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> dict[str, Any]:
        """Start the workflow.

        Args:
            start_phase: Phase to start from
            end_phase: Phase to end at
            skip_validation: Skip validation phase
            autonomous: Run autonomously
            on_progress: Optional progress callback

        Returns:
            Result dictionary
        """
        manager = get_connection_manager()

        # Broadcast start event
        await manager.broadcast_to_project(
            self.project_name,
            "workflow_start",
            {
                "start_phase": start_phase,
                "end_phase": end_phase,
                "autonomous": autonomous,
            },
        )

        try:
            result = await self.orchestrator.run_langgraph(
                start_phase=start_phase,
                end_phase=end_phase,
                skip_validation=skip_validation,
                autonomous=autonomous,
                use_rich_display=False,
            )

            # Broadcast completion
            await manager.broadcast_to_project(
                self.project_name,
                "workflow_complete",
                {
                    "success": result.get("success", False),
                    "results": result,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            await manager.broadcast_to_project(
                self.project_name,
                "workflow_error",
                {"error": str(e)},
            )
            raise

    async def resume(
        self,
        human_response: Optional[dict] = None,
        autonomous: bool = False,
    ) -> dict[str, Any]:
        """Resume the workflow.

        Args:
            human_response: Optional response for escalation
            autonomous: Run autonomously

        Returns:
            Result dictionary
        """
        manager = get_connection_manager()

        # Broadcast resume event
        await manager.broadcast_to_project(
            self.project_name,
            "workflow_resume",
            {"autonomous": autonomous},
        )

        try:
            result = await self.orchestrator.resume_langgraph(
                human_response=human_response,
                autonomous=autonomous,
                use_rich_display=False,
            )

            # Broadcast completion
            await manager.broadcast_to_project(
                self.project_name,
                "workflow_complete",
                {
                    "success": result.get("success", False),
                    "results": result,
                },
            )

            return result

        except Exception as e:
            logger.error(f"Workflow resume failed: {e}")
            await manager.broadcast_to_project(
                self.project_name,
                "workflow_error",
                {"error": str(e)},
            )
            raise

    def rollback(self, phase: int) -> dict[str, Any]:
        """Rollback to a previous phase.

        Args:
            phase: Phase number to rollback to

        Returns:
            Result dictionary
        """
        return self.orchestrator.rollback_to_phase(phase)

    def reset(self) -> None:
        """Reset workflow state."""
        self.orchestrator.reset()

    async def get_pending_escalation(self) -> Optional[dict]:
        """Get pending escalation if any.

        Returns:
            Escalation info or None
        """
        from orchestrator.langgraph import WorkflowRunner

        async with WorkflowRunner(self.project_dir) as runner:
            return await runner.get_pending_interrupt_async()
