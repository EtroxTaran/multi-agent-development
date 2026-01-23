"""Workflow state storage adapter.

Provides unified interface for workflow state management using SurrealDB.
This is the DB-only version - no file fallback.
"""

import logging
from pathlib import Path
from typing import Optional

from .surreal_store import SurrealWorkflowRepository

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
WorkflowStorageAdapter = SurrealWorkflowRepository

# Cache of adapters per project
_workflow_adapters: dict[str, SurrealWorkflowRepository] = {}


def get_workflow_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> SurrealWorkflowRepository:
    """Get or create workflow storage adapter for a project.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        SurrealWorkflowRepository instance
    """
    key = str(Path(project_dir).resolve())

    if key not in _workflow_adapters:
        _workflow_adapters[key] = SurrealWorkflowRepository(project_dir, project_name)
    return _workflow_adapters[key]