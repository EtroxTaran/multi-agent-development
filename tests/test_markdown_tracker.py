"""Tests for markdown task tracker.

Tests cover:
1. MarkdownTrackerConfig loading
2. MarkdownTracker initialization
3. Task file creation with YAML frontmatter
4. Task status updates with history
5. Read-only file enforcement
6. Checksum validation

Run with: pytest tests/test_markdown_tracker.py -v
"""

import json
import os
import stat
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.langgraph.state import TaskStatus


# =============================================================================
# Test MarkdownTrackerConfig
# =============================================================================

class TestMarkdownTrackerConfig:
    """Test markdown tracker configuration loading."""

    def test_default_config(self):
        """Test default configuration values."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            MarkdownTrackerConfig,
        )

        config = MarkdownTrackerConfig()

        assert config.enabled is True
        assert config.tasks_dir == "tasks"
        assert config.make_readonly is True
        assert config.validate_checksums is True

    def test_load_config_no_file(self, temp_project_dir):
        """Test loading when no config file exists."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            load_tracker_config,
        )

        config = load_tracker_config(temp_project_dir)

        assert config.enabled is True  # Default is enabled
        assert config.tasks_dir == "tasks"

    def test_load_config_with_tracking_section(self, temp_project_dir):
        """Test loading config with task_tracking section."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            load_tracker_config,
        )

        config_content = {
            "project_type": "node-api",
            "integrations": {
                "task_tracking": {
                    "enabled": True,
                    "tasks_dir": "custom_tasks",
                    "make_readonly": False,
                    "validate_checksums": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        config = load_tracker_config(temp_project_dir)

        assert config.enabled is True
        assert config.tasks_dir == "custom_tasks"
        assert config.make_readonly is False
        assert config.validate_checksums is False

    def test_load_config_disabled(self, temp_project_dir):
        """Test loading config with tracking disabled."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            load_tracker_config,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "enabled": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        config = load_tracker_config(temp_project_dir)

        assert config.enabled is False

    def test_load_config_invalid_json(self, temp_project_dir):
        """Test loading with invalid JSON returns defaults."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            load_tracker_config,
        )

        (temp_project_dir / ".project-config.json").write_text("invalid json")

        config = load_tracker_config(temp_project_dir)

        assert config.enabled is True  # Default


# =============================================================================
# Test MarkdownTracker Initialization
# =============================================================================

class TestMarkdownTrackerInit:
    """Test markdown tracker initialization."""

    def test_tracker_init(self, temp_project_dir):
        """Test tracker initialization."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            MarkdownTracker,
            MarkdownTrackerConfig,
        )

        config = MarkdownTrackerConfig()
        tracker = MarkdownTracker(temp_project_dir, config)

        assert tracker.enabled is True
        assert tracker.tasks_dir == temp_project_dir / ".workflow" / "tasks"

    def test_tracker_disabled(self, temp_project_dir):
        """Test tracker when disabled."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            MarkdownTracker,
            MarkdownTrackerConfig,
        )

        config = MarkdownTrackerConfig(enabled=False)
        tracker = MarkdownTracker(temp_project_dir, config)

        assert tracker.enabled is False

    def test_factory_function(self, temp_project_dir):
        """Test create_markdown_tracker factory."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        tracker = create_markdown_tracker(temp_project_dir)

        assert tracker.enabled is True


# =============================================================================
# Test Task File Creation
# =============================================================================

