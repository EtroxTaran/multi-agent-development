"""SurrealDB Workflow Repository.

Implementation of StorageRepository using SurrealDB backend.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .repository import StorageRepository
from .async_utils import run_async
from ..db.repositories.workflow import get_workflow_repository

logger = logging.getLogger(__name__)


class SurrealWorkflowRepository(StorageRepository):
    """Workflow storage implementation using SurrealDB."""

    def __init__(
        self,
        project_dir: Path,
        project_name: Optional[str] = None,
    ):
        """Initialize the repository.

        Args:
            project_dir: Project directory
            project_name: Project name (defaults to directory name)
        """
        self.project_dir = Path(project_dir)
        self.project_name = project_name or self.project_dir.name
        self._db_backend = None

    def _get_db_backend(self) -> Any:
        """Get or create database backend."""
        if self._db_backend is None:
            self._db_backend = get_workflow_repository(self.project_name)
        return self._db_backend

    def get_state(self) -> Optional[Any]:
        """Retrieve the current workflow state.
        
        Returns:
            Workflow state object or None if not found.
        """
        db = self._get_db_backend()
        return run_async(db.get_state())

    def save_state(self, state: Any) -> None:
        """Save the workflow state.
        
        Args:
            state: Workflow state object to save.
        """
        # Note: In the current architecture, state updates are granular via methods like update_state
        # rather than saving the whole state object at once.
        # This method is primarily for interface compliance or full-state overwrites if needed.
        # For now, we'll log a warning if used, as we prefer granular updates.
        logger.warning("save_state called on SurrealWorkflowRepository - prefer granular updates")
        pass

    def get_summary(self) -> dict:
        """Get a summary of the workflow status.
        
        Returns:
            Dictionary with project status summary.
        """
        db = self._get_db_backend()
        return run_async(db.get_summary())

    def reset_state(self) -> None:
        """Reset the workflow state to initial values."""
        db = self._get_db_backend()
        run_async(db.reset_state())

    def reset_to_phase(self, phase: int) -> None:
        """Reset workflow state to the beginning of a specific phase.
        
        Args:
            phase: Phase number (1-5) to reset to.
        """
        db = self._get_db_backend()
        run_async(db.reset_to_phase(phase))

    def record_git_commit(self, phase: int, commit_hash: str, message: str) -> None:
        """Record a git commit associated with a phase.
        
        Args:
            phase: Phase number.
            commit_hash: Git commit hash.
            message: Commit message.
        """
        db = self._get_db_backend()
        run_async(db.record_git_commit(phase, commit_hash, message))

    def get_git_commits(self) -> list[dict]:
        """Retrieve history of recorded git commits.
        
        Returns:
            List of commit dictionaries.
        """
        db = self._get_db_backend()
        return run_async(db.get_git_commits())
    
    # --- Additional methods specific to current WorkflowStorageAdapter usage ---
    
    def initialize_state(
        self,
        project_dir: str,
        execution_mode: str = "afk",
    ) -> Any:
        db = self._get_db_backend()
        return run_async(
            db.initialize_state(
                project_dir=project_dir,
                execution_mode=execution_mode,
            )
        )

    def update_state(self, **updates: Any) -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.update_state(**updates))

    def set_phase(self, phase: int, status: str = "in_progress") -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.set_phase(phase, status))

    def increment_iteration(self) -> int:
        db = self._get_db_backend()
        state = run_async(db.increment_iteration())
        return state.iteration_count if state else 0

    def set_plan(self, plan: dict) -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.set_plan(plan))

    def set_validation_feedback(self, agent: str, feedback: dict) -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.set_validation_feedback(agent, feedback))

    def set_verification_feedback(self, agent: str, feedback: dict) -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.set_verification_feedback(agent, feedback))

    def set_implementation_result(self, result: dict) -> Optional[Any]:
        db = self._get_db_backend()
        return run_async(db.set_implementation_result(result))

    def set_decision(self, decision: str) -> Optional[Any]:
        return self.update_state(next_decision=decision)