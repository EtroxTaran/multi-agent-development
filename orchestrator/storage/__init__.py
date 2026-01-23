"""Storage adapter layer for orchestrator.

Provides unified storage interfaces that automatically select between
file-based and SurrealDB backends based on configuration. The adapters
implement the Protocol classes defined in base.py, ensuring consistent
behavior regardless of the underlying storage mechanism.

Architecture:
    Callers (sync)  →  Storage Adapters  →  File Backend (fallback)
                                        →  SurrealDB Backend (if enabled)

Usage:
    from orchestrator.storage import (
        get_audit_storage,
        get_session_storage,
        get_budget_storage,
        get_checkpoint_storage,
        get_workflow_storage,
    )

    # Get storage adapters for a project
    project_dir = Path("/path/to/project")

    audit = get_audit_storage(project_dir)
    session = get_session_storage(project_dir)
    budget = get_budget_storage(project_dir)
    checkpoint = get_checkpoint_storage(project_dir)
    workflow = get_workflow_storage(project_dir)

    # Use adapters - they automatically select backend
    with audit.record("claude", "T1", prompt) as entry:
        result = run_command(...)
        entry.set_result(success=True, exit_code=0)

    session.create_session("T1", agent="claude")
    budget.record_spend("T1", "claude", 0.05)
    checkpoint.create_checkpoint("pre-refactor")
    workflow.set_phase(2, status="in_progress")

Backend Selection:
    SurrealDB is used when:
    - SURREAL_URL environment variable is set
    - Connection can be established

    File backend is used when:
    - SURREAL_URL is not set (default)
    - SurrealDB connection fails (graceful fallback)
"""

from pathlib import Path
from typing import Optional

# Async utilities
from .async_utils import (
    AsyncContextAdapter,
    ensure_async,
    gather_with_fallback,
    run_async,
    sync_wrapper,
)

# Adapters and factory functions
from .audit_adapter import AuditRecordContext, AuditStorageAdapter, get_audit_storage

# Protocol definitions (for type hints)
from .base import (
    AuditEntryData,
    AuditStatisticsData,
    AuditStorageProtocol,
    BudgetRecordData,
    BudgetStorageProtocol,
    BudgetSummaryData,
    CheckpointData,
    CheckpointStorageProtocol,
    SessionData,
    SessionStorageProtocol,
    WorkflowStateData,
    WorkflowStorageProtocol,
)
from .budget_adapter import BudgetStorageAdapter, get_budget_storage
from .checkpoint_adapter import CheckpointStorageAdapter, get_checkpoint_storage
from .session_adapter import SessionStorageAdapter, get_session_storage
from .workflow_adapter import WorkflowStorageAdapter, get_workflow_storage


def get_all_storage(
    project_dir: Path,
    project_name: Optional[str] = None,
) -> dict:
    """Get all storage adapters for a project.

    Convenience function to get all adapters at once.

    Args:
        project_dir: Project directory
        project_name: Project name (defaults to directory name)

    Returns:
        Dictionary with all storage adapters
    """
    return {
        "audit": get_audit_storage(project_dir, project_name),
        "session": get_session_storage(project_dir, project_name),
        "budget": get_budget_storage(project_dir, project_name),
        "checkpoint": get_checkpoint_storage(project_dir, project_name),
        "workflow": get_workflow_storage(project_dir, project_name),
    }


def is_surrealdb_active() -> bool:
    """Check if SurrealDB is currently active for storage.

    Returns:
        True if SurrealDB is enabled and connected
    """
    try:
        from orchestrator.db import is_surrealdb_enabled

        return is_surrealdb_enabled()
    except ImportError:
        return False


__all__ = [
    # Protocols
    "AuditStorageProtocol",
    "SessionStorageProtocol",
    "BudgetStorageProtocol",
    "CheckpointStorageProtocol",
    "WorkflowStorageProtocol",
    # Data classes
    "AuditEntryData",
    "AuditStatisticsData",
    "SessionData",
    "BudgetRecordData",
    "BudgetSummaryData",
    "CheckpointData",
    "WorkflowStateData",
    # Async utilities
    "run_async",
    "sync_wrapper",
    "AsyncContextAdapter",
    "ensure_async",
    "gather_with_fallback",
    # Adapters
    "AuditStorageAdapter",
    "AuditRecordContext",
    "SessionStorageAdapter",
    "BudgetStorageAdapter",
    "CheckpointStorageAdapter",
    "WorkflowStorageAdapter",
    # Factory functions
    "get_audit_storage",
    "get_session_storage",
    "get_budget_storage",
    "get_checkpoint_storage",
    "get_workflow_storage",
    "get_all_storage",
    # Utility
    "is_surrealdb_active",
]