class TestTaskFileCreation:
    """Test creating task markdown files."""

    def test_create_single_task_file(self, temp_project_dir):
        """Test creating a single task file."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {
                "id": "T1",
                "title": "Implement feature",
                "status": TaskStatus.PENDING,
                "priority": "high",
                "user_story": "As a user, I want to do something",
                "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                "files_to_create": ["src/feature.py"],
                "files_to_modify": [],
                "test_files": ["tests/test_feature.py"],
                "dependencies": [],
            }
        ]

        result = tracker.create_task_files(tasks)

        assert "T1" in result
        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        assert task_file.exists()

    def test_task_file_frontmatter(self, temp_project_dir):
        """Test task file has correct YAML frontmatter."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        # Disable readonly for easier testing
        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {
                "id": "T1",
                "title": "Test task",
                "status": TaskStatus.PENDING,
                "priority": "medium",
                "user_story": "Test story",
                "acceptance_criteria": ["AC1"],
                "files_to_create": [],
                "files_to_modify": [],
                "test_files": [],
                "dependencies": ["T0"],
            }
        ]

        tracker.create_task_files(tasks)

        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        content = task_file.read_text()

        # Check frontmatter markers
        assert content.startswith("---")
        assert "id: T1" in content
        assert "title: Test task" in content
        assert "status: pending" in content
        assert "priority: medium" in content

    def test_task_file_body(self, temp_project_dir):
        """Test task file has correct markdown body."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {
                "id": "T1",
                "title": "Test task",
                "status": TaskStatus.PENDING,
                "priority": "high",
                "user_story": "As a user, I want this",
                "acceptance_criteria": ["Must do A", "Must do B"],
                "files_to_create": ["src/new.py"],
                "files_to_modify": ["src/old.py"],
                "test_files": ["tests/test.py"],
                "dependencies": [],
            }
        ]

        tracker.create_task_files(tasks)

        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        content = task_file.read_text()

        # Check body sections
        assert "# T1: Test task" in content
        assert "## User Story" in content
        assert "As a user, I want this" in content
        assert "## Acceptance Criteria" in content
        assert "- [ ] Must do A" in content
        assert "- [ ] Must do B" in content
        assert "### To Create" in content
        assert "`src/new.py`" in content
        assert "### To Modify" in content
        assert "`src/old.py`" in content
        assert "### Test Files" in content
        assert "`tests/test.py`" in content
        assert "## History" in content

    def test_create_multiple_task_files(self, temp_project_dir):
        """Test creating multiple task files."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
            {"id": "T2", "title": "Task 2", "status": TaskStatus.PENDING},
            {"id": "T3", "title": "Task 3", "status": TaskStatus.PENDING},
        ]

        result = tracker.create_task_files(tasks)

        assert len(result) == 3
        assert all(f.exists() for f in result.values())

    def test_create_task_with_linear_mapping(self, temp_project_dir):
        """Test creating task file with Linear issue ID."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        linear_mapping = {"T1": "LINEAR-123"}

        tracker.create_task_files(tasks, linear_mapping)

        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        content = task_file.read_text()

        assert "linear_issue_id: LINEAR-123" in content

    def test_create_task_disabled(self, temp_project_dir):
        """Test creating tasks when tracking is disabled."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "enabled": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]

        result = tracker.create_task_files(tasks)

        assert result == {}


# =============================================================================
# Test Status Updates
# =============================================================================

