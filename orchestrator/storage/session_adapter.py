"""Session storage adapter.

Provides unified interface for session management using SurrealDB.
This is the DB-only version - no file fallback.
"""

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .async_utils import run_async
from .base import SessionData, SessionStorageProtocol

logger = logging.getLogger(__name__)


class SessionStorageAdapter(SessionStorageProtocol):
    """Storage adapter for session management.

    Uses SurrealDB as the only storage backend. No file fallback.

    Usage:
        adapter = SessionStorageAdapter(project_dir)

        # Create a new session
        session = adapter.create_session("T1", agent="claude")

        # Get resume arguments
        args = adapter.get_resume_args("T1")  # ["--resume", "session-id"] or []

        # Record an invocation
        adapter.record_invocation("T1", cost_usd=0.05)

        # Close session when done
        adapter.close_session("T1")
    """

    def __init__(
        self,
        project_dir: Path,
        project_name: Optional[str] = None,
    ):
        """Initialize session storage adapter.

        Args:
            project_dir: Project directory
            project_name: Project name (defaults to directory name)
        """
        self.project_dir = Path(project_dir)
        self.project_name = project_name or self.project_dir.name
        self._db_backend: Optional[Any] = None

    def _get_db_backend(self) -> Any:
        """Get or create database backend."""
        if self._db_backend is None:
            from orchestrator.db.repositories.sessions import get_session_repository

            self._db_backend = get_session_repository(self.project_name)
        return self._db_backend

    def _generate_session_id(self, task_id: str) -> str:
        """Generate a unique session ID.

        Args:
            task_id: Task identifier

        Returns:
            Generated session ID
        """
        timestamp = datetime.now().isoformat()
        random_bytes = os.urandom(4).hex()
        hash_input = f"{task_id}-{timestamp}-{random_bytes}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
        return f"{task_id}-{hash_value}"

    def create_session(
        self,
        task_id: str,
        agent: str = "claude",
        session_id: Optional[str] = None,
    ) -> SessionData:
        """Create a new session for a task.

        Args:
            task_id: Task identifier
            agent: Agent identifier (default: claude)
            session_id: Optional session ID (auto-generated if not provided)

        Returns:
            SessionData for the new session
        """
        if session_id is None:
            session_id = self._generate_session_id(task_id)

        db = self._get_db_backend()
        session = run_async(
            db.create_session(
                session_id=session_id,
                task_id=task_id,
                agent=agent,
            )
        )
        return self._db_session_to_data(session)

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found
        """
        db = self._get_db_backend()
        session = run_async(db.get_session(session_id))
        if session:
            return self._db_session_to_data(session)
        return None

    def get_active_session(self, task_id: str) -> Optional[SessionData]:
        """Get the active session for a task.

        Args:
            task_id: Task identifier

        Returns:
            Active SessionData if exists
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            return self._db_session_to_data(session)
        return None

    def get_resume_args(self, task_id: str) -> list[str]:
        """Get CLI arguments to resume a session.

        If a valid session exists for the task, returns:
            ["--resume", "<session_id>"]

        Otherwise returns empty list (start fresh).

        Args:
            task_id: Task identifier

        Returns:
            CLI arguments list
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            return ["--resume", session.id]
        return []

    def get_session_id_args(self, task_id: str) -> list[str]:
        """Get CLI arguments to set a new session ID.

        If a session exists, returns its ID. Otherwise creates one.
        Returns: ["--session-id", "<session_id>"]

        Args:
            task_id: Task identifier

        Returns:
            CLI arguments list
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            return ["--session-id", session.id]
        # Create new session
        new_session = self.create_session(task_id)
        return ["--session-id", new_session.id]

    def touch_session(self, task_id: str) -> None:
        """Update the session's last used timestamp.

        Args:
            task_id: Task identifier
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            run_async(db.touch_session(session.id))

    def capture_session_id_from_output(self, task_id: str, output: str) -> Optional[str]:
        """Capture and record session ID from CLI output.

        For DB backend, sessions are managed internally.

        Args:
            task_id: Task identifier
            output: CLI output that may contain session ID

        Returns:
            None (DB backend manages sessions internally)
        """
        return None

    def close_session(self, task_id: str) -> bool:
        """Close the session for a task.

        Args:
            task_id: Task identifier

        Returns:
            True if session was closed
        """
        db = self._get_db_backend()
        result = run_async(db.close_task_sessions(task_id))
        return result is not None

    def record_invocation(self, task_id: str, cost_usd: float = 0.0) -> None:
        """Record an invocation in the current session.

        Args:
            task_id: Task identifier
            cost_usd: Cost of this invocation
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            run_async(db.record_invocation(session.id, cost_usd))

    def get_or_create_session(
        self,
        task_id: str,
        agent: str = "claude",
    ) -> SessionData:
        """Get existing session or create new one.

        Args:
            task_id: Task identifier
            agent: Agent identifier (default: claude)

        Returns:
            SessionData
        """
        session = self.get_active_session(task_id)
        if session:
            return session
        return self.create_session(task_id, agent)

    def list_sessions(
        self,
        include_inactive: bool = False,
    ) -> list[SessionData]:
        """List all sessions.

        Args:
            include_inactive: Whether to include inactive sessions

        Returns:
            List of sessions
        """
        db = self._get_db_backend()
        sessions = run_async(db.find_all())
        result = [self._db_session_to_data(s) for s in sessions]
        if not include_inactive:
            result = [s for s in result if s.status == "active"]
        return result

    def delete_session(self, task_id: str) -> bool:
        """Delete a session completely.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted
        """
        db = self._get_db_backend()
        session = run_async(db.get_active_session(task_id))
        if session:
            run_async(db.delete(session.id))
            return True
        return False

    @staticmethod
    def _db_session_to_data(session: Any) -> SessionData:
        """Convert database session to data class."""
        return SessionData(
            id=session.id,
            task_id=session.task_id,
            agent=session.agent,
            status=session.status,
            invocation_count=session.invocation_count,
            total_cost_usd=session.total_cost_usd,
            created_at=session.created_at,
            updated_at=session.updated_at,
            closed_at=session.closed_at,
        )


# Cache of adapters per project
_session_adapters: dict[str, SessionStorageAdapter] = {}


def get_session_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> SessionStorageAdapter:
    """Get or create session storage adapter for a project.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        SessionStorageAdapter instance
    """
    key = str(Path(project_dir).resolve())

    if key not in _session_adapters:
        _session_adapters[key] = SessionStorageAdapter(project_dir, project_name)
    return _session_adapters[key]
