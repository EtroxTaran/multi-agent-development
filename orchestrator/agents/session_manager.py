"""Session manager for Claude Code CLI sessions.

Manages session IDs across task iterations, enabling:
- Session continuity within a task (maintains debugging context)
- Fresh sessions between tasks (prevents cross-contamination)
- Session tracking and cleanup

When using --resume, Claude continues from previous conversation
state instead of starting fresh, preserving file reads and insights.

Reference: https://docs.anthropic.com/claude-code/cli#session-management
"""

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Session storage location
DEFAULT_SESSIONS_DIR = ".workflow/sessions"

# Session expiry for automatic cleanup
SESSION_TTL_HOURS = 24


@dataclass
class SessionInfo:
    """Information about a Claude Code session.

    Attributes:
        session_id: The Claude Code session ID (from --session-id output)
        task_id: The task this session belongs to
        project_dir: Project directory
        created_at: When the session was created
        last_used_at: When the session was last used
        iteration: Current iteration number (for Ralph Wiggum loops)
        is_active: Whether the session is still usable
        metadata: Additional session metadata
    """

    session_id: str
    task_id: str
    project_dir: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime = field(default_factory=datetime.now)
    iteration: int = 1
    is_active: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "project_dir": self.project_dir,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "iteration": self.iteration,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionInfo":
        """Deserialize from dictionary."""
        return cls(
            session_id=data["session_id"],
            task_id=data["task_id"],
            project_dir=data["project_dir"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used_at=datetime.fromisoformat(data["last_used_at"]),
            iteration=data.get("iteration", 1),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Manages Claude Code sessions for task continuity.

    Session Scope: Per-task (not per-project)
    - Each task gets its own session
    - Sessions persist across iterations within a task
    - New tasks get new sessions (avoids cross-contamination)

    Usage:
        manager = SessionManager(project_dir)

        # Get or create session for a task
        session = manager.get_or_create_session("T1")

        # Build resume flag if session exists
        resume_args = manager.get_resume_args("T1")

        # After iteration, mark session as used
        manager.touch_session("T1")

        # When task completes, mark session inactive
        manager.close_session("T1")
    """

    def __init__(
        self,
        project_dir: Path | str,
        sessions_dir: Optional[str] = None,
        session_ttl_hours: int = SESSION_TTL_HOURS,
    ):
        """Initialize session manager.

        Args:
            project_dir: Project directory
            sessions_dir: Directory for session storage (relative to project)
            session_ttl_hours: Hours before sessions expire
        """
        self.project_dir = Path(project_dir)
        self.sessions_dir = self.project_dir / (sessions_dir or DEFAULT_SESSIONS_DIR)
        self.session_ttl_hours = session_ttl_hours

        # Thread safety lock for _sessions dict access
        self._lock = threading.Lock()

        # In-memory cache of active sessions
        self._sessions: dict[str, SessionInfo] = {}

        # Load existing sessions
        self._load_sessions()

    def _load_sessions(self) -> None:
        """Load sessions from disk."""
        if not self.sessions_dir.exists():
            return

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(session_file.read_text())
                session = SessionInfo.from_dict(data)

                # Skip expired sessions
                if self._is_expired(session):
                    session_file.unlink(missing_ok=True)
                    continue

                with self._lock:
                    self._sessions[session.task_id] = session
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to load session {session_file}: {e}")

    def _save_session(self, session: SessionInfo) -> None:
        """Save session to disk."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.sessions_dir / f"{session.task_id}.json"
        session_file.write_text(json.dumps(session.to_dict(), indent=2))

    def _is_expired(self, session: SessionInfo) -> bool:
        """Check if session has expired."""
        expiry = session.last_used_at + timedelta(hours=self.session_ttl_hours)
        return datetime.now() > expiry

    def get_session(self, task_id: str) -> Optional[SessionInfo]:
        """Get existing session for a task.

        Args:
            task_id: Task identifier

        Returns:
            SessionInfo if session exists and is active, None otherwise
        """
        with self._lock:
            session = self._sessions.get(task_id)
            if session is None:
                return None

            if not session.is_active:
                return None

            if self._is_expired(session):
                # Mark as inactive (close_session logic inlined to avoid deadlock)
                session.is_active = False
                self._save_session(session)
                logger.info(f"Closed expired session for task {task_id}")
                return None

            return session

    def create_session(
        self,
        task_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> SessionInfo:
        """Create a new session for a task.

        If a session already exists for the task, it will be closed first.

        Args:
            task_id: Task identifier
            session_id: Optional explicit session ID (usually captured from CLI output)
            metadata: Optional metadata to attach to session

        Returns:
            New SessionInfo
        """
        with self._lock:
            # Close any existing session (inlined to avoid deadlock)
            existing = self._sessions.get(task_id)
            if existing is not None:
                existing.is_active = False
                self._save_session(existing)

            # Generate session ID if not provided
            if session_id is None:
                session_id = self._generate_session_id(task_id)

            session = SessionInfo(
                session_id=session_id,
                task_id=task_id,
                project_dir=str(self.project_dir),
                metadata=metadata or {},
            )

            self._sessions[task_id] = session
            self._save_session(session)

        logger.info(f"Created session {session_id} for task {task_id}")
        return session

    def get_or_create_session(
        self,
        task_id: str,
        metadata: Optional[dict] = None,
    ) -> SessionInfo:
        """Get existing session or create new one.

        Args:
            task_id: Task identifier
            metadata: Metadata for new session (ignored if session exists)

        Returns:
            SessionInfo
        """
        session = self.get_session(task_id)
        if session is not None:
            return session
        return self.create_session(task_id, metadata=metadata)

    def touch_session(self, task_id: str) -> bool:
        """Update session's last used timestamp.

        Call this after each successful iteration.

        Args:
            task_id: Task identifier

        Returns:
            True if session was updated, False if not found
        """
        with self._lock:
            session = self._sessions.get(task_id)
            if session is None:
                return False

            session.last_used_at = datetime.now()
            session.iteration += 1
            self._save_session(session)
            return True

    def close_session(self, task_id: str) -> bool:
        """Close a session (mark inactive).

        Call this when a task completes or fails permanently.

        Args:
            task_id: Task identifier

        Returns:
            True if session was closed, False if not found
        """
        with self._lock:
            session = self._sessions.get(task_id)
            if session is None:
                return False

            session.is_active = False
            self._save_session(session)

        logger.info(f"Closed session for task {task_id}")
        return True

    def delete_session(self, task_id: str) -> bool:
        """Delete a session completely.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            session = self._sessions.pop(task_id, None)
            if session is None:
                return False

        session_file = self.sessions_dir / f"{task_id}.json"
        session_file.unlink(missing_ok=True)

        logger.info(f"Deleted session for task {task_id}")
        return True

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
        session = self.get_session(task_id)
        if session is None:
            return []

        return ["--resume", session.session_id]

    def get_session_id_args(self, task_id: str) -> list[str]:
        """Get CLI arguments to set session ID.

        Used when starting a new session to capture the ID.

        Args:
            task_id: Task identifier

        Returns:
            CLI arguments list
        """
        session = self.get_or_create_session(task_id)
        return ["--session-id", session.session_id]

    def capture_session_id_from_output(
        self,
        task_id: str,
        output: str,
    ) -> Optional[str]:
        """Extract session ID from Claude CLI output and update session.

        Claude Code may output a session ID in the response. This method
        extracts it and updates the stored session.

        Args:
            task_id: Task identifier
            output: CLI stdout output

        Returns:
            Captured session ID or None
        """
        # Look for session ID in output (format may vary)
        # Common patterns:
        # "Session: abc123"
        # "session_id": "abc123"
        patterns = [
            r"[Ss]ession[:\s]+([a-f0-9-]+)",
            r'"session_id"\s*:\s*"([^"]+)"',
            r"session_id=([a-f0-9-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                session_id = match.group(1)
                with self._lock:
                    session = self._sessions.get(task_id)
                    if session and session.is_active and session.session_id != session_id:
                        session.session_id = session_id
                        self._save_session(session)
                return session_id

        return None

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        # Get list of expired task IDs under lock
        with self._lock:
            expired = [
                task_id
                for task_id, session in self._sessions.items()
                if self._is_expired(session) or not session.is_active
            ]

        # Delete each expired session (delete_session handles its own locking)
        for task_id in expired:
            self.delete_session(task_id)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

        return len(expired)

    def list_sessions(self, include_inactive: bool = False) -> list[SessionInfo]:
        """List all sessions.

        Args:
            include_inactive: Whether to include inactive sessions

        Returns:
            List of sessions
        """
        with self._lock:
            sessions = list(self._sessions.values())
        if not include_inactive:
            sessions = [s for s in sessions if s.is_active]
        return sorted(sessions, key=lambda s: s.last_used_at, reverse=True)

    def _generate_session_id(self, task_id: str) -> str:
        """Generate a unique session ID.

        Format: {task_id}-{timestamp_hash}-{random}

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


def extract_session_from_cli_response(response: dict) -> Optional[str]:
    """Extract session ID from parsed Claude CLI JSON response.

    Args:
        response: Parsed JSON response from Claude CLI

    Returns:
        Session ID if found, None otherwise
    """
    # Check common locations in response
    if "session_id" in response:
        return response["session_id"]
    if "metadata" in response and "session_id" in response["metadata"]:
        return response["metadata"]["session_id"]
    return None
