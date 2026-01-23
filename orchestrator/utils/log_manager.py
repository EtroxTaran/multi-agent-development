"""Log manager for rotation and cleanup.

Handles log lifecycle to prevent unbounded growth, including
rotation by size, archival by age, and compression.
"""

import gzip
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class LogRotationConfig:
    """Configuration for log rotation."""

    max_file_size_mb: float = 10.0  # Rotate when file exceeds this size
    max_backup_count: int = 5  # Number of backup files to keep
    max_age_days: int = 7  # Archive files older than this
    archive_retention_days: int = 30  # Delete archives older than this
    compress_archives: bool = True  # gzip old logs

    def to_dict(self) -> dict:
        return {
            "max_file_size_mb": self.max_file_size_mb,
            "max_backup_count": self.max_backup_count,
            "max_age_days": self.max_age_days,
            "archive_retention_days": self.archive_retention_days,
            "compress_archives": self.compress_archives,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogRotationConfig":
        return cls(
            max_file_size_mb=data.get("max_file_size_mb", 10.0),
            max_backup_count=data.get("max_backup_count", 5),
            max_age_days=data.get("max_age_days", 7),
            archive_retention_days=data.get("archive_retention_days", 30),
            compress_archives=data.get("compress_archives", True),
        )


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    rotated_files: list[str] = field(default_factory=list)
    archived_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    freed_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rotated_files": self.rotated_files,
            "archived_files": self.archived_files,
            "deleted_files": self.deleted_files,
            "freed_bytes": self.freed_bytes,
            "freed_mb": round(self.freed_bytes / (1024 * 1024), 2),
            "errors": self.errors,
        }


