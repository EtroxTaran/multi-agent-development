"""State projector for generating state.json from SQLite checkpoints.

This module provides a read-only projection of workflow state from the
authoritative SQLite checkpoint database. This ensures state.json is
always consistent with the checkpoint and eliminates dual-write issues.

Usage:
    projector = StateProjector(project_dir)
    state = projector.project_state_sync()  # Generates state.json

    # Or async version
    state = await projector.project_state()
"""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StateProjector:
    """Projects workflow state from SQLite checkpoints to state.json.

    This class provides a single source of truth for state by:
    1. Reading state from SQLite checkpoint (authoritative source)
    2. Converting to legacy state.json format
    3. Writing atomically to prevent corruption

    The projection is read-only from the perspective of state consumers -
    all state modifications should go through the LangGraph workflow.
    """

    def __init__(
        self,
        project_dir: str | Path,
    ):
        """Initialize the state projector.

        Args:
            project_dir: Project directory path
        """
        self.project_dir = Path(project_dir)
        self.workflow_dir = self.project_dir / ".workflow"
        self.state_file = self.workflow_dir / "state.json"

    async def project_state(
        self,
        thread_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Project state from checkpoint to state.json.

        Reads the latest checkpoint state from SurrealDB, converts it to
        the legacy state.json format, and writes atomically.

        Args:
            thread_id: Optional thread ID to load (defaults to project-based)

        Returns:
            The projected state dict, or None if no checkpoint exists
        """
        try:
            # Load checkpoint state
            lg_state = await self._load_checkpoint_state(thread_id)

            if lg_state is None:
                logger.debug("No checkpoint state found")
                return self._load_fallback_state()

            # Convert to legacy format
            legacy_state = self._convert_to_legacy_format(lg_state)

            # Atomic write to state.json
            self._atomic_write_state(legacy_state)

            logger.info(f"Projected state to {self.state_file}")
            return legacy_state

        except Exception as e:
            logger.warning(f"Failed to project state: {e}")
            return self._load_fallback_state()

    def project_state_sync(
        self,
        thread_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Synchronous wrapper for project_state.

        Args:
            thread_id: Optional thread ID to load

        Returns:
            The projected state dict, or None if no checkpoint exists
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # We're in an async context, create a new task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.project_state(thread_id))
                return future.result()
        else:
            return asyncio.run(self.project_state(thread_id))

    async def _load_checkpoint_state(
        self,
        thread_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Load state from SurrealDB checkpoint.

        Args:
            thread_id: Thread ID to load (defaults to project-based)

        Returns:
            LangGraph state dict or None
        """
        from ..db.config import is_surrealdb_enabled
        from ..langgraph.surrealdb_saver import SurrealDBSaver

        if not is_surrealdb_enabled():
            logger.debug("SurrealDB not enabled - cannot load checkpoint")
            return None

        if thread_id is None:
            thread_id = f"workflow-{self.project_dir.name}"

        config = {
            "configurable": {
                "thread_id": thread_id,
            },
        }

        try:
            # Create a temporary checkpointer to read state
            checkpointer = SurrealDBSaver(self.project_dir.name)

            # Get the latest checkpoint
            checkpoint_tuple = await checkpointer.aget_tuple(config)

            if checkpoint_tuple is None:
                return None

            # Extract the checkpoint state
            checkpoint = checkpoint_tuple.checkpoint

            # LangGraph v0.2.x uses 'channel_values' in the checkpoint dict
            # or it might be the checkpoint object itself if it has channel_values attribute
            if hasattr(checkpoint, "channel_values"):
                return checkpoint.channel_values
            elif isinstance(checkpoint, dict):
                return checkpoint.get("channel_values", {})
            return {}

        except Exception as e:
            logger.warning(f"Failed to load checkpoint state: {e}")
            return None

    def _convert_to_legacy_format(
        self,
        lg_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert LangGraph state to legacy state.json format.

        Args:
            lg_state: LangGraph WorkflowState

        Returns:
            Legacy state.json format dict
        """
        # Phase name mapping
        phase_names = {
            1: "planning",
            2: "validation",
            3: "implementation",
            4: "verification",
            5: "completion",
        }

        # Convert phase statuses
        phases = {}
        phase_status = lg_state.get("phase_status", {})

        for phase_num_str, phase_state in phase_status.items():
            phase_num = int(phase_num_str)
            phase_name = phase_names.get(phase_num)

            if phase_name and phase_state:
                # Handle both PhaseState dataclass and dict
                if hasattr(phase_state, "to_dict"):
                    phases[phase_name] = phase_state.to_dict()
                elif isinstance(phase_state, dict):
                    phases[phase_name] = {
                        "status": phase_state.get("status", "pending"),
                        "attempts": phase_state.get("attempts", 0),
                        "max_attempts": phase_state.get("max_attempts", 3),
                        "started_at": phase_state.get("started_at"),
                        "completed_at": phase_state.get("completed_at"),
                        "error": phase_state.get("error"),
                        "blockers": phase_state.get("blockers", []),
                    }
                else:
                    # PhaseState dataclass - extract attributes
                    phases[phase_name] = {
                        "status": getattr(phase_state, "status", "pending"),
                        "attempts": getattr(phase_state, "attempts", 0),
                        "max_attempts": getattr(phase_state, "max_attempts", 3),
                        "started_at": getattr(phase_state, "started_at", None),
                        "completed_at": getattr(phase_state, "completed_at", None),
                        "error": getattr(phase_state, "error", None),
                        "blockers": getattr(phase_state, "blockers", []),
                    }

                    # Convert enum status to string
                    if hasattr(phases[phase_name]["status"], "value"):
                        phases[phase_name]["status"] = phases[phase_name]["status"].value

        # Build legacy state
        legacy_state = {
            "project_name": lg_state.get("project_name", self.project_dir.name),
            "current_phase": lg_state.get("current_phase", 1),
            "iteration_count": lg_state.get("iteration_count", 0),
            "phases": phases,
            "git_commits": lg_state.get("git_commits", []),
            "created_at": lg_state.get("created_at", datetime.now().isoformat()),
            "updated_at": lg_state.get("updated_at", datetime.now().isoformat()),
        }

        # Add task information if present
        tasks = lg_state.get("tasks", [])
        if tasks:
            legacy_state["tasks"] = {
                "total": len(tasks),
                "completed": len(lg_state.get("completed_task_ids", [])),
                "failed": len(lg_state.get("failed_task_ids", [])),
                "current_task_id": lg_state.get("current_task_id"),
            }

        # Add error summary if present
        errors = lg_state.get("errors", [])
        if errors:
            legacy_state["errors_count"] = len(errors)
            # Include last few errors
            legacy_state["recent_errors"] = errors[-5:] if len(errors) > 5 else errors

        return legacy_state

    def _atomic_write_state(self, state: dict[str, Any]) -> None:
        """Write state atomically using temp file + rename.

        This prevents partial writes and corruption.

        Args:
            state: State dict to write
        """
        # Ensure workflow directory exists
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory (ensures same filesystem)
        fd, temp_path = tempfile.mkstemp(
            prefix=".state_",
            suffix=".json.tmp",
            dir=str(self.workflow_dir),
        )

        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2, default=str)

            # Atomic rename
            os.replace(temp_path, str(self.state_file))

        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _load_fallback_state(self) -> Optional[dict[str, Any]]:
        """Load state from state.json as fallback.

        Used when checkpoint is unavailable.

        Returns:
            State dict or None
        """
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load fallback state: {e}")
            return None

    def get_state(self) -> Optional[dict[str, Any]]:
        """Get current state, projecting from checkpoint if available.

        This is the primary method for reading state.

        Returns:
            State dict or None
        """
        # Try to project from checkpoint
        state = self.project_state_sync()

        if state is not None:
            return state

        # Fall back to reading state.json directly
        return self._load_fallback_state()


def get_state_projector(project_dir: str | Path) -> StateProjector:
    """Factory function to create a state projector.

    Args:
        project_dir: Project directory path

    Returns:
        StateProjector instance
    """
    return StateProjector(project_dir)
