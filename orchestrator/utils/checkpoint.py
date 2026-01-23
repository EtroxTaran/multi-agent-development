"""Manual checkpoint support for workflow state snapshots.

Allows creating named checkpoints with notes for strategic state capture
and rollback capabilities. Based on GSD strategic checkpoint pattern.
"""

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """A workflow checkpoint with metadata.

    Attributes:
        id: Unique checkpoint identifier (hash-based)
        name: Human-readable checkpoint name
        notes: User-provided notes about this checkpoint
        created_at: Timestamp when checkpoint was created
        phase: Current workflow phase at checkpoint time
        task_progress: Task completion status
        state_snapshot: Copy of workflow state
        files_snapshot: List of files at checkpoint time
    """

    id: str
    name: str
    notes: str
    created_at: datetime
    phase: int
    task_progress: dict  # {total, completed, in_progress}
    state_snapshot: dict
    files_snapshot: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "phase": self.phase,
            "task_progress": self.task_progress,
            "state_snapshot": self.state_snapshot,
            "files_snapshot": self.files_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            notes=data["notes"],
            created_at=datetime.fromisoformat(data["created_at"]),
            phase=data["phase"],
            task_progress=data["task_progress"],
            state_snapshot=data["state_snapshot"],
            files_snapshot=data.get("files_snapshot", []),
        )

    def summary(self) -> str:
        """Get brief summary for listing."""
        progress = self.task_progress
        return (
            f"[{self.id[:8]}] {self.name} - Phase {self.phase} "
            f"({progress.get('completed', 0)}/{progress.get('total', 0)} tasks) "
            f"- {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


class CheckpointManager:
    """Manages workflow checkpoints for a project.

    Provides checkpoint creation, listing, and rollback capabilities.
    Checkpoints are stored in .workflow/checkpoints/ directory.
    """

    def __init__(self, project_dir: Path):
        """Initialize checkpoint manager.

        Args:
            project_dir: Project directory path
        """
        self.project_dir = Path(project_dir)
        self.workflow_dir = self.project_dir / ".workflow"
        self.checkpoints_dir = self.workflow_dir / "checkpoints"
        self.index_file = self.checkpoints_dir / "index.json"

    def _generate_checkpoint_id(self, name: str, timestamp: datetime) -> str:
        """Generate unique checkpoint ID."""
        content = f"{name}-{timestamp.isoformat()}-{self.project_dir}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def _load_index(self) -> dict[str, dict]:
        """Load checkpoint index."""
        if not self.index_file.exists():
            return {}

        try:
            return json.loads(self.index_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load checkpoint index: {e}")
            return {}

    def _save_index(self, index: dict[str, dict]) -> None:
        """Save checkpoint index."""
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(index, indent=2))

    def _get_current_state(self) -> dict:
        """Get current workflow state.

        Uses StateProjector to get state from checkpoint if available,
        falling back to state.json for backwards compatibility.
        """
        try:
            from .state_projector import StateProjector

            projector = StateProjector(self.project_dir)
            state = projector.get_state()
            if state is not None:
                return state
        except ImportError:
            logger.debug("StateProjector not available, falling back to direct read")
        except Exception as e:
            logger.debug(f"StateProjector failed: {e}, falling back to direct read")

        # Fallback: direct read from state.json
        state_file = self.workflow_dir / "state.json"
        if state_file.exists():
            try:
                return json.loads(state_file.read_text())
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to read state.json: {e}")
        return {}

    def _get_task_progress(self, state: dict) -> dict:
        """Extract task progress from state."""
        tasks = state.get("tasks", [])
        if not tasks:
            return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0}

        completed = sum(1 for t in tasks if t.get("status") == "completed")
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        pending = sum(1 for t in tasks if t.get("status") == "pending")

        return {
            "total": len(tasks),
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
        }

    def _get_tracked_files(self) -> list[str]:
        """Get list of tracked files in project."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")
        except Exception as e:
            logger.debug(f"Failed to get tracked files: {e}")

        return []

    def create_checkpoint(
        self,
        name: str,
        notes: str = "",
        include_files: bool = False,
    ) -> Checkpoint:
        """Create a new checkpoint.

        Args:
            name: Human-readable checkpoint name
            notes: Optional notes about this checkpoint
            include_files: Whether to record file list

        Returns:
            Created Checkpoint object
        """
        timestamp = datetime.now()
        checkpoint_id = self._generate_checkpoint_id(name, timestamp)

        # Get current state
        state = self._get_current_state()
        task_progress = self._get_task_progress(state)

        # Get files if requested
        files = self._get_tracked_files() if include_files else []

        # Create checkpoint
        checkpoint = Checkpoint(
            id=checkpoint_id,
            name=name,
            notes=notes,
            created_at=timestamp,
            phase=state.get("current_phase", 0),
            task_progress=task_progress,
            state_snapshot=state,
            files_snapshot=files,
        )

        # Save checkpoint data
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Save checkpoint metadata
        (checkpoint_dir / "checkpoint.json").write_text(json.dumps(checkpoint.to_dict(), indent=2))

        # Copy current state.json
        state_file = self.workflow_dir / "state.json"
        if state_file.exists():
            shutil.copy(state_file, checkpoint_dir / "state.json")

        # Update index
        index = self._load_index()
        index[checkpoint_id] = {
            "name": name,
            "notes": notes,
            "created_at": timestamp.isoformat(),
            "phase": checkpoint.phase,
        }
        self._save_index(index)

        logger.info(f"Created checkpoint: {checkpoint.summary()}")
        return checkpoint

    def list_checkpoints(self) -> list[Checkpoint]:
        """List all checkpoints for this project.

        Returns:
            List of Checkpoint objects, sorted by creation time
        """
        checkpoints = []
        index = self._load_index()

        for checkpoint_id in index:
            checkpoint_dir = self.checkpoints_dir / checkpoint_id
            checkpoint_file = checkpoint_dir / "checkpoint.json"

            if checkpoint_file.exists():
                try:
                    data = json.loads(checkpoint_file.read_text())
                    checkpoints.append(Checkpoint.from_dict(data))
                except (OSError, json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to load checkpoint {checkpoint_id}: {e}")

        # Sort by creation time
        checkpoints.sort(key=lambda c: c.created_at)
        return checkpoints

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a specific checkpoint by ID.

        Args:
            checkpoint_id: Full or partial checkpoint ID

        Returns:
            Checkpoint if found, None otherwise
        """
        index = self._load_index()

        # Try exact match first
        if checkpoint_id in index:
            checkpoint_dir = self.checkpoints_dir / checkpoint_id
        else:
            # Try partial match
            matches = [cid for cid in index if cid.startswith(checkpoint_id)]
            if len(matches) == 1:
                checkpoint_dir = self.checkpoints_dir / matches[0]
            elif len(matches) > 1:
                logger.warning(f"Ambiguous checkpoint ID '{checkpoint_id}': {matches}")
                return None
            else:
                logger.warning(f"Checkpoint not found: {checkpoint_id}")
                return None

        checkpoint_file = checkpoint_dir / "checkpoint.json"
        if checkpoint_file.exists():
            try:
                data = json.loads(checkpoint_file.read_text())
                return Checkpoint.from_dict(data)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to load checkpoint: {e}")

        return None

    def rollback_to_checkpoint(
        self,
        checkpoint_id: str,
        confirm: bool = False,
    ) -> bool:
        """Rollback workflow state to a checkpoint.

        WARNING: This overwrites current state.json with checkpoint state.

        Args:
            checkpoint_id: Checkpoint ID to rollback to
            confirm: Must be True to actually perform rollback

        Returns:
            True if rollback successful
        """
        if not confirm:
            logger.warning("Rollback requires confirm=True")
            return False

        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            return False

        # Get checkpoint state file
        checkpoint_dir = self.checkpoints_dir / checkpoint.id
        checkpoint_state = checkpoint_dir / "state.json"

        if not checkpoint_state.exists():
            logger.error(f"Checkpoint state file not found: {checkpoint_state}")
            return False

        # Backup current state
        current_state = self.workflow_dir / "state.json"
        if current_state.exists():
            backup_name = f"state.json.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy(current_state, self.workflow_dir / backup_name)
            logger.info(f"Backed up current state to: {backup_name}")

        # Restore checkpoint state
        shutil.copy(checkpoint_state, current_state)
        logger.info(f"Rolled back to checkpoint: {checkpoint.summary()}")

        return True

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to delete

        Returns:
            True if deleted successfully
        """
        checkpoint = self.get_checkpoint(checkpoint_id)
        if not checkpoint:
            return False

        # Remove checkpoint directory
        checkpoint_dir = self.checkpoints_dir / checkpoint.id
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)

        # Update index
        index = self._load_index()
        if checkpoint.id in index:
            del index[checkpoint.id]
            self._save_index(index)

        logger.info(f"Deleted checkpoint: {checkpoint.id}")
        return True

    def prune_old_checkpoints(self, keep_count: int = 10) -> int:
        """Remove old checkpoints, keeping the most recent ones.

        Args:
            keep_count: Number of checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        checkpoints = self.list_checkpoints()

        if len(checkpoints) <= keep_count:
            return 0

        # Sort by creation time (oldest first)
        to_delete = checkpoints[:-keep_count]
        deleted = 0

        for checkpoint in to_delete:
            if self.delete_checkpoint(checkpoint.id):
                deleted += 1

        logger.info(f"Pruned {deleted} old checkpoints")
        return deleted


def create_checkpoint_manager(project_dir: Path) -> CheckpointManager:
    """Create a checkpoint manager for a project.

    Args:
        project_dir: Project directory

    Returns:
        Configured CheckpointManager
    """
    return CheckpointManager(project_dir)


def quick_checkpoint(
    project_dir: Path,
    name: str,
    notes: str = "",
) -> Checkpoint:
    """Convenience function to create a checkpoint quickly.

    Args:
        project_dir: Project directory
        name: Checkpoint name
        notes: Optional notes

    Returns:
        Created Checkpoint
    """
    manager = create_checkpoint_manager(project_dir)
    return manager.create_checkpoint(name, notes)
