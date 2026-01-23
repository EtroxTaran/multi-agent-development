"""Storage Repository Interface.

Defines the contract for workflow state persistence and retrieval.
This abstraction allows decoupling the Orchestrator from specific
storage backends (e.g. SurrealDB, FileSystem, Memory).
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from pathlib import Path

from ..models import PhaseStatus


class StorageRepository(ABC):
    """Abstract base class for storage repositories."""

    @abstractmethod
    def get_state(self) -> Optional[Any]:
        """Retrieve the current workflow state.
        
        Returns:
            Workflow state object or None if not found.
        """
        pass

    @abstractmethod
    def save_state(self, state: Any) -> None:
        """Save the workflow state.
        
        Args:
            state: Workflow state object to save.
        """
        pass

    @abstractmethod
    def get_summary(self) -> dict:
        """Get a summary of the workflow status.
        
        Returns:
            Dictionary with project status summary.
        """
        pass

    @abstractmethod
    def reset_state(self) -> None:
        """Reset the workflow state to initial values."""
        pass

    @abstractmethod
    def reset_to_phase(self, phase: int) -> None:
        """Reset workflow state to the beginning of a specific phase.
        
        Args:
            phase: Phase number (1-5) to reset to.
        """
        pass

    @abstractmethod
    def record_git_commit(self, phase: int, commit_hash: str, message: str) -> None:
        """Record a git commit associated with a phase.
        
        Args:
            phase: Phase number.
            commit_hash: Git commit hash.
            message: Commit message.
        """
        pass

    @abstractmethod
    def get_git_commits(self) -> list[dict]:
        """Retrieve history of recorded git commits.
        
        Returns:
            List of commit dictionaries.
        """
        pass
