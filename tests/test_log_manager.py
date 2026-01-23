"""Tests for LogManager component."""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.log_manager import (
    CleanupResult,
    LogManager,
    LogRotationConfig,
    load_config,
    should_auto_cleanup,
)


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir) / ".workflow"
        workflow_dir.mkdir()
        yield workflow_dir


@pytest.fixture
def log_manager(temp_workflow_dir):
    """Create a log manager instance with small thresholds for testing."""
    config = LogRotationConfig(
        max_file_size_mb=0.001,  # 1KB for testing
        max_backup_count=3,
        max_age_days=1,
        archive_retention_days=7,
        compress_archives=True,
    )
    return LogManager(temp_workflow_dir, config)


class TestLogRotationConfig:
    """Tests for LogRotationConfig dataclass."""

    def test_default_values(self):
        config = LogRotationConfig()

        assert config.max_file_size_mb == 10.0
        assert config.max_backup_count == 5
        assert config.max_age_days == 7
        assert config.archive_retention_days == 30
        assert config.compress_archives is True

    def test_to_dict(self):
        config = LogRotationConfig(max_file_size_mb=5.0, max_backup_count=3)
        result = config.to_dict()

        assert result["max_file_size_mb"] == 5.0
        assert result["max_backup_count"] == 3

    def test_from_dict(self):
        data = {
            "max_file_size_mb": 5.0,
            "max_backup_count": 3,
        }
        config = LogRotationConfig.from_dict(data)

        assert config.max_file_size_mb == 5.0
        assert config.max_backup_count == 3
        # Defaults for missing values
        assert config.max_age_days == 7


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_to_dict(self):
        result = CleanupResult(
            rotated_files=["file1.log", "file2.log"],
            archived_files=["file1.log.gz"],
            deleted_files=["old.log.gz"],
            freed_bytes=1024 * 1024,
            errors=["Error 1"],
        )
        data = result.to_dict()

        assert len(data["rotated_files"]) == 2
        assert data["freed_mb"] == 1.0
        assert len(data["errors"]) == 1