class TestStatusUpdates:
    """Test updating task status."""

    def test_update_status_to_in_progress(self, temp_project_dir):
        """Test updating status to in_progress."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        result = tracker.update_task_status("T1", TaskStatus.IN_PROGRESS)

        assert result is True

        # Check file content
        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        content = task_file.read_text()
        assert "status: in_progress" in content

    def test_update_status_adds_history(self, temp_project_dir):
        """Test updating status adds history entry."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        tracker.update_task_status("T1", TaskStatus.COMPLETED, "All done!")

        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        content = task_file.read_text()

        assert "Status changed to completed" in content
        assert "All done!" in content

    def test_update_status_nonexistent_task(self, temp_project_dir):
        """Test updating status for non-existent task."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        tracker = create_markdown_tracker(temp_project_dir)

        result = tracker.update_task_status("T999", TaskStatus.COMPLETED)

        assert result is False


# =============================================================================
# Test Read-Only Enforcement
# =============================================================================

class TestReadOnlyEnforcement:
    """Test read-only file permissions."""

    def test_files_are_readonly(self, temp_project_dir):
        """Test task files are made read-only."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        # Enable readonly
        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": True,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        file_stat = os.stat(task_file)
        mode = stat.S_IMODE(file_stat.st_mode)

        # Check read-only (444)
        assert mode == 0o444

    def test_status_update_with_readonly(self, temp_project_dir):
        """Test status update works with readonly files."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": True,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        # Should still be able to update
        result = tracker.update_task_status("T1", TaskStatus.COMPLETED)

        assert result is True

        # Should be readonly again
        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        file_stat = os.stat(task_file)
        mode = stat.S_IMODE(file_stat.st_mode)
        assert mode == 0o444


# =============================================================================
# Test Checksum Validation
# =============================================================================

class TestChecksumValidation:
    """Test checksum validation functionality."""

    def test_checksums_file_created(self, temp_project_dir):
        """Test checksums file is created."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        checksums_file = temp_project_dir / ".workflow" / "tasks" / ".task-checksums.json"
        assert checksums_file.exists()

        checksums = json.loads(checksums_file.read_text())
        assert "T1" in checksums
        assert len(checksums["T1"]) == 64  # SHA256 hex length

    def test_validate_integrity_unchanged(self, temp_project_dir):
        """Test validating unchanged task file."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        is_valid = tracker.validate_task_integrity("T1")

        assert is_valid is True

    def test_validate_integrity_modified(self, temp_project_dir):
        """Test detecting modified task file."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        # Manually modify file
        task_file = temp_project_dir / ".workflow" / "tasks" / "T1.md"
        task_file.write_text(task_file.read_text() + "\n# Modified!")

        is_valid = tracker.validate_task_integrity("T1")

        assert is_valid is False

    def test_read_task_validates_checksum(self, temp_project_dir):
        """Test read_task validates checksum when enabled."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )
        import logging

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                    "validate_checksums": True,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {"id": "T1", "title": "Task 1", "status": TaskStatus.PENDING},
        ]
        tracker.create_task_files(tasks)

        # Read should work
        task_data = tracker.read_task("T1")
        assert task_data is not None
        assert task_data["id"] == "T1"


# =============================================================================
# Test Reading Tasks
# =============================================================================

class TestReadTask:
    """Test reading task files."""

    def test_read_task(self, temp_project_dir):
        """Test reading a task file."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        config_content = {
            "integrations": {
                "task_tracking": {
                    "make_readonly": False,
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(
            json.dumps(config_content)
        )

        tracker = create_markdown_tracker(temp_project_dir)

        tasks = [
            {
                "id": "T1",
                "title": "Test task",
                "status": TaskStatus.PENDING,
                "priority": "high",
            },
        ]
        tracker.create_task_files(tasks)

        task_data = tracker.read_task("T1")

        assert task_data is not None
        assert task_data["id"] == "T1"
        assert task_data["title"] == "Test task"
        assert task_data["status"] == "pending"
        assert task_data["priority"] == "high"

    def test_read_nonexistent_task(self, temp_project_dir):
        """Test reading non-existent task."""
        from orchestrator.langgraph.integrations.markdown_tracker import (
            create_markdown_tracker,
        )

        tracker = create_markdown_tracker(temp_project_dir)

        task_data = tracker.read_task("T999")

        assert task_data is None


# =============================================================================
# Test Integration Exports
# =============================================================================

class TestIntegrationExports:
    """Test integrations __init__ exports."""

    def test_markdown_tracker_exports(self):
        """Test MarkdownTracker classes are exported from integrations."""
        from orchestrator.langgraph.integrations import (
            MarkdownTracker,
            MarkdownTrackerConfig,
            create_markdown_tracker,
            load_tracker_config,
        )

        # Just verify imports work
        assert MarkdownTracker is not None
        assert MarkdownTrackerConfig is not None
        assert create_markdown_tracker is not None
        assert load_tracker_config is not None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
