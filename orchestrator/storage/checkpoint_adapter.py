"""Checkpoint storage adapter.

Provides unified interface for checkpoint management using SurrealDB.
This is the DB-only version - no file fallback.

Supports both full and incremental checkpointing:
- Full checkpoints: Store complete state snapshot (default)
- Incremental checkpoints: Store only changed fields since last checkpoint
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .async_utils import run_async
from .base import CheckpointData, CheckpointStorageProtocol

logger = logging.getLogger(__name__)


# Fields that are safe to skip in incremental checkpoints (large or regenerable)
INCREMENTAL_SKIP_FIELDS = {
    "execution_history",  # Can be large, regenerated from audit trail
    "fix_history",  # Can be large, kept in separate history
    "errors",  # Append-only, kept separately
}

# Fields that should always be included in incremental checkpoints
INCREMENTAL_REQUIRED_FIELDS = {
    "current_phase",
    "phase_status",
    "current_task_id",
    "next_decision",
}


@dataclass
class StateDelta:
    """Represents the difference between two workflow states.

    Used for incremental checkpointing to only store changed fields.
    """

    changed_fields: dict[str, Any] = field(default_factory=dict)
    deleted_fields: list[str] = field(default_factory=list)
    base_checkpoint_id: Optional[str] = None
    field_hashes: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check if there are no changes."""
        return not self.changed_fields and not self.deleted_fields

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "changed_fields": self.changed_fields,
            "deleted_fields": self.deleted_fields,
            "base_checkpoint_id": self.base_checkpoint_id,
            "field_hashes": self.field_hashes,
            "is_incremental": True,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StateDelta":
        """Create from dictionary."""
        return cls(
            changed_fields=data.get("changed_fields", {}),
            deleted_fields=data.get("deleted_fields", []),
            base_checkpoint_id=data.get("base_checkpoint_id"),
            field_hashes=data.get("field_hashes", {}),
        )


def _compute_field_hash(value: Any) -> str:
    """Compute a hash for a field value to detect changes.

    Args:
        value: The field value to hash

    Returns:
        MD5 hash of the JSON-serialized value
    """
    try:
        # Sort keys for consistent hashing
        serialized = json.dumps(value, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode()).hexdigest()[:12]
    except (TypeError, ValueError):
        # For non-serializable values, use repr
        return hashlib.md5(repr(value).encode()).hexdigest()[:12]


def compute_state_delta(
    current_state: dict,
    previous_state: dict,
    previous_hashes: Optional[dict[str, str]] = None,
) -> StateDelta:
    """Compute the difference between two workflow states.

    Args:
        current_state: Current workflow state
        previous_state: Previous workflow state (from last checkpoint)
        previous_hashes: Optional pre-computed hashes from previous checkpoint

    Returns:
        StateDelta containing only changed fields
    """
    delta = StateDelta()

    # Compute hashes for current state
    current_hashes: dict[str, str] = {}
    for key, value in current_state.items():
        if key not in INCREMENTAL_SKIP_FIELDS:
            current_hashes[key] = _compute_field_hash(value)

    delta.field_hashes = current_hashes

    # If we have previous hashes, use them for comparison
    if previous_hashes:
        for key, current_hash in current_hashes.items():
            prev_hash = previous_hashes.get(key)
            if prev_hash != current_hash or key in INCREMENTAL_REQUIRED_FIELDS:
                delta.changed_fields[key] = current_state[key]

        # Check for deleted fields
        for key in previous_hashes:
            if key not in current_hashes:
                delta.deleted_fields.append(key)
    else:
        # No previous hashes - compare values directly
        for key, value in current_state.items():
            if key in INCREMENTAL_SKIP_FIELDS:
                continue

            prev_value = previous_state.get(key)

            # Include if changed or required
            if key in INCREMENTAL_REQUIRED_FIELDS:
                delta.changed_fields[key] = value
            elif prev_value is None and value is not None:
                delta.changed_fields[key] = value
            elif prev_value != value:
                delta.changed_fields[key] = value

        # Check for deleted fields
        for key in previous_state:
            if key not in current_state and key not in INCREMENTAL_SKIP_FIELDS:
                delta.deleted_fields.append(key)

    return delta


