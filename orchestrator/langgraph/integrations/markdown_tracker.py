"""Local markdown task tracker.

Provides local task tracking using markdown files with YAML frontmatter:
- Task files stored in .workflow/tasks/
- Read-only file permissions (chmod 444)
- SHA256 checksum validation
- Status updates with history logging

Works identically whether Linear integration is enabled or not.
"""

import hashlib
import json
import logging
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import Task, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class MarkdownTrackerConfig:
    """Configuration for markdown task tracker.

    Attributes:
        enabled: Whether task tracking is enabled
        tasks_dir: Directory for task files relative to .workflow/
        make_readonly: Whether to set files as read-only (chmod 444)
        validate_checksums: Whether to validate file checksums on read
    """

    enabled: bool = True
    tasks_dir: str = "tasks"
    make_readonly: bool = True
    validate_checksums: bool = True


# Default configuration
DEFAULT_CONFIG = MarkdownTrackerConfig()


def load_tracker_config(project_dir: Path) -> MarkdownTrackerConfig:
    """Load markdown tracker configuration from project config.

    Args:
        project_dir: Project directory path

    Returns:
        MarkdownTrackerConfig instance
    """
    config_path = project_dir / ".project-config.json"
    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        config = json.loads(config_path.read_text())
        integrations = config.get("integrations", {})
        task_tracking = integrations.get("task_tracking", {})

        return MarkdownTrackerConfig(
            enabled=task_tracking.get("enabled", True),
            tasks_dir=task_tracking.get("tasks_dir", "tasks"),
            make_readonly=task_tracking.get("make_readonly", True),
            validate_checksums=task_tracking.get("validate_checksums", True),
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not load task tracking config: {e}")
        return DEFAULT_CONFIG


class MarkdownTracker:
    """Local markdown task tracker.

    Creates and manages task files in .workflow/tasks/ with:
    - YAML frontmatter for metadata
    - Markdown body for human-readable content
    - Read-only permissions to prevent accidental modification
    - SHA256 checksum validation
    """

    def __init__(self, project_dir: Path, config: MarkdownTrackerConfig):
        """Initialize markdown tracker.

        Args:
            project_dir: Project directory path
            config: Tracker configuration
        """
        self.project_dir = project_dir
        self.config = config
        self._tasks_dir = project_dir / ".workflow" / config.tasks_dir
        self._checksums_file = self._tasks_dir / ".task-checksums.json"
        self._checksums: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        """Check if task tracking is enabled."""
        return self.config.enabled

    @property
    def tasks_dir(self) -> Path:
        """Get the tasks directory path."""
        return self._tasks_dir

    def create_task_files(
        self,
        tasks: list[Task],
        linear_mapping: Optional[dict[str, str]] = None,
    ) -> dict[str, Path]:
        """Create markdown task files from tasks.

        Args:
            tasks: List of tasks to create files for
            linear_mapping: Optional mapping of task_id -> linear_issue_id

        Returns:
            Dict mapping task_id to file path
        """
        if not self.enabled:
            logger.debug("Task tracking disabled, skipping file creation")
            return {}

        # Ensure tasks directory exists
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

        # Load existing checksums
        self._load_checksums()

        results: dict[str, Path] = {}
        linear_mapping = linear_mapping or {}

        for task in tasks:
            try:
                task_id = task.get("id", "")
                if not task_id:
                    logger.warning("Task missing ID, skipping")
                    continue

                file_path = self._create_task_file(task, linear_mapping.get(task_id))
                if file_path:
                    results[task_id] = file_path

            except Exception as e:
                logger.warning(f"Failed to create task file for {task.get('id')}: {e}")

        # Save checksums
        self._save_checksums()

        logger.info(f"Created {len(results)} task files in {self._tasks_dir}")
        return results

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        notes: Optional[str] = None,
    ) -> bool:
        """Update task status in markdown file.

        Adds a history entry and updates the frontmatter status.

        Args:
            task_id: Task ID
            status: New status
            notes: Optional notes to add

        Returns:
            True if update successful
        """
        if not self.enabled:
            return True

        file_path = self._tasks_dir / f"{task_id}.md"
        if not file_path.exists():
            logger.warning(f"Task file not found: {file_path}")
            return False

        try:
            # Make file writable temporarily
            self._make_writable(file_path)

            # Read current content
            content = file_path.read_text()

            # Parse and update
            frontmatter, body = self._parse_frontmatter(content)

            status_value = status.value if isinstance(status, TaskStatus) else status
            frontmatter["status"] = status_value
            frontmatter["updated_at"] = datetime.now().isoformat()

            # Add history entry
            timestamp = datetime.now().isoformat()
            history_entry = f"- {timestamp} - Status changed to {status_value}"
            if notes:
                history_entry += f": {notes}"

            # Append to history section
            body = self._append_to_history(body, history_entry)

            # Write updated content
            new_content = self._format_frontmatter(frontmatter) + body
            file_path.write_text(new_content)

            # Update checksum
            self._update_checksum(task_id, new_content)

            # Restore read-only
            if self.config.make_readonly:
                self._make_readonly(file_path)

            logger.debug(f"Updated task {task_id} status to {status_value}")
            return True

        except Exception as e:
            logger.error(f"Failed to update task {task_id} status: {e}")
            return False

    def read_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read task from markdown file.

        Args:
            task_id: Task ID

        Returns:
            Task data dict or None if not found
        """
        file_path = self._tasks_dir / f"{task_id}.md"
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text()

            # Validate checksum if enabled
            if self.config.validate_checksums:
                if not self._validate_checksum(task_id, content):
                    logger.warning(f"Checksum validation failed for task {task_id}")

            frontmatter, body = self._parse_frontmatter(content)
            return {
                **frontmatter,
                "body": body,
            }

        except Exception as e:
            logger.error(f"Failed to read task {task_id}: {e}")
            return None

    def validate_task_integrity(self, task_id: str) -> bool:
        """Validate task file integrity using checksum.

        Args:
            task_id: Task ID

        Returns:
            True if file is unchanged, False if modified
        """
        file_path = self._tasks_dir / f"{task_id}.md"
        if not file_path.exists():
            return False

        try:
            content = file_path.read_text()
            return self._validate_checksum(task_id, content)
        except Exception:
            return False

    def _create_task_file(
        self,
        task: Task,
        linear_issue_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Create a single task file.

        Args:
            task: Task data
            linear_issue_id: Optional Linear issue ID

        Returns:
            Path to created file or None
        """
        task_id = task["id"]
        file_path = self._tasks_dir / f"{task_id}.md"

        # Build frontmatter
        now = datetime.now().isoformat()
        frontmatter = {
            "id": task_id,
            "title": task.get("title", ""),
            "status": task.get("status", TaskStatus.PENDING).value if isinstance(task.get("status"), TaskStatus) else task.get("status", "pending"),
            "priority": task.get("priority", "medium"),
            "linear_issue_id": linear_issue_id,
            "dependencies": task.get("dependencies", []),
            "milestone_id": task.get("milestone_id"),
            "created_at": now,
            "updated_at": now,
        }

        # Build body
        body = self._format_task_body(task)

        # Combine
        content = self._format_frontmatter(frontmatter) + body

        # Write file
        file_path.write_text(content)

        # Calculate and store checksum
        self._update_checksum(task_id, content)

        # Make read-only if configured
        if self.config.make_readonly:
            self._make_readonly(file_path)

        logger.debug(f"Created task file: {file_path}")
        return file_path

    def _format_task_body(self, task: Task) -> str:
        """Format task body as markdown.

        Args:
            task: Task data

        Returns:
            Markdown body string
        """
        task_id = task.get("id", "")
        title = task.get("title", "Untitled")
        user_story = task.get("user_story", "")
        acceptance_criteria = task.get("acceptance_criteria", [])
        files_to_create = task.get("files_to_create", [])
        files_to_modify = task.get("files_to_modify", [])
        test_files = task.get("test_files", [])

        lines = [
            f"# {task_id}: {title}",
            "",
            "## User Story",
            user_story or "_No user story defined_",
            "",
            "## Acceptance Criteria",
        ]

        if acceptance_criteria:
            for criterion in acceptance_criteria:
                lines.append(f"- [ ] {criterion}")
        else:
            lines.append("_No acceptance criteria defined_")

        lines.extend([
            "",
            "## Files",
            "",
            "### To Create",
        ])

        if files_to_create:
            for f in files_to_create:
                lines.append(f"- `{f}`")
        else:
            lines.append("- None")

        lines.extend([
            "",
            "### To Modify",
        ])

        if files_to_modify:
            for f in files_to_modify:
                lines.append(f"- `{f}`")
        else:
            lines.append("- None")

        lines.extend([
            "",
            "### Test Files",
        ])

        if test_files:
            for f in test_files:
                lines.append(f"- `{f}`")
        else:
            lines.append("- None")

        lines.extend([
            "",
            "## Implementation Notes",
            "<!-- Updated after completion -->",
            "",
            "## History",
            f"- {datetime.now().isoformat()} - Task created",
        ])

        return "\n".join(lines) + "\n"

    def _format_frontmatter(self, data: dict[str, Any]) -> str:
        """Format frontmatter as YAML.

        Args:
            data: Frontmatter data

        Returns:
            YAML frontmatter string with delimiters
        """
        lines = ["---"]

        for key, value in data.items():
            if value is None:
                lines.append(f"{key}: null")
            elif isinstance(value, bool):
                lines.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, list):
                if not value:
                    lines.append(f"{key}: []")
                else:
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - \"{item}\"")
            elif isinstance(value, str):
                # Quote strings with special characters
                if any(c in value for c in ":#{}[]&*!|>'\"%@`"):
                    lines.append(f'{key}: "{value}"')
                else:
                    lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {value}")

        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content.

        Args:
            content: Full markdown content

        Returns:
            Tuple of (frontmatter dict, body string)
        """
        if not content.startswith("---"):
            return {}, content

        # Find end delimiter
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return {}, content

        frontmatter_text = content[3:end_idx].strip()
        body = content[end_idx + 3:].lstrip("\n")

        # Simple YAML parsing (handles our limited format)
        frontmatter: dict[str, Any] = {}
        current_key = None
        current_list: list[str] = []

        for line in frontmatter_text.split("\n"):
            line = line.rstrip()

            # Check for list item
            if line.startswith("  - "):
                if current_key:
                    item = line[4:].strip().strip('"')
                    current_list.append(item)
                continue

            # Save previous list
            if current_key and current_list:
                frontmatter[current_key] = current_list
                current_list = []
                current_key = None

            # Parse key: value
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if value == "":
                    # Might be a list
                    current_key = key
                elif value == "[]":
                    frontmatter[key] = []
                elif value == "null":
                    frontmatter[key] = None
                elif value == "true":
                    frontmatter[key] = True
                elif value == "false":
                    frontmatter[key] = False
                elif value.startswith('"') and value.endswith('"'):
                    frontmatter[key] = value[1:-1]
                else:
                    frontmatter[key] = value

        # Handle final list
        if current_key and current_list:
            frontmatter[current_key] = current_list

        return frontmatter, body

    def _append_to_history(self, body: str, entry: str) -> str:
        """Append entry to history section.

        Args:
            body: Markdown body
            entry: History entry to append

        Returns:
            Updated body
        """
        # Find history section
        history_marker = "## History"
        if history_marker in body:
            # Insert after the marker line
            parts = body.split(history_marker, 1)
            return parts[0] + history_marker + parts[1].rstrip() + "\n" + entry + "\n"
        else:
            # Add history section
            return body.rstrip() + f"\n\n{history_marker}\n{entry}\n"

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of content.

        Args:
            content: File content

        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def _load_checksums(self) -> None:
        """Load checksums from file."""
        if self._checksums_file.exists():
            try:
                self._checksums = json.loads(self._checksums_file.read_text())
            except json.JSONDecodeError:
                self._checksums = {}
        else:
            self._checksums = {}

    def _save_checksums(self) -> None:
        """Save checksums to file."""
        self._checksums_file.write_text(json.dumps(self._checksums, indent=2))

    def _update_checksum(self, task_id: str, content: str) -> None:
        """Update checksum for a task.

        Args:
            task_id: Task ID
            content: File content
        """
        self._checksums[task_id] = self._calculate_checksum(content)

    def _validate_checksum(self, task_id: str, content: str) -> bool:
        """Validate content against stored checksum.

        Args:
            task_id: Task ID
            content: Current file content

        Returns:
            True if checksum matches
        """
        self._load_checksums()
        stored = self._checksums.get(task_id)
        if not stored:
            return True  # No checksum stored, consider valid

        return self._calculate_checksum(content) == stored

    def _make_readonly(self, path: Path) -> None:
        """Make file read-only (chmod 444).

        Args:
            path: File path
        """
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as e:
            logger.warning(f"Could not set read-only: {e}")

    def _make_writable(self, path: Path) -> None:
        """Make file writable (chmod 644).

        Args:
            path: File path
        """
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as e:
            logger.warning(f"Could not set writable: {e}")


def create_markdown_tracker(project_dir: Path) -> MarkdownTracker:
    """Factory function to create a markdown tracker.

    Args:
        project_dir: Project directory path

    Returns:
        Configured MarkdownTracker instance
    """
    config = load_tracker_config(project_dir)
    return MarkdownTracker(project_dir, config)
