"""
Cleanup manager for artifact lifecycle management.

Manages the lifecycle of artifacts created during agent execution:
- TRANSIENT: Deleted after agent execution completes
- SESSION: Deleted after task completion
- PERSISTENT: Kept for configurable retention period
- PERMANENT: Never deleted (audit trail)

Usage:
    from orchestrator.cleanup import CleanupManager

    manager = CleanupManager(project_dir)
    manager.on_agent_complete("A04", "task-1")
    manager.on_task_done("task-1")
"""

import asyncio
import glob
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ArtifactLifetime(str, Enum):
    """Lifecycle categories for artifacts."""

    TRANSIENT = "transient"  # Deleted after agent execution
    SESSION = "session"  # Deleted after task completion
    PERSISTENT = "persistent"  # Kept for retention period
    PERMANENT = "permanent"  # Never deleted (audit trail)


@dataclass
class CleanupRule:
    """Rule for artifact cleanup."""

    pattern: str  # Glob pattern for matching files
    lifetime: ArtifactLifetime
    max_age_hours: Optional[int] = None  # For PERSISTENT lifetime
    description: str = ""

    def matches(self, path: Path, base_dir: Path) -> bool:
        """Check if a path matches this rule's pattern."""
        try:
            relative_path = path.relative_to(base_dir)
            return path.match(self.pattern) or str(relative_path).startswith(
                self.pattern.rstrip("*").rstrip("/")
            )
        except ValueError:
            return False


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    files_deleted: list[str] = field(default_factory=list)
    directories_deleted: list[str] = field(default_factory=list)
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_deleted(self) -> int:
        """Total number of items deleted."""
        return len(self.files_deleted) + len(self.directories_deleted)

    @property
    def success(self) -> bool:
        """Whether cleanup completed without errors."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_deleted": self.files_deleted,
            "directories_deleted": self.directories_deleted,
            "bytes_freed": self.bytes_freed,
            "errors": self.errors,
            "total_deleted": self.total_deleted,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
        }


# Default cleanup rules
DEFAULT_CLEANUP_RULES = [
    # Transient files - deleted after agent execution
    CleanupRule(
        pattern=".workflow/temp/**/*",
        lifetime=ArtifactLifetime.TRANSIENT,
        description="Temporary files created during agent execution",
    ),
    CleanupRule(
        pattern=".workflow/temp/*",
        lifetime=ArtifactLifetime.TRANSIENT,
        description="Temporary directories for tasks",
    ),
    # Session files - deleted after task completion
    CleanupRule(
        pattern=".workflow/sessions/**/*",
        lifetime=ArtifactLifetime.SESSION,
        description="Session-specific agent outputs and reviews",
    ),
    CleanupRule(
        pattern=".workflow/messages/processing/*",
        lifetime=ArtifactLifetime.SESSION,
        description="Messages being processed",
    ),
    # Persistent files - kept for retention period then cleaned
    CleanupRule(
        pattern=".workflow/messages/archive/**/*",
        lifetime=ArtifactLifetime.PERSISTENT,
        max_age_hours=168,  # 7 days
        description="Archived message chains",
    ),
    CleanupRule(
        pattern=".workflow/history/**/*",
        lifetime=ArtifactLifetime.PERSISTENT,
        max_age_hours=168,  # 7 days
        description="Historical task summaries",
    ),
    CleanupRule(
        pattern=".board/archive/**/*",
        lifetime=ArtifactLifetime.PERSISTENT,
        max_age_hours=720,  # 30 days
        description="Archived board items",
    ),
    # Permanent files - never deleted
    CleanupRule(
        pattern=".workflow/audit/**/*",
        lifetime=ArtifactLifetime.PERMANENT,
        description="Audit trail and security logs",
    ),
    CleanupRule(
        pattern=".workflow/phases/**/*.json",
        lifetime=ArtifactLifetime.PERMANENT,
        description="Phase completion records",
    ),
]


class CleanupManager:
    """Manages artifact cleanup throughout workflow lifecycle."""

    def __init__(
        self,
        project_dir: Path,
        rules: Optional[list[CleanupRule]] = None,
        dry_run: bool = False,
    ):
        """Initialize cleanup manager.

        Args:
            project_dir: Project directory to manage
            rules: Custom cleanup rules (uses defaults if None)
            dry_run: If True, only simulate cleanup without deleting
        """
        self.project_dir = Path(project_dir)
        self.rules = rules or DEFAULT_CLEANUP_RULES.copy()
        self.dry_run = dry_run
        self._cleanup_log: list[CleanupResult] = []
        self._registered_temp_files: dict[str, set[str]] = {}  # task_id -> files
        self._registered_session_files: dict[str, set[str]] = {}  # task_id -> files

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        dirs = [
            self.project_dir / ".workflow" / "temp",
            self.project_dir / ".workflow" / "sessions",
            self.project_dir / ".workflow" / "history",
            self.project_dir / ".workflow" / "audit",
            self.project_dir / ".workflow" / "messages" / "inbox",
            self.project_dir / ".workflow" / "messages" / "processing",
            self.project_dir / ".workflow" / "messages" / "outbox",
            self.project_dir / ".workflow" / "messages" / "archive",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def get_temp_dir(self, task_id: str, agent_id: Optional[str] = None) -> Path:
        """Get a temporary directory for an agent execution.

        Args:
            task_id: Task identifier
            agent_id: Optional agent identifier for namespacing

        Returns:
            Path to temporary directory
        """
        self._ensure_directories()

        if agent_id:
            temp_dir = self.project_dir / ".workflow" / "temp" / task_id / agent_id
        else:
            temp_dir = self.project_dir / ".workflow" / "temp" / task_id

        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def get_session_dir(self, task_id: str) -> Path:
        """Get a session directory for task-scoped files.

        Args:
            task_id: Task identifier

        Returns:
            Path to session directory
        """
        self._ensure_directories()
        session_dir = self.project_dir / ".workflow" / "sessions" / task_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def register_temp_file(self, task_id: str, file_path: str) -> None:
        """Register a temporary file for cleanup after agent execution.

        Args:
            task_id: Task identifier
            file_path: Path to temporary file
        """
        if task_id not in self._registered_temp_files:
            self._registered_temp_files[task_id] = set()
        self._registered_temp_files[task_id].add(file_path)

    def register_session_file(self, task_id: str, file_path: str) -> None:
        """Register a session file for cleanup after task completion.

        Args:
            task_id: Task identifier
            file_path: Path to session file
        """
        if task_id not in self._registered_session_files:
            self._registered_session_files[task_id] = set()
        self._registered_session_files[task_id].add(file_path)

    def on_agent_complete(
        self,
        agent_id: str,
        task_id: str,
    ) -> CleanupResult:
        """Clean up after an agent execution completes.

        Removes TRANSIENT artifacts for the specific agent/task.

        Args:
            agent_id: Agent that completed
            task_id: Task that was executed

        Returns:
            CleanupResult with details of cleanup
        """
        result = CleanupResult()

        # Clean temp directory for this agent/task
        temp_dir = self.project_dir / ".workflow" / "temp" / task_id / agent_id
        if temp_dir.exists():
            result = self._delete_directory(temp_dir, result)

        # Clean registered temp files
        if task_id in self._registered_temp_files:
            for file_path in self._registered_temp_files[task_id].copy():
                path = Path(file_path)
                if path.exists():
                    result = self._delete_file(path, result)
            # Keep the set but clear files that were specific to this agent
            # (we might not know which agent registered which file)

        self._cleanup_log.append(result)
        logger.info(
            f"Agent complete cleanup for {agent_id}/{task_id}: "
            f"{result.total_deleted} items deleted, {result.bytes_freed} bytes freed"
        )
        return result

    def on_task_done(
        self,
        task_id: str,
        archive: bool = True,
    ) -> CleanupResult:
        """Clean up after a task is fully completed.

        Archives important data and removes SESSION artifacts.

        Args:
            task_id: Task that completed
            archive: Whether to archive before deleting

        Returns:
            CleanupResult with details of cleanup
        """
        result = CleanupResult()

        # Archive task summary if requested
        if archive:
            self._archive_task_summary(task_id)

        # Clean temp directory for entire task
        temp_dir = self.project_dir / ".workflow" / "temp" / task_id
        if temp_dir.exists():
            result = self._delete_directory(temp_dir, result)

        # Clean session directory
        session_dir = self.project_dir / ".workflow" / "sessions" / task_id
        if session_dir.exists():
            result = self._delete_directory(session_dir, result)

        # Clean registered session files
        if task_id in self._registered_session_files:
            for file_path in self._registered_session_files[task_id]:
                path = Path(file_path)
                if path.exists():
                    result = self._delete_file(path, result)
            del self._registered_session_files[task_id]

        # Clean up temp file registry
        if task_id in self._registered_temp_files:
            del self._registered_temp_files[task_id]

        self._cleanup_log.append(result)
        logger.info(
            f"Task done cleanup for {task_id}: "
            f"{result.total_deleted} items deleted, {result.bytes_freed} bytes freed"
        )
        return result

    def scheduled_cleanup(self) -> CleanupResult:
        """Run scheduled cleanup of old PERSISTENT artifacts.

        Should be run periodically (e.g., daily) to remove old files
        that have exceeded their retention period.

        Returns:
            CleanupResult with details of cleanup
        """
        result = CleanupResult()
        now = datetime.utcnow()

        for rule in self.rules:
            if rule.lifetime == ArtifactLifetime.PERSISTENT and rule.max_age_hours:
                max_age = timedelta(hours=rule.max_age_hours)
                pattern = str(self.project_dir / rule.pattern)

                for file_path in glob.glob(pattern, recursive=True):
                    path = Path(file_path)
                    if not path.exists() or not path.is_file():
                        continue

                    # Check file age
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if now - mtime > max_age:
                        result = self._delete_file(path, result)

        self._cleanup_log.append(result)
        logger.info(
            f"Scheduled cleanup: "
            f"{result.total_deleted} items deleted, {result.bytes_freed} bytes freed"
        )
        return result

    def cleanup_by_pattern(
        self,
        pattern: str,
        max_age_hours: Optional[int] = None,
    ) -> CleanupResult:
        """Clean up files matching a specific pattern.

        Args:
            pattern: Glob pattern relative to project directory
            max_age_hours: Only delete files older than this (optional)

        Returns:
            CleanupResult with details of cleanup
        """
        result = CleanupResult()
        now = datetime.utcnow()
        full_pattern = str(self.project_dir / pattern)

        for file_path in glob.glob(full_pattern, recursive=True):
            path = Path(file_path)
            if not path.exists():
                continue

            # Check age if specified
            if max_age_hours:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if now - mtime < timedelta(hours=max_age_hours):
                    continue

            if path.is_file():
                result = self._delete_file(path, result)
            elif path.is_dir():
                result = self._delete_directory(path, result)

        return result

    def _delete_file(self, path: Path, result: CleanupResult) -> CleanupResult:
        """Delete a single file.

        Args:
            path: File to delete
            result: Result to update

        Returns:
            Updated CleanupResult
        """
        try:
            if self.dry_run:
                logger.debug(f"[DRY RUN] Would delete file: {path}")
                result.files_deleted.append(str(path))
                result.bytes_freed += path.stat().st_size
            else:
                size = path.stat().st_size
                path.unlink()
                result.files_deleted.append(str(path))
                result.bytes_freed += size
                logger.debug(f"Deleted file: {path}")
        except Exception as e:
            result.errors.append(f"Failed to delete {path}: {e}")
            logger.warning(f"Failed to delete file {path}: {e}")
        return result

    def _delete_directory(self, path: Path, result: CleanupResult) -> CleanupResult:
        """Delete a directory and all contents.

        Args:
            path: Directory to delete
            result: Result to update

        Returns:
            Updated CleanupResult
        """
        try:
            if self.dry_run:
                logger.debug(f"[DRY RUN] Would delete directory: {path}")
                # Count contents for reporting
                for item in path.rglob("*"):
                    if item.is_file():
                        result.files_deleted.append(str(item))
                        result.bytes_freed += item.stat().st_size
                result.directories_deleted.append(str(path))
            else:
                # Calculate size before deleting
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                file_count = sum(1 for f in path.rglob("*") if f.is_file())

                shutil.rmtree(path)

                result.directories_deleted.append(str(path))
                result.files_deleted.extend([f"[{file_count} files in {path}]"])
                result.bytes_freed += size
                logger.debug(f"Deleted directory: {path} ({file_count} files, {size} bytes)")
        except Exception as e:
            result.errors.append(f"Failed to delete {path}: {e}")
            logger.warning(f"Failed to delete directory {path}: {e}")
        return result

    def _archive_task_summary(self, task_id: str) -> None:
        """Archive a task summary before cleanup.

        Args:
            task_id: Task to archive
        """
        import json

        session_dir = self.project_dir / ".workflow" / "sessions" / task_id
        history_dir = self.project_dir / ".workflow" / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        # Collect summary data
        summary = {
            "task_id": task_id,
            "archived_at": datetime.utcnow().isoformat(),
            "files_found": [],
        }

        if session_dir.exists():
            for f in session_dir.rglob("*.json"):
                try:
                    summary["files_found"].append(
                        {
                            "name": f.name,
                            "size": f.stat().st_size,
                        }
                    )
                except Exception:
                    pass

        # Write summary
        archive_file = history_dir / f"{task_id}.json"
        if not self.dry_run:
            archive_file.write_text(json.dumps(summary, indent=2))
            logger.debug(f"Archived task summary: {archive_file}")

    def get_cleanup_log(self) -> list[dict[str, Any]]:
        """Get the cleanup log.

        Returns:
            List of cleanup result dictionaries
        """
        return [r.to_dict() for r in self._cleanup_log]

    def get_disk_usage(self) -> dict[str, int]:
        """Get disk usage for workflow directories.

        Returns:
            Dictionary of directory -> bytes used
        """
        usage = {}
        workflow_dir = self.project_dir / ".workflow"

        if workflow_dir.exists():
            for subdir in ["temp", "sessions", "history", "audit", "messages", "phases"]:
                subdir_path = workflow_dir / subdir
                if subdir_path.exists():
                    total = sum(f.stat().st_size for f in subdir_path.rglob("*") if f.is_file())
                    usage[subdir] = total

        return usage

    def get_artifact_lifetime(self, file_path: Path) -> ArtifactLifetime:
        """Determine the lifetime category for a file.

        Args:
            file_path: Path to check

        Returns:
            ArtifactLifetime for the file
        """
        for rule in self.rules:
            if rule.matches(file_path, self.project_dir):
                return rule.lifetime

        # Default to SESSION if unknown
        return ArtifactLifetime.SESSION


async def cleanup_task_async(
    project_dir: Path,
    task_id: str,
) -> CleanupResult:
    """Async wrapper for task cleanup.

    Args:
        project_dir: Project directory
        task_id: Task to clean up

    Returns:
        CleanupResult
    """
    manager = CleanupManager(project_dir)
    return await asyncio.to_thread(manager.on_task_done, task_id)
