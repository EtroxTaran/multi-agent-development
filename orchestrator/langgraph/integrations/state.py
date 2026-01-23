"""LangGraph adapter for StateManager.

Provides bidirectional sync between LangGraph workflow state
and the existing file-based StateManager.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...utils.state import PhaseState as LegacyPhaseState
from ...utils.state import PhaseStatus as LegacyPhaseStatus
from ...utils.state import StateManager
from ...utils.state import WorkflowState as LegacyWorkflowState
from ..state import PhaseState, PhaseStatus, WorkflowState, create_initial_state

logger = logging.getLogger(__name__)


class LangGraphStateAdapter:
    """Adapter for syncing LangGraph state with StateManager.

    DEPRECATION NOTICE: This adapter's dual-write functionality is deprecated.
    State should now be managed exclusively through LangGraph checkpoints,
    with state.json generated on-demand via StateProjector.

    Use cases:
    - load_as_langgraph_state(): Still useful for one-time migration from
      legacy state.json to LangGraph checkpoints.
    - save_langgraph_state(): DEPRECATED - state.json is now projected
      from checkpoints on-demand. Do not call directly.

    Migration path:
    1. Use StateProjector.project_state() to generate state.json from checkpoints
    2. Read state via StateProjector.get_state() (auto-projects from checkpoint)
    3. All state modifications flow through LangGraph workflow nodes
    """

    # Map between phase numbers and names
    PHASE_MAP = {
        0: "prerequisites",
        1: "planning",
        2: "validation",
        3: "implementation",
        4: "verification",
        5: "completion",
    }

    # Map between LangGraph PhaseStatus and Legacy PhaseStatus
    STATUS_MAP = {
        PhaseStatus.PENDING: LegacyPhaseStatus.PENDING,
        PhaseStatus.IN_PROGRESS: LegacyPhaseStatus.IN_PROGRESS,
        PhaseStatus.COMPLETED: LegacyPhaseStatus.COMPLETED,
        PhaseStatus.FAILED: LegacyPhaseStatus.FAILED,
        PhaseStatus.SKIPPED: LegacyPhaseStatus.PENDING,  # No SKIPPED in legacy
    }

    REVERSE_STATUS_MAP = {
        LegacyPhaseStatus.PENDING: PhaseStatus.PENDING,
        LegacyPhaseStatus.IN_PROGRESS: PhaseStatus.IN_PROGRESS,
        LegacyPhaseStatus.COMPLETED: PhaseStatus.COMPLETED,
        LegacyPhaseStatus.FAILED: PhaseStatus.FAILED,
        LegacyPhaseStatus.BLOCKED: PhaseStatus.FAILED,
    }

    def __init__(self, project_dir: str | Path):
        """Initialize the adapter.

        Args:
            project_dir: Project directory path
        """
        self.project_dir = Path(project_dir)
        self.state_manager = StateManager(project_dir)

    def load_as_langgraph_state(self) -> WorkflowState:
        """Load legacy state and convert to LangGraph format.

        Returns:
            LangGraph WorkflowState TypedDict
        """
        legacy_state = self.state_manager.load()

        # Create base LangGraph state
        lg_state: WorkflowState = create_initial_state(
            project_dir=str(self.project_dir),
            project_name=legacy_state.project_name,
        )

        # Convert phase statuses
        phase_status = {}
        for phase_num, phase_name in self.PHASE_MAP.items():
            if phase_num == 0:
                continue  # Prerequisites not in legacy

            if phase_name in legacy_state.phases:
                legacy_phase = legacy_state.phases[phase_name]
                lg_phase = self._convert_legacy_phase(legacy_phase, phase_num)
                phase_status[str(phase_num)] = lg_phase

        lg_state["phase_status"] = phase_status
        lg_state["current_phase"] = legacy_state.current_phase
        lg_state["iteration_count"] = legacy_state.iteration_count
        lg_state["git_commits"] = legacy_state.git_commits
        lg_state["created_at"] = legacy_state.created_at
        lg_state["updated_at"] = legacy_state.updated_at

        # Load plan if it exists
        plan_file = self.project_dir / ".workflow" / "phases" / "planning" / "plan.json"
        if plan_file.exists():
            import json

            try:
                lg_state["plan"] = json.loads(plan_file.read_text())
            except json.JSONDecodeError:
                pass

        logger.info(f"Loaded legacy state for project: {legacy_state.project_name}")
        return lg_state

    def save_langgraph_state(self, lg_state: WorkflowState) -> None:
        """Save LangGraph state to legacy format.

        DEPRECATED: State should now be persisted through LangGraph checkpoints
        and projected to state.json on-demand via StateProjector.

        This method is retained for backwards compatibility during migration
        but should not be called in new code.

        Args:
            lg_state: LangGraph WorkflowState
        """
        import warnings

        warnings.warn(
            "save_langgraph_state() is deprecated. State should be persisted "
            "through LangGraph checkpoints and projected via StateProjector.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Load existing legacy state or create new
        if self.state_manager.state_file.exists():
            legacy_state = self.state_manager.load()
        else:
            legacy_state = LegacyWorkflowState(
                project_name=lg_state.get("project_name", self.project_dir.name)
            )
            self.state_manager._state = legacy_state

        # Update legacy state from LangGraph state
        legacy_state.current_phase = lg_state.get("current_phase", 1)
        legacy_state.iteration_count = lg_state.get("iteration_count", 0)
        legacy_state.git_commits = lg_state.get("git_commits", [])
        legacy_state.updated_at = datetime.now().isoformat()

        # Convert phase statuses
        phase_status = lg_state.get("phase_status", {})
        for phase_num_str, lg_phase in phase_status.items():
            phase_num = int(phase_num_str)
            if phase_num == 0:
                continue

            phase_name = self.PHASE_MAP.get(phase_num)
            if phase_name and phase_name in legacy_state.phases:
                self._update_legacy_phase(legacy_state.phases[phase_name], lg_phase)

        self.state_manager.save()
        logger.info(f"Saved LangGraph state for project: {legacy_state.project_name}")

    def sync_phase(
        self,
        phase_num: int,
        lg_state: WorkflowState,
    ) -> None:
        """Sync a specific phase to legacy state.

        DEPRECATED: Phase state should be persisted through LangGraph checkpoints
        and projected to state.json on-demand via StateProjector.

        Args:
            phase_num: Phase number to sync
            lg_state: LangGraph state containing phase updates
        """
        import warnings

        warnings.warn(
            "sync_phase() is deprecated. State should be persisted "
            "through LangGraph checkpoints and projected via StateProjector.",
            DeprecationWarning,
            stacklevel=2,
        )
        phase_status = lg_state.get("phase_status", {})
        lg_phase = phase_status.get(str(phase_num))

        if not lg_phase:
            return

        phase_name = self.PHASE_MAP.get(phase_num)
        if not phase_name:
            return

        legacy_state = self.state_manager.load()
        if phase_name in legacy_state.phases:
            self._update_legacy_phase(legacy_state.phases[phase_name], lg_phase)
            self.state_manager.save()

    def start_phase(self, phase_num: int) -> dict[str, Any]:
        """Start a phase and return state update.

        Args:
            phase_num: Phase number to start

        Returns:
            State update dict for LangGraph
        """
        phase = self.state_manager.start_phase(phase_num)
        return {
            "current_phase": phase_num,
            "phase_status": {str(phase_num): self._convert_legacy_phase(phase, phase_num)},
        }

    def complete_phase(
        self,
        phase_num: int,
        outputs: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Complete a phase and return state update.

        Args:
            phase_num: Phase number to complete
            outputs: Optional phase outputs

        Returns:
            State update dict for LangGraph
        """
        phase = self.state_manager.complete_phase(phase_num, outputs)
        return {
            "phase_status": {str(phase_num): self._convert_legacy_phase(phase, phase_num)},
        }

    def fail_phase(
        self,
        phase_num: int,
        error: str,
    ) -> dict[str, Any]:
        """Mark a phase as failed and return state update.

        Args:
            phase_num: Phase number to fail
            error: Error message

        Returns:
            State update dict for LangGraph
        """
        phase = self.state_manager.fail_phase(phase_num, error)
        return {
            "phase_status": {str(phase_num): self._convert_legacy_phase(phase, phase_num)},
        }

    def record_commit(
        self,
        phase_num: int,
        commit_hash: str,
        message: str,
    ) -> None:
        """Record a git commit.

        Args:
            phase_num: Phase number
            commit_hash: Git commit hash
            message: Commit message
        """
        self.state_manager.record_commit(phase_num, commit_hash, message)

    def get_summary(self) -> dict:
        """Get workflow summary.

        Returns:
            Summary dictionary
        """
        return self.state_manager.get_summary()

    def can_retry(self, phase_num: int) -> bool:
        """Check if a phase can be retried.

        Args:
            phase_num: Phase number

        Returns:
            True if phase can be retried
        """
        return self.state_manager.can_retry(phase_num)

    def _convert_legacy_phase(
        self,
        legacy: LegacyPhaseState,
        phase_num: int,
    ) -> PhaseState:
        """Convert legacy PhaseState to LangGraph PhaseState.

        Args:
            legacy: Legacy PhaseState
            phase_num: Phase number

        Returns:
            LangGraph PhaseState
        """
        status = self.REVERSE_STATUS_MAP.get(legacy.status, PhaseStatus.PENDING)

        return PhaseState(
            status=status,
            started_at=legacy.started_at,
            completed_at=legacy.completed_at,
            attempts=legacy.attempts,
            max_attempts=legacy.max_attempts,
            blockers=legacy.blockers,
            error=legacy.error,
            output=legacy.outputs,
        )

    def _update_legacy_phase(
        self,
        legacy: LegacyPhaseState,
        lg_phase: PhaseState,
    ) -> None:
        """Update legacy PhaseState from LangGraph PhaseState.

        Args:
            legacy: Legacy PhaseState to update
            lg_phase: LangGraph PhaseState source
        """
        if hasattr(lg_phase, "status"):
            legacy.status = self.STATUS_MAP.get(lg_phase.status, LegacyPhaseStatus.PENDING)
        elif isinstance(lg_phase, dict):
            status_val = lg_phase.get("status")
            if isinstance(status_val, PhaseStatus):
                legacy.status = self.STATUS_MAP.get(status_val, LegacyPhaseStatus.PENDING)
            elif isinstance(status_val, str):
                try:
                    legacy.status = LegacyPhaseStatus(status_val)
                except ValueError:
                    pass

        # Update other fields
        if hasattr(lg_phase, "started_at"):
            legacy.started_at = lg_phase.started_at
        elif isinstance(lg_phase, dict):
            legacy.started_at = lg_phase.get("started_at")

        if hasattr(lg_phase, "completed_at"):
            legacy.completed_at = lg_phase.completed_at
        elif isinstance(lg_phase, dict):
            legacy.completed_at = lg_phase.get("completed_at")

        if hasattr(lg_phase, "attempts"):
            legacy.attempts = lg_phase.attempts
        elif isinstance(lg_phase, dict):
            legacy.attempts = lg_phase.get("attempts", 0)

        if hasattr(lg_phase, "error"):
            legacy.error = lg_phase.error
        elif isinstance(lg_phase, dict):
            legacy.error = lg_phase.get("error")

        if hasattr(lg_phase, "output"):
            legacy.outputs = lg_phase.output
        elif isinstance(lg_phase, dict):
            legacy.outputs = lg_phase.get("output", {})


def create_state_adapter(project_dir: str | Path) -> LangGraphStateAdapter:
    """Factory function to create a state adapter.

    Args:
        project_dir: Project directory path

    Returns:
        LangGraphStateAdapter instance
    """
    return LangGraphStateAdapter(project_dir)