class LogManager:
    """Manages log lifecycle including rotation, archival, and cleanup.

    Supports multiple log file types commonly found in the workflow:
    - coordination.log (plain text)
    - coordination.jsonl (JSON lines)
    - action_log.jsonl (JSON lines)
    - traces/*.json (trace files)
    - errors/*.jsonl (error logs)
    """

    # Files to manage with their rotation settings
    MANAGED_FILES = [
        "coordination.log",
        "coordination.jsonl",
        "action_log.jsonl",
    ]

    MANAGED_DIRS = [
        "traces",
        "errors",
    ]

    def __init__(
        self,
        workflow_dir: str | Path,
        config: Optional[LogRotationConfig] = None,
    ):
        """Initialize the log manager.

        Args:
            workflow_dir: Directory containing log files
            config: Rotation configuration (uses defaults if not provided)
        """
        self.workflow_dir = Path(workflow_dir)
        self.config = config or LogRotationConfig()
        self.archive_dir = self.workflow_dir / "archives"

    def _get_file_size_mb(self, path: Path) -> float:
        """Get file size in megabytes."""
        if not path.exists():
            return 0.0
        return path.stat().st_size / (1024 * 1024)

    def _get_file_age_days(self, path: Path) -> float:
        """Get file age in days."""
        if not path.exists():
            return 0.0
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return (datetime.now() - mtime).total_seconds() / 86400

    def _rotate_file(self, file_path: Path, result: CleanupResult) -> None:
        """Rotate a single file.

        Shifts existing backups and creates a new backup:
        file.log → file.log.1 → file.log.2 → ... → file.log.N (deleted)
        """
        if not file_path.exists():
            return

        try:
            # Shift existing backups
            for i in range(self.config.max_backup_count, 0, -1):
                old_backup = file_path.with_suffix(f"{file_path.suffix}.{i}")
                new_backup = file_path.with_suffix(f"{file_path.suffix}.{i + 1}")

                if i == self.config.max_backup_count:
                    # Delete oldest backup
                    if old_backup.exists():
                        old_size = old_backup.stat().st_size
                        old_backup.unlink()
                        result.deleted_files.append(str(old_backup))
                        result.freed_bytes += old_size
                else:
                    # Shift backup
                    if old_backup.exists():
                        shutil.move(str(old_backup), str(new_backup))

            # Also handle compressed backups
            for i in range(self.config.max_backup_count, 0, -1):
                old_backup = file_path.with_suffix(f"{file_path.suffix}.{i}.gz")
                new_backup = file_path.with_suffix(f"{file_path.suffix}.{i + 1}.gz")

                if i == self.config.max_backup_count:
                    if old_backup.exists():
                        old_size = old_backup.stat().st_size
                        old_backup.unlink()
                        result.deleted_files.append(str(old_backup))
                        result.freed_bytes += old_size
                else:
                    if old_backup.exists():
                        shutil.move(str(old_backup), str(new_backup))

            # Move current file to .1
            backup_path = file_path.with_suffix(f"{file_path.suffix}.1")
            shutil.move(str(file_path), str(backup_path))
            result.rotated_files.append(str(file_path))

            # Compress if enabled
            if self.config.compress_archives:
                self._compress_file(backup_path, result)

            # Create empty new file
            file_path.touch()

        except Exception as e:
            result.errors.append(f"Error rotating {file_path}: {e}")

    def _compress_file(self, file_path: Path, result: CleanupResult) -> None:
        """Compress a file using gzip."""
        if not file_path.exists():
            return

        compressed_path = file_path.with_suffix(file_path.suffix + ".gz")

        try:
            original_size = file_path.stat().st_size

            with open(file_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove original
            file_path.unlink()

            compressed_size = compressed_path.stat().st_size
            result.freed_bytes += original_size - compressed_size
            result.archived_files.append(str(compressed_path))

        except Exception as e:
            result.errors.append(f"Error compressing {file_path}: {e}")

    def _archive_old_files(self, directory: Path, result: CleanupResult) -> None:
        """Archive old files in a directory."""
        if not directory.exists():
            return

        cutoff_date = datetime.now() - timedelta(days=self.config.max_age_days)

        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue

            # Skip already compressed files
            if file_path.suffix == ".gz":
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_date:
                    if self.config.compress_archives:
                        self._compress_file(file_path, result)
                    else:
                        # Just move to archives
                        self.archive_dir.mkdir(parents=True, exist_ok=True)
                        archive_path = self.archive_dir / file_path.name
                        shutil.move(str(file_path), str(archive_path))
                        result.archived_files.append(str(archive_path))

            except Exception as e:
                result.errors.append(f"Error archiving {file_path}: {e}")

    def _delete_old_archives(self, result: CleanupResult) -> None:
        """Delete archives older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.config.archive_retention_days)

        # Check main workflow directory for old compressed backups
        for file_path in self.workflow_dir.glob("*.gz"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_date:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    result.deleted_files.append(str(file_path))
                    result.freed_bytes += file_size
            except Exception as e:
                result.errors.append(f"Error deleting {file_path}: {e}")

        # Check archives directory
        if self.archive_dir.exists():
            for file_path in self.archive_dir.iterdir():
                if not file_path.is_file():
                    continue

                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_date:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        result.deleted_files.append(str(file_path))
                        result.freed_bytes += file_size
                except Exception as e:
                    result.errors.append(f"Error deleting {file_path}: {e}")

        # Check managed directories
        for dir_name in self.MANAGED_DIRS:
            dir_path = self.workflow_dir / dir_name
            if not dir_path.exists():
                continue

            for file_path in dir_path.glob("*.gz"):
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_date:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        result.deleted_files.append(str(file_path))
                        result.freed_bytes += file_size
                except Exception as e:
                    result.errors.append(f"Error deleting {file_path}: {e}")

    def check_rotation_needed(self) -> dict[str, bool]:
        """Check which files need rotation.

        Returns:
            Dictionary mapping file names to whether they need rotation
        """
        needs_rotation = {}

        for file_name in self.MANAGED_FILES:
            file_path = self.workflow_dir / file_name
            size_mb = self._get_file_size_mb(file_path)
            needs_rotation[file_name] = size_mb >= self.config.max_file_size_mb

        return needs_rotation

    def rotate_if_needed(self) -> CleanupResult:
        """Rotate files that exceed size threshold.

        Returns:
            CleanupResult with details of what was done
        """
        result = CleanupResult()

        for file_name in self.MANAGED_FILES:
            file_path = self.workflow_dir / file_name
            size_mb = self._get_file_size_mb(file_path)

            if size_mb >= self.config.max_file_size_mb:
                self._rotate_file(file_path, result)

        return result

    def cleanup(self, dry_run: bool = False) -> CleanupResult:
        """Perform full cleanup operation.

        Args:
            dry_run: If True, report what would be done without doing it

        Returns:
            CleanupResult with details of what was done (or would be done)
        """
        result = CleanupResult()

        if dry_run:
            # Just report what would be done
            for file_name in self.MANAGED_FILES:
                file_path = self.workflow_dir / file_name
                size_mb = self._get_file_size_mb(file_path)
                if size_mb >= self.config.max_file_size_mb:
                    result.rotated_files.append(f"{file_path} ({size_mb:.2f} MB)")

            cutoff_date = datetime.now() - timedelta(days=self.config.max_age_days)
            archive_cutoff = datetime.now() - timedelta(days=self.config.archive_retention_days)

            for dir_name in self.MANAGED_DIRS:
                dir_path = self.workflow_dir / dir_name
                if not dir_path.exists():
                    continue

                for file_path in dir_path.iterdir():
                    if not file_path.is_file():
                        continue
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_date:
                        result.archived_files.append(str(file_path))
                    if file_path.suffix == ".gz" and mtime < archive_cutoff:
                        result.deleted_files.append(str(file_path))
                        result.freed_bytes += file_path.stat().st_size

            return result

        # Actually perform cleanup

        # 1. Rotate oversized files
        for file_name in self.MANAGED_FILES:
            file_path = self.workflow_dir / file_name
            size_mb = self._get_file_size_mb(file_path)
            if size_mb >= self.config.max_file_size_mb:
                self._rotate_file(file_path, result)

        # 2. Archive old files in managed directories
        for dir_name in self.MANAGED_DIRS:
            dir_path = self.workflow_dir / dir_name
            self._archive_old_files(dir_path, result)

        # 3. Delete old archives
        self._delete_old_archives(result)

        return result

    def get_log_stats(self) -> dict:
        """Get statistics about log files.

        Returns:
            Dictionary with log statistics
        """
        stats = {
            "total_size_mb": 0.0,
            "files": {},
            "needs_rotation": [],
            "archive_count": 0,
        }

        # Check managed files
        for file_name in self.MANAGED_FILES:
            file_path = self.workflow_dir / file_name
            size_mb = self._get_file_size_mb(file_path)
            stats["files"][file_name] = {
                "exists": file_path.exists(),
                "size_mb": round(size_mb, 2),
                "age_days": round(self._get_file_age_days(file_path), 1),
            }
            stats["total_size_mb"] += size_mb

            if size_mb >= self.config.max_file_size_mb:
                stats["needs_rotation"].append(file_name)

        # Check managed directories
        for dir_name in self.MANAGED_DIRS:
            dir_path = self.workflow_dir / dir_name
            if dir_path.exists():
                dir_size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                dir_size_mb = dir_size / (1024 * 1024)
                stats["files"][dir_name] = {
                    "exists": True,
                    "size_mb": round(dir_size_mb, 2),
                    "file_count": len(list(dir_path.rglob("*"))),
                }
                stats["total_size_mb"] += dir_size_mb

        # Count archives
        for ext in ["*.gz", "*.1", "*.2", "*.3", "*.4", "*.5"]:
            stats["archive_count"] += len(list(self.workflow_dir.glob(ext)))

        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        return stats


def load_config(workflow_dir: Path) -> LogRotationConfig:
    """Load log rotation config from workflow config file.

    Args:
        workflow_dir: Workflow directory

    Returns:
        LogRotationConfig loaded from config or defaults
    """
    config_file = workflow_dir / "config.json"

    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
                log_config = data.get("log_management", {})
                return LogRotationConfig(
                    max_file_size_mb=log_config.get("max_log_size_mb", 10.0),
                    max_backup_count=log_config.get("max_backup_count", 5),
                    max_age_days=log_config.get("archive_after_days", 7),
                    archive_retention_days=log_config.get("delete_archives_after_days", 30),
                    compress_archives=log_config.get("compress_archives", True),
                )
        except (OSError, json.JSONDecodeError):
            pass

    return LogRotationConfig()


def should_auto_cleanup(workflow_dir: Path) -> bool:
    """Check if auto cleanup is enabled in config.

    Args:
        workflow_dir: Workflow directory

    Returns:
        True if auto cleanup is enabled
    """
    config_file = workflow_dir / "config.json"

    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("log_management", {}).get("auto_cleanup_on_start", True)
        except (OSError, json.JSONDecodeError):
            pass

    return True  # Default to enabled