def reconstruct_state_from_deltas(
    base_state: dict,
    deltas: list[StateDelta],
) -> dict:
    """Reconstruct a full state from a base state and a chain of deltas.

    Args:
        base_state: The full base checkpoint state
        deltas: List of deltas to apply in order

    Returns:
        Reconstructed full state
    """
    state = dict(base_state)

    for delta in deltas:
        # Apply changes
        state.update(delta.changed_fields)

        # Remove deleted fields
        for field_name in delta.deleted_fields:
            state.pop(field_name, None)

    return state


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

    def create_incremental_checkpoint(
        self,
        name: str,
        notes: str = "",
    ) -> CheckpointData:
        """Create an incremental checkpoint storing only changed fields.

        This is more efficient than full checkpoints for frequent saves,
        as it only stores fields that have changed since the last checkpoint.

        Args:
            name: Human-readable checkpoint name
            notes: Optional notes about this checkpoint

        Returns:
            Created CheckpointData (with incremental delta in state_snapshot)
        """
        # Get current state
        current_state = self._get_current_state()
        task_progress = self._get_task_progress(current_state)
        phase = current_state.get("current_phase", 0)

        # Get the latest checkpoint for comparison
        latest = self.get_latest()
        base_checkpoint_id = None
        previous_state = {}
        previous_hashes = None

        if latest and latest.state_snapshot:
            # Check if latest is also incremental
            if latest.state_snapshot.get("is_incremental"):
                # Need to reconstruct full state from base
                # For simplicity, use the latest as base even if incremental
                # In production, you'd chain deltas or use periodic full checkpoints
                previous_state = latest.state_snapshot.get("changed_fields", {})
                previous_hashes = latest.state_snapshot.get("field_hashes")
            else:
                previous_state = latest.state_snapshot
                previous_hashes = None  # Will be computed

            base_checkpoint_id = latest.id

        # Compute delta
        delta = compute_state_delta(current_state, previous_state, previous_hashes)
        delta.base_checkpoint_id = base_checkpoint_id

        # If no changes, still create checkpoint with required fields
        if delta.is_empty():
            logger.info(f"No changes detected, creating minimal checkpoint: {name}")

        db = self._get_db_backend()
        checkpoint = run_async(
            db.create_checkpoint(
                name=name,
                state_snapshot=delta.to_dict(),
                phase=phase,
                notes=f"[incremental] {notes}",
                task_progress=task_progress,
                files_snapshot=[],
            )
        )
        return self._db_checkpoint_to_data(checkpoint)

    def reconstruct_full_state(self, checkpoint_id: str) -> Optional[dict]:
        """Reconstruct full state from a checkpoint.

        For full checkpoints, returns the state directly.
        For incremental checkpoints, reconstructs from base + deltas.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Full reconstructed state, or None if checkpoint not found
        """
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint or not checkpoint.state_snapshot:
            return None

        state_snapshot = checkpoint.state_snapshot

        # Check if this is an incremental checkpoint
        if not state_snapshot.get("is_incremental"):
            return state_snapshot

        # Reconstruct from delta chain
        delta = StateDelta.from_dict(state_snapshot)
        base_checkpoint_id = delta.base_checkpoint_id

        if not base_checkpoint_id:
            # No base, return changed fields as state
            return delta.changed_fields

        # Get base state (recursively reconstruct if needed)
        base_state = self.reconstruct_full_state(base_checkpoint_id)
        if not base_state:
            logger.warning(f"Base checkpoint {base_checkpoint_id} not found")
            return delta.changed_fields

        # Apply delta to base
        return reconstruct_state_from_deltas(base_state, [delta])

    def should_create_full_checkpoint(self, max_delta_chain: int = 10) -> bool:
        """Check if a full checkpoint should be created instead of incremental.

        Creates full checkpoints periodically to prevent long delta chains.

        Args:
            max_delta_chain: Maximum incremental checkpoints before full

        Returns:
            True if full checkpoint is recommended
        """
        checkpoints = self.list_checkpoints()

        # Count consecutive incremental checkpoints
        consecutive_incremental = 0
        for checkpoint in reversed(checkpoints):
            if checkpoint.state_snapshot and checkpoint.state_snapshot.get("is_incremental"):
                consecutive_incremental += 1
            else:
                break

        return consecutive_incremental >= max_delta_chain

    def create_smart_checkpoint(
        self,
        name: str,
        notes: str = "",
        max_delta_chain: int = 10,
    ) -> CheckpointData:
        """Create a checkpoint, automatically choosing full or incremental.

        Creates incremental checkpoints for efficiency, but periodically
        creates full checkpoints to prevent long delta chains.

        Args:
            name: Human-readable checkpoint name
            notes: Optional notes
            max_delta_chain: Max incremental checkpoints before full

        Returns:
            Created CheckpointData
        """
        if self.should_create_full_checkpoint(max_delta_chain):
            logger.info(f"Creating full checkpoint (delta chain limit reached): {name}")
            return self.create_checkpoint(name, notes)
        else:
            return self.create_incremental_checkpoint(name, notes)

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