class TestLogManager:
    """Tests for LogManager class."""

    def test_check_rotation_needed(self, temp_workflow_dir):
        """Test checking if rotation is needed."""
        # Create a log manager with 1KB threshold
        config = LogRotationConfig(max_file_size_mb=0.001)
        manager = LogManager(temp_workflow_dir, config)

        # Create a small file (under threshold)
        small_file = temp_workflow_dir / "coordination.log"
        small_file.write_text("small content")

        needs_rotation = manager.check_rotation_needed()
        assert needs_rotation["coordination.log"] is False

        # Create a larger file (over threshold)
        large_content = "x" * 2000  # 2KB
        small_file.write_text(large_content)

        needs_rotation = manager.check_rotation_needed()
        assert needs_rotation["coordination.log"] is True

    def test_rotate_if_needed(self, temp_workflow_dir):
        """Test rotating files when needed."""
        config = LogRotationConfig(max_file_size_mb=0.001, compress_archives=False)
        manager = LogManager(temp_workflow_dir, config)

        # Create oversized log file
        log_file = temp_workflow_dir / "coordination.log"
        log_file.write_text("x" * 2000)

        result = manager.rotate_if_needed()

        assert len(result.rotated_files) == 1
        assert (temp_workflow_dir / "coordination.log.1").exists()
        # New empty file created
        assert log_file.exists()
        assert log_file.stat().st_size == 0

    def test_rotate_with_compression(self, temp_workflow_dir):
        """Test rotation with compression enabled."""
        config = LogRotationConfig(max_file_size_mb=0.001, compress_archives=True)
        manager = LogManager(temp_workflow_dir, config)

        log_file = temp_workflow_dir / "coordination.log"
        log_file.write_text("x" * 2000)

        result = manager.rotate_if_needed()

        # Should have compressed the backup
        assert (temp_workflow_dir / "coordination.log.1.gz").exists()
        assert not (temp_workflow_dir / "coordination.log.1").exists()

    def test_rotate_shifts_backups(self, temp_workflow_dir):
        """Test that rotation shifts existing backups."""
        config = LogRotationConfig(
            max_file_size_mb=0.001,
            max_backup_count=3,
            compress_archives=False,
        )
        manager = LogManager(temp_workflow_dir, config)

        log_file = temp_workflow_dir / "coordination.log"

        # Create initial backups
        (temp_workflow_dir / "coordination.log.1").write_text("backup1")
        (temp_workflow_dir / "coordination.log.2").write_text("backup2")

        # Trigger rotation
        log_file.write_text("x" * 2000)
        manager.rotate_if_needed()

        # Backups should have shifted
        assert (temp_workflow_dir / "coordination.log.1").exists()
        assert (temp_workflow_dir / "coordination.log.2").read_text() == "backup1"
        assert (temp_workflow_dir / "coordination.log.3").read_text() == "backup2"

    def test_rotate_deletes_oldest(self, temp_workflow_dir):
        """Test that rotation deletes oldest backup when at max."""
        config = LogRotationConfig(
            max_file_size_mb=0.001,
            max_backup_count=2,
            compress_archives=False,
        )
        manager = LogManager(temp_workflow_dir, config)

        log_file = temp_workflow_dir / "coordination.log"

        # Create max backups
        (temp_workflow_dir / "coordination.log.1").write_text("backup1")
        (temp_workflow_dir / "coordination.log.2").write_text("oldest")

        # Trigger rotation
        log_file.write_text("x" * 2000)
        result = manager.rotate_if_needed()

        # Oldest should be deleted
        assert not (temp_workflow_dir / "coordination.log.3").exists()
        assert len(result.deleted_files) == 1

    def test_cleanup_dry_run(self, temp_workflow_dir):
        """Test cleanup in dry run mode."""
        config = LogRotationConfig(max_file_size_mb=0.001)
        manager = LogManager(temp_workflow_dir, config)

        # Create oversized log
        log_file = temp_workflow_dir / "coordination.log"
        original_content = "x" * 2000
        log_file.write_text(original_content)

        result = manager.cleanup(dry_run=True)

        # Should report what would be done
        assert len(result.rotated_files) == 1

        # But file should be unchanged
        assert log_file.read_text() == original_content

    def test_cleanup_full(self, temp_workflow_dir):
        """Test full cleanup operation."""
        config = LogRotationConfig(
            max_file_size_mb=0.001,
            max_age_days=0,  # Archive everything
            compress_archives=True,
        )
        manager = LogManager(temp_workflow_dir, config)

        # Create oversized log
        log_file = temp_workflow_dir / "coordination.log"
        log_file.write_text("x" * 2000)

        # Create traces directory with old file
        traces_dir = temp_workflow_dir / "traces"
        traces_dir.mkdir()
        old_trace = traces_dir / "trace.json"
        old_trace.write_text("{}")

        result = manager.cleanup()

        # Should rotate log
        assert len(result.rotated_files) >= 1

        # Should archive old trace
        assert len(result.archived_files) >= 1

    def test_get_log_stats(self, temp_workflow_dir):
        """Test getting log statistics."""
        config = LogRotationConfig(max_file_size_mb=0.001)
        manager = LogManager(temp_workflow_dir, config)

        # Create some log files with enough content to register size
        (temp_workflow_dir / "coordination.log").write_text("log content " * 1000)
        (temp_workflow_dir / "coordination.jsonl").write_text('{"key": "value"}\n' * 100)
        (temp_workflow_dir / "action_log.jsonl").write_text('{"action": "test"}\n' * 100)

        # Create archive
        (temp_workflow_dir / "coordination.log.1.gz").write_bytes(b"compressed" * 100)

        stats = manager.get_log_stats()

        assert stats["total_size_mb"] >= 0  # May be 0 for small files, just check it exists
        assert "coordination.log" in stats["files"]
        assert stats["archive_count"] >= 1

    def test_get_log_stats_needs_rotation(self, temp_workflow_dir):
        """Test that stats report files needing rotation."""
        config = LogRotationConfig(max_file_size_mb=0.001)
        manager = LogManager(temp_workflow_dir, config)

        # Create oversized log
        (temp_workflow_dir / "coordination.log").write_text("x" * 2000)

        stats = manager.get_log_stats()

        assert "coordination.log" in stats["needs_rotation"]


class TestConfigLoading:
    """Tests for config loading functions."""

    def test_load_config_default(self, temp_workflow_dir):
        """Test loading config when no file exists."""
        config = load_config(temp_workflow_dir)

        # Should return defaults
        assert config.max_file_size_mb == 10.0
        assert config.max_backup_count == 5

    def test_load_config_from_file(self, temp_workflow_dir):
        """Test loading config from file."""
        config_data = {
            "log_management": {
                "max_log_size_mb": 5.0,
                "max_backup_count": 3,
                "archive_after_days": 14,
                "delete_archives_after_days": 60,
                "compress_archives": False,
            }
        }
        config_file = temp_workflow_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        config = load_config(temp_workflow_dir)

        assert config.max_file_size_mb == 5.0
        assert config.max_backup_count == 3
        assert config.max_age_days == 14
        assert config.archive_retention_days == 60
        assert config.compress_archives is False

    def test_should_auto_cleanup_default(self, temp_workflow_dir):
        """Test auto cleanup default."""
        # Default should be enabled
        assert should_auto_cleanup(temp_workflow_dir) is True

    def test_should_auto_cleanup_from_config(self, temp_workflow_dir):
        """Test auto cleanup from config file."""
        config_data = {
            "log_management": {
                "auto_cleanup_on_start": False,
            }
        }
        config_file = temp_workflow_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        assert should_auto_cleanup(temp_workflow_dir) is False

    def test_load_config_invalid_json(self, temp_workflow_dir):
        """Test loading config with invalid JSON."""
        config_file = temp_workflow_dir / "config.json"
        config_file.write_text("invalid json {")

        # Should return defaults without error
        config = load_config(temp_workflow_dir)
        assert config.max_file_size_mb == 10.0
