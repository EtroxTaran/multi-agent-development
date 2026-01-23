"""Checkpoint storage adapter.

Provides unified interface for checkpoint management using SurrealDB.
This is the DB-only version - no file fallback.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .async_utils import run_async
from .base import CheckpointData, CheckpointStorageProtocol

logger = logging.getLogger(__name__)


class CheckpointStorageAdapter(CheckpointStorageProtocol):
    """Storage adapter for checkpoint management.

    Uses SurrealDB as the only storage backend. No file fallback.

    Usage:
        adapter = CheckpointStorageAdapter(project_dir)

        # Create a checkpoint
        checkpoint = adapter.create_checkpoint("before-refactor", notes="Pre-refactor state")

        # List checkpoints
        checkpoints = adapter.list_checkpoints()

        # Rollback to checkpoint
        adapter.rollback_to_checkpoint(checkpoint_id, confirm=True)
    """

    def __init__(
        self,
        project_dir: Path,
        project_name: Optional[str] = None,
    ):
        """Initialize checkpoint storage adapter.

        Args:
            project_dir: Project directory
            project_name: Project name (defaults to directory name)
        """
        self.project_dir = Path(project_dir)
        self.project_name = project_name or self.project_dir.name
        self._db_backend: Optional[Any] = None
        self._workflow_backend: Optional[Any] = None

    def _get_db_backend(self) -> Any:
        """Get or create database backend."""
        if self._db_backend is None:
            from orchestrator.db.repositories.checkpoints import get_checkpoint_repository

            self._db_backend = get_checkpoint_repository(self.project_name)
        return self._db_backend

    def _get_workflow_backend(self) -> Any:
        """Get workflow repository for state access."""
        if self._workflow_backend is None:
            from orchestrator.db.repositories.workflow import get_workflow_repository

            self._workflow_backend = get_workflow_repository(self.project_name)
        return self._workflow_backend

    def _get_current_state(self) -> dict:
        """Get current workflow state for checkpointing."""
        workflow = self._get_workflow_backend()
        state = run_async(workflow.get_state())
        if state:
            return {
                "project_dir": state.project_dir,
                "current_phase": state.current_phase,
                "phase_status": state.phase_status,
                "iteration_count": state.iteration_count,
                "plan": state.plan,
                "validation_feedback": state.validation_feedback,
                "verification_feedback": state.verification_feedback,
                "implementation_result": state.implementation_result,
                "next_decision": state.next_decision,
                "execution_mode": state.execution_mode,
                "discussion_complete": state.discussion_complete,
                "research_complete": state.research_complete,
                "research_findings": state.research_findings,
                "token_usage": state.token_usage,
            }
        return {}

    def _get_task_progress(self, state: dict) -> dict:
        """Extract task progress from state."""
        from orchestrator.db.repositories.tasks import get_task_repository

        task_repo = get_task_repository(self.project_name)
        progress = run_async(task_repo.get_progress())

        return {
            "total_tasks": progress.get("total", 0),
            "completed_tasks": progress.get("completed", 0),
            "pending_tasks": progress.get("pending", 0),
            "in_progress_tasks": progress.get("in_progress", 0),
            "completion_rate": progress.get("completion_rate", 0.0),
        }

    def create_checkpoint(
        self,
        name: str,
        notes: str = "",
        include_files: bool = False,
    ) -> CheckpointData:
        """Create a new checkpoint.

        Args:
            name: Human-readable checkpoint name
            notes: Optional notes about this checkpoint
            include_files: Whether to record file list (not supported in DB-only mode)

        Returns:
            Created CheckpointData
        """
        # Get current state
        state = self._get_current_state()
        task_progress = self._get_task_progress(state)
        phase = state.get("current_phase", 0)

        db = self._get_db_backend()
        checkpoint = run_async(
            db.create_checkpoint(
                name=name,
                state_snapshot=state,
                phase=phase,
                notes=notes,
                task_progress=task_progress,
                files_snapshot=[],  # Not tracking files in DB-only mode
            )
        )
        return self._db_checkpoint_to_data(checkpoint)

    def list_checkpoints(self) -> list[CheckpointData]:
        """List all checkpoints for this project.

        Returns:
            List of CheckpointData objects, sorted by creation time
        """
        db = self._get_db_backend()
        checkpoints = run_async(db.list_checkpoints())
        return [self._db_checkpoint_to_data(c) for c in checkpoints]

    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Get checkpoint by ID.

        Args:
            checkpoint_id: Full or partial checkpoint ID

        Returns:
            CheckpointData if found
        """
        db = self._get_db_backend()
        checkpoint = run_async(db.get_checkpoint(checkpoint_id))
        if checkpoint:
            return self._db_checkpoint_to_data(checkpoint)
        return None

    def rollback_to_checkpoint(self, checkpoint_id: str, confirm: bool = False) -> bool:
        """Rollback workflow state to a checkpoint.

        WARNING: This overwrites current state with checkpoint state.

        Args:
            checkpoint_id: Checkpoint ID to rollback to
            confirm: Must be True to actually perform rollback

        Returns:
            True if rollback successful
        """
        if not confirm:
            logger.warning("Rollback requires confirm=True")
            return False

        # Get checkpoint
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint not found: {checkpoint_id}")
            return False

        if not checkpoint.state_snapshot:
            logger.error(f"Checkpoint has no state snapshot: {checkpoint_id}")
            return False

        # Restore state via workflow repository
        workflow = self._get_workflow_backend()
        state_snapshot = checkpoint.state_snapshot

        # Update the workflow state with checkpoint data
        run_async(
            workflow.update_state(
                current_phase=state_snapshot.get("current_phase", 1),
                phase_status=state_snapshot.get("phase_status", {}),
                iteration_count=state_snapshot.get("iteration_count", 0),
                plan=state_snapshot.get("plan"),
                validation_feedback=state_snapshot.get("validation_feedback"),
                verification_feedback=state_snapshot.get("verification_feedback"),
                implementation_result=state_snapshot.get("implementation_result"),
                next_decision=state_snapshot.get("next_decision"),
                execution_mode=state_snapshot.get("execution_mode", "afk"),
                discussion_complete=state_snapshot.get("discussion_complete", False),
                research_complete=state_snapshot.get("research_complete", False),
                research_findings=state_snapshot.get("research_findings"),
                token_usage=state_snapshot.get("token_usage"),
            )
        )

        logger.info(f"Rolled back to checkpoint: {checkpoint.name}")
        return True

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to delete

        Returns:
            True if deleted successfully
        """
        db = self._get_db_backend()
        result = run_async(db.delete_checkpoint(checkpoint_id))
        return bool(result)

    def prune_old_checkpoints(self, keep_count: int = 10) -> int:
        """Remove old checkpoints, keeping the most recent ones.

        Args:
            keep_count: Number of checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        db = self._get_db_backend()
        return run_async(db.prune_old_checkpoints(keep_count))

    def get_latest(self) -> Optional[CheckpointData]:
        """Get the most recent checkpoint.

        Returns:
            Latest CheckpointData or None
        """
        db = self._get_db_backend()
        checkpoint = run_async(db.get_latest())
        if checkpoint:
            return self._db_checkpoint_to_data(checkpoint)
        return None

    @staticmethod
    def _db_checkpoint_to_data(checkpoint: Any) -> CheckpointData:
        """Convert database checkpoint to data class."""
        return CheckpointData(
            id=checkpoint.id,
            name=checkpoint.name,
            notes=checkpoint.notes,
            phase=checkpoint.phase,
            task_progress=checkpoint.task_progress,
            state_snapshot=checkpoint.state_snapshot,
            files_snapshot=checkpoint.files_snapshot,
            created_at=checkpoint.created_at,
        )


# Cache of adapters per project
_checkpoint_adapters: dict[str, CheckpointStorageAdapter] = {}


def get_checkpoint_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> CheckpointStorageAdapter:
    """Get or create checkpoint storage adapter for a project.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        CheckpointStorageAdapter instance
    """
    key = str(Path(project_dir).resolve())

    if key not in _checkpoint_adapters:
        _checkpoint_adapters[key] = CheckpointStorageAdapter(project_dir, project_name)
    return _checkpoint_adapters[key]
