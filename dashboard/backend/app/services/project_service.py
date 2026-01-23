"""Project management service.

Wraps ProjectManager with additional functionality for the dashboard.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)

# Add orchestrator to path
import sys

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))

from orchestrator.project_manager import ProjectManager


class ProjectService:
    """Service for project management operations.

    Provides a high-level interface over ProjectManager with
    additional features for the dashboard.
    """

    def __init__(self, project_manager: Optional[ProjectManager] = None):
        """Initialize project service.

        Args:
            project_manager: Optional ProjectManager instance
        """
        self.settings = get_settings()
        self._project_manager = project_manager

    @property
    def project_manager(self) -> ProjectManager:
        """Get or create project manager."""
        if self._project_manager is None:
            self._project_manager = ProjectManager(self.settings.conductor_root)
        return self._project_manager

    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects with enriched information.

        Returns:
            List of project info dictionaries
        """
        projects = self.project_manager.list_projects()

        # Enrich with additional info
        for project in projects:
            project_dir = Path(project["path"])
            project["workflow_status"] = self._get_workflow_status(project_dir)
            project["last_activity"] = self._get_last_activity(project_dir)

        return projects

    def get_project(self, name: str) -> Optional[dict[str, Any]]:
        """Get detailed project information.

        Args:
            name: Project name

        Returns:
            Project info dictionary or None
        """
        project_dir = self.project_manager.get_project(name)
        if not project_dir:
            return None

        status = self.project_manager.get_project_status(name)
        if "error" in status:
            return None

        # Enrich with additional info
        status["workflow_status"] = self._get_workflow_status(project_dir)
        status["last_activity"] = self._get_last_activity(project_dir)
        status["task_summary"] = self._get_task_summary(project_dir)

        return status

    def init_project(self, name: str) -> dict[str, Any]:
        """Initialize a new project.

        Args:
            name: Project name

        Returns:
            Result dictionary
        """
        return self.project_manager.init_project(name)

    def get_project_dir(self, name: str) -> Optional[Path]:
        """Get project directory path.

        Args:
            name: Project name

        Returns:
            Path to project directory or None
        """
        return self.project_manager.get_project(name)

    def list_workspace_folders(self) -> list[dict[str, Any]]:
        """List all folders in the workspace.

        Returns:
            List of folder info dictionaries
        """
        workspace_path = self.settings.projects_path

        if not workspace_path.exists():
            return []

        folders = []
        for item in sorted(workspace_path.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                folders.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "is_project": (item / ".project-config.json").exists(),
                        "has_workflow": (item / ".workflow").exists(),
                        "has_product_md": self._has_product_md(item),
                        "has_docs": (item / "Docs").exists() or (item / "Documents").exists(),
                    }
                )

        return folders

    def _has_product_md(self, project_dir: Path) -> bool:
        """Check if project has PRODUCT.md."""
        # Check root
        if (project_dir / "PRODUCT.md").exists():
            return True
        # Check Docs folder
        if (project_dir / "Docs" / "PRODUCT.md").exists():
            return True
        # Check Documents folder
        if (project_dir / "Documents" / "PRODUCT.md").exists():
            return True
        return False

    def _get_workflow_status(self, project_dir: Path) -> str:
        """Get workflow status string.

        Args:
            project_dir: Project directory

        Returns:
            Status string
        """
        state_path = project_dir / ".workflow" / "state.json"
        if not state_path.exists():
            return "not_started"

        try:
            state = json.loads(state_path.read_text())
            current_phase = state.get("current_phase", 0)

            if current_phase == 0:
                return "not_started"
            elif current_phase >= 5:
                # Check if completed
                phase_status = state.get("phase_status", {})
                phase_5 = phase_status.get("5", {})
                if isinstance(phase_5, dict) and phase_5.get("status") == "completed":
                    return "completed"
                return "in_progress"
            else:
                return "in_progress"
        except (json.JSONDecodeError, OSError):
            return "unknown"

    def _get_last_activity(self, project_dir: Path) -> Optional[str]:
        """Get last activity timestamp.

        Args:
            project_dir: Project directory

        Returns:
            ISO timestamp string or None
        """
        state_path = project_dir / ".workflow" / "state.json"
        if not state_path.exists():
            return None

        try:
            state = json.loads(state_path.read_text())
            return state.get("updated_at")
        except (json.JSONDecodeError, OSError):
            return None

    def _get_task_summary(self, project_dir: Path) -> dict[str, int]:
        """Get task summary counts.

        Args:
            project_dir: Project directory

        Returns:
            Dictionary with task counts
        """
        summary = {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
            "failed": 0,
        }

        # Try to load from plan.json
        plan_path = project_dir / ".workflow" / "phases" / "planning" / "plan.json"
        if plan_path.exists():
            try:
                plan = json.loads(plan_path.read_text())
                tasks = plan.get("tasks", [])
                summary["total"] = len(tasks)

                for task in tasks:
                    status = task.get("status", "pending").lower()
                    if status == "completed":
                        summary["completed"] += 1
                    elif status == "in_progress":
                        summary["in_progress"] += 1
                    elif status == "failed":
                        summary["failed"] += 1
                    else:
                        summary["pending"] += 1
            except (json.JSONDecodeError, OSError):
                pass

        return summary
