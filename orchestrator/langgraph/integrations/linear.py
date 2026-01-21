"""Linear integration adapter.

Provides optional integration with Linear issue tracking:
- Create issues from tasks
- Update issue status when task status changes
- Add blocker comments

Uses the official Linear MCP (https://mcp.linear.app/mcp) with graceful degradation.
MCP calls are made via subprocess to the Claude CLI.
"""

import asyncio
import json
import logging
import os
import subprocess
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

        Tests MCP availability by attempting to list teams.

        Returns:
            True if MCP is available
        """
        if self._mcp_available is not None:
            return self._mcp_available

        try:
            # Test MCP by running a simple query
            prompt = "List Linear teams using the mcp__linear__listTeams tool. Return only the JSON response."
            result = self._run_mcp_command(prompt)

            if result and "teams" in result.lower():
                self._mcp_available = True
                logger.info("Linear MCP is available")
            else:
                self._mcp_available = False
                logger.info(
                    "Linear MCP not available. "
                    "Ensure mcp-linear is configured in your mcp.json."
                )
        except Exception as e:
            self._mcp_available = False
            logger.info(f"Linear MCP check failed: {e}")

        return self._mcp_available

    def _create_issue(self, task: Task, project_name: str) -> Optional[str]:
        """Create a Linear issue for a task.

        Uses the Linear MCP createIssue tool.

        Args:
            task: Task to create issue for
            project_name: Project name

        Returns:
            Issue ID if created, None otherwise
        """
        task_id = task.get("id", "")
        title = task.get("title", "")
        user_story = task.get("user_story", "")
        acceptance_criteria = task.get("acceptance_criteria", [])
        priority_map = {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
        }
        priority = priority_map.get(task.get("priority", "medium"), 3)

        # Build description
        description_parts = [
            f"**Project:** {project_name}",
            f"**Task ID:** {task_id}",
            "",
            "## User Story",
            user_story or "_No user story defined_",
            "",
            "## Acceptance Criteria",
        ]
        for criterion in acceptance_criteria:
            description_parts.append(f"- [ ] {criterion}")

        description = "\n".join(description_parts)

        prompt = f"""Create a Linear issue using mcp__linear__createIssue with:
- teamId: "{self.config.team_id}"
- title: "[{task_id}] {title}"
- description: {json.dumps(description)}
- priority: {priority}

Return ONLY the issue ID from the response in format: ISSUE_ID: <id>"""

        try:
            result = self._run_mcp_command(prompt)
            if result:
                # Parse issue ID from response
                if "ISSUE_ID:" in result:
                    issue_id = result.split("ISSUE_ID:")[1].strip().split()[0]
                    logger.info(f"Created Linear issue {issue_id} for task {task_id}")
                    return issue_id

                # Try to parse from JSON response
                try:
                    data = json.loads(result)
                    if isinstance(data, dict):
                        issue_id = data.get("id") or data.get("issueId")
                        if issue_id:
                            logger.info(f"Created Linear issue {issue_id} for task {task_id}")
                            return issue_id
                except json.JSONDecodeError:
                    pass

                logger.warning(f"Could not parse issue ID from response: {result[:200]}")

        except Exception as e:
            logger.warning(f"Failed to create Linear issue for task {task_id}: {e}")

        return None

    def _update_issue(self, issue_id: str, updates: dict) -> bool:
        """Update a Linear issue.

        Uses the Linear MCP updateIssue tool.

        Args:
            issue_id: Issue ID
            updates: Fields to update (e.g., {"status": "In Progress"})

        Returns:
            True if updated
        """
        # Build the update prompt
        update_fields = []
        for key, value in updates.items():
            if key == "status":
                # Status needs to be mapped to state ID
                update_fields.append(f'- stateId for status "{value}"')
            else:
                update_fields.append(f"- {key}: {json.dumps(value)}")

        prompt = f"""Update Linear issue {issue_id} using mcp__linear__updateIssue with:
{chr(10).join(update_fields)}

First get the workflow states for the team to find the correct stateId, then update the issue.
Return SUCCESS if updated, or ERROR with reason."""

        try:
            result = self._run_mcp_command(prompt)
            if result and "SUCCESS" in result.upper():
                logger.debug(f"Updated Linear issue {issue_id}")
                return True
            elif result and "ERROR" not in result.upper():
                # Assume success if no explicit error
                logger.debug(f"Updated Linear issue {issue_id}")
                return True
            else:
                logger.warning(f"Failed to update Linear issue {issue_id}: {result}")
                return False

        except Exception as e:
            logger.warning(f"Failed to update Linear issue {issue_id}: {e}")
            return False

    def _add_comment(self, issue_id: str, body: str) -> bool:
        """Add a comment to a Linear issue.

        Uses the Linear MCP createComment tool.

        Args:
            issue_id: Issue ID
            body: Comment body (markdown supported)

        Returns:
            True if added
        """
        prompt = f"""Add a comment to Linear issue {issue_id} using mcp__linear__createComment with:
- issueId: "{issue_id}"
- body: {json.dumps(body)}

Return SUCCESS if added, or ERROR with reason."""

        try:
            result = self._run_mcp_command(prompt)
            if result and "SUCCESS" in result.upper():
                logger.debug(f"Added comment to Linear issue {issue_id}")
                return True
            elif result and "ERROR" not in result.upper():
                # Assume success if no explicit error
                logger.debug(f"Added comment to Linear issue {issue_id}")
                return True
            else:
                logger.warning(f"Failed to add comment to Linear issue {issue_id}: {result}")
                return False

        except Exception as e:
            logger.warning(f"Failed to add comment to Linear issue {issue_id}: {e}")
            return False

    def _run_mcp_command(self, prompt: str, timeout: int = 30) -> Optional[str]:
        """Run a Claude CLI command with MCP tools.

        Args:
            prompt: Prompt for Claude
            timeout: Command timeout in seconds

        Returns:
            Command output or None on failure
        """
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "text",
            "--allowedTools", "mcp__linear__*",
            "--max-turns", "3",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "TERM": "dumb"},
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.debug(f"MCP command failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.warning(f"MCP command timed out after {timeout}s")
            return None
        except FileNotFoundError:
            logger.warning("Claude CLI not found")
            return None
        except Exception as e:
            logger.warning(f"MCP command error: {e}")
            return None


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
