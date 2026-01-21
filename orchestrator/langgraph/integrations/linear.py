"""Linear integration adapter.

Provides optional integration with Linear issue tracking:
- Create issues from tasks
- Update issue status when task status changes
- Add blocker comments

Uses the official Linear MCP (https://mcp.linear.app/mcp) with graceful degradation.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..state import Task, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class LinearConfig:
    """Configuration for Linear integration.

    Attributes:
        enabled: Whether Linear integration is enabled
        team_id: Linear team ID (required if enabled)
        create_project: Whether to create a Linear project for the feature
        status_mapping: Map TaskStatus to Linear workflow states
        project_id: Optional existing project ID to use
    """

    enabled: bool = False
    team_id: Optional[str] = None
    create_project: bool = True
    project_id: Optional[str] = None
    status_mapping: dict[str, str] = field(default_factory=lambda: {
        "pending": "Backlog",
        "in_progress": "In Progress",
        "completed": "Done",
        "blocked": "Blocked",
        "failed": "Cancelled",
    })


# Default status mapping used when not specified in config
DEFAULT_STATUS_MAPPING = {
    "pending": "Backlog",
    "in_progress": "In Progress",
    "completed": "Done",
    "blocked": "Blocked",
    "failed": "Cancelled",
}


def load_linear_config(project_dir: Path) -> LinearConfig:
    """Load Linear configuration from project config.

    Args:
        project_dir: Project directory path

    Returns:
        LinearConfig instance
    """
    config_path = project_dir / ".project-config.json"
    if not config_path.exists():
        return LinearConfig()

    try:
        config = json.loads(config_path.read_text())
        integrations = config.get("integrations", {})
        linear = integrations.get("linear", {})

        return LinearConfig(
            enabled=linear.get("enabled", False),
            team_id=linear.get("team_id"),
            create_project=linear.get("create_project", True),
            project_id=linear.get("project_id"),
            status_mapping=linear.get("status_mapping", DEFAULT_STATUS_MAPPING),
        )

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not load Linear config: {e}")
        return LinearConfig()


class LinearAdapter:
    """Adapter for Linear MCP integration.

    Wraps the official Linear MCP with graceful degradation
    when integration is not available or configured.

    This adapter is designed to be called from workflow nodes
    without requiring async/await at the call site.
    """

    def __init__(self, config: LinearConfig):
        """Initialize Linear adapter.

        Args:
            config: Linear configuration
        """
        self.config = config
        self._mcp_available: Optional[bool] = None
        self._issue_cache: dict[str, str] = {}  # task_id -> linear_issue_id

    @property
    def enabled(self) -> bool:
        """Check if Linear integration is enabled and configured."""
        return self.config.enabled and self.config.team_id is not None

    def create_issues_from_tasks(
        self,
        tasks: list[Task],
        project_name: str,
    ) -> dict[str, str]:
        """Create Linear issues from tasks.

        Args:
            tasks: List of tasks to create issues for
            project_name: Name of the project/feature

        Returns:
            Dict mapping task_id to linear_issue_id
        """
        if not self.enabled:
            logger.debug("Linear integration disabled, skipping issue creation")
            return {}

        if not self._check_mcp_available():
            logger.warning("Linear MCP not available, skipping issue creation")
            return {}

        results = {}
        for task in tasks:
            try:
                issue_id = self._create_issue(task, project_name)
                if issue_id:
                    results[task["id"]] = issue_id
                    self._issue_cache[task["id"]] = issue_id
            except Exception as e:
                logger.warning(f"Failed to create Linear issue for {task.get('id')}: {e}")

        return results

    def update_issue_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> bool:
        """Update Linear issue status when task status changes.

        Args:
            task_id: Task ID
            status: New task status

        Returns:
            True if update successful, False otherwise
        """
        if not self.enabled:
            return True  # Not a failure if disabled

        issue_id = self._issue_cache.get(task_id)
        if not issue_id:
            logger.debug(f"No Linear issue found for task {task_id}")
            return True

        linear_status = self.config.status_mapping.get(
            status.value if isinstance(status, TaskStatus) else status,
            "Backlog"
        )

        try:
            return self._update_issue(issue_id, {"status": linear_status})
        except Exception as e:
            logger.warning(f"Failed to update Linear issue {issue_id}: {e}")
            return False

    def add_blocker_comment(
        self,
        task_id: str,
        blocker: str,
    ) -> bool:
        """Add a blocker comment to Linear issue.

        Args:
            task_id: Task ID
            blocker: Blocker description

        Returns:
            True if comment added, False otherwise
        """
        if not self.enabled:
            return True

        issue_id = self._issue_cache.get(task_id)
        if not issue_id:
            logger.debug(f"No Linear issue found for task {task_id}")
            return True

        try:
            return self._add_comment(issue_id, f"🚫 **Blocked**: {blocker}")
        except Exception as e:
            logger.warning(f"Failed to add comment to Linear issue {issue_id}: {e}")
            return False

    def add_completion_comment(
        self,
        task_id: str,
        notes: str,
    ) -> bool:
        """Add a completion comment to Linear issue.

        Args:
            task_id: Task ID
            notes: Completion notes

        Returns:
            True if comment added, False otherwise
        """
        if not self.enabled:
            return True

        issue_id = self._issue_cache.get(task_id)
        if not issue_id:
            return True

        try:
            return self._add_comment(issue_id, f"✅ **Completed**: {notes}")
        except Exception as e:
            logger.warning(f"Failed to add completion comment: {e}")
            return False

    def _check_mcp_available(self) -> bool:
        """Check if Linear MCP is available.

        Returns:
            True if MCP is available
        """
        if self._mcp_available is not None:
            return self._mcp_available

        # For now, assume not available since MCP integration
        # requires runtime context we don't have in this adapter
        # The actual MCP calls would be made through the MCP server
        # when running in a Claude Code context
        self._mcp_available = False
        logger.info(
            "Linear MCP integration requires MCP runtime. "
            "Add mcp-linear to your mcp.json for full integration."
        )
        return self._mcp_available

    def _create_issue(self, task: Task, project_name: str) -> Optional[str]:
        """Create a Linear issue for a task.

        Note: This is a placeholder for the actual MCP call.
        In practice, the workflow nodes would call the Linear MCP
        tools directly when available.

        Args:
            task: Task to create issue for
            project_name: Project name

        Returns:
            Issue ID if created, None otherwise
        """
        # Placeholder - actual implementation would call Linear MCP
        logger.debug(f"Would create Linear issue for task {task.get('id')}")
        return None

    def _update_issue(self, issue_id: str, updates: dict) -> bool:
        """Update a Linear issue.

        Args:
            issue_id: Issue ID
            updates: Fields to update

        Returns:
            True if updated
        """
        # Placeholder
        logger.debug(f"Would update Linear issue {issue_id}: {updates}")
        return True

    def _add_comment(self, issue_id: str, body: str) -> bool:
        """Add a comment to a Linear issue.

        Args:
            issue_id: Issue ID
            body: Comment body

        Returns:
            True if added
        """
        # Placeholder
        logger.debug(f"Would add comment to Linear issue {issue_id}")
        return True


def create_linear_adapter(project_dir: Path) -> LinearAdapter:
    """Factory function to create a Linear adapter.

    Args:
        project_dir: Project directory path

    Returns:
        Configured LinearAdapter instance
    """
    config = load_linear_config(project_dir)
    return LinearAdapter(config)


def save_issue_mapping(
    project_dir: Path,
    mapping: dict[str, str],
) -> None:
    """Save task-to-issue mapping to workflow directory.

    Args:
        project_dir: Project directory
        mapping: Dict of task_id -> linear_issue_id
    """
    if not mapping:
        return

    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    mapping_file = workflow_dir / "linear_issues.json"

    # Load existing mapping
    existing = {}
    if mapping_file.exists():
        try:
            existing = json.loads(mapping_file.read_text())
        except json.JSONDecodeError:
            pass

    # Merge and save
    existing.update(mapping)
    mapping_file.write_text(json.dumps(existing, indent=2))


def load_issue_mapping(project_dir: Path) -> dict[str, str]:
    """Load task-to-issue mapping from workflow directory.

    Args:
        project_dir: Project directory

    Returns:
        Dict of task_id -> linear_issue_id
    """
    mapping_file = project_dir / ".workflow" / "linear_issues.json"
    if not mapping_file.exists():
        return {}

    try:
        return json.loads(mapping_file.read_text())
    except json.JSONDecodeError:
        return {}
