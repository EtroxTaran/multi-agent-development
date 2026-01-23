"""FastAPI dependencies."""

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Query

from .config import get_settings

# Add orchestrator to path
_settings = get_settings()
sys.path.insert(0, str(_settings.conductor_root))

from orchestrator.agents.budget import BudgetManager
from orchestrator.orchestrator import Orchestrator
from orchestrator.project_manager import ProjectManager
from orchestrator.storage.audit_adapter import AuditStorageAdapter, get_audit_storage


@lru_cache
def get_project_manager() -> ProjectManager:
    """Get ProjectManager singleton.

    Returns:
        ProjectManager instance
    """
    settings = get_settings()
    return ProjectManager(settings.conductor_root)


def get_project_dir(
    project_name: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Path:
    """Get project directory from project name.

    Args:
        project_name: Project name
        project_manager: ProjectManager instance

    Returns:
        Path to project directory

    Raises:
        HTTPException: If project not found
    """
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_name}' not found",
        )
    return project_dir


def get_orchestrator(project_dir: Path = Depends(get_project_dir)) -> Orchestrator:
    """Get Orchestrator for a project.

    Args:
        project_dir: Project directory

    Returns:
        Orchestrator instance
    """
    return Orchestrator(project_dir, console_output=False)


def get_audit_adapter(
    project_dir: Path = Depends(get_project_dir),
) -> AuditStorageAdapter:
    """Get AuditStorageAdapter for a project.

    Args:
        project_dir: Project directory

    Returns:
        AuditStorageAdapter instance
    """
    return get_audit_storage(project_dir)


def get_budget_manager(
    project_dir: Path = Depends(get_project_dir),
) -> BudgetManager:
    """Get BudgetManager for a project.

    Args:
        project_dir: Project directory

    Returns:
        BudgetManager instance
    """
    return BudgetManager(project_dir)


# Query parameter dependencies
def pagination_params(
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of items to return"),
) -> dict:
    """Get pagination parameters.

    Args:
        offset: Number of items to skip
        limit: Maximum number of items to return

    Returns:
        Dict with offset and limit
    """
    return {"offset": offset, "limit": limit}
