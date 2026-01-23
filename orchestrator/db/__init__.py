"""SurrealDB integration for Conductor orchestrator.

Provides:
- Connection management with pooling
- Schema definitions and migrations
- Repository layer for all entities
- Live Query support for real-time monitoring
- Migration utilities from file-based storage

Usage:
    from orchestrator.db import (
        get_connection,
        ensure_schema,
        get_audit_repository,
        get_workflow_repository,
        get_task_repository,
        is_surrealdb_enabled,
    )

    # Check if SurrealDB is configured
    if is_surrealdb_enabled():
        # Initialize schema
        await ensure_schema("my-project")

        # Use repositories
        audit = get_audit_repository("my-project")
        entry = await audit.create_entry("claude", "T1", "My prompt")

    # Real-time monitoring
    from orchestrator.db import create_workflow_monitor

    async with create_workflow_monitor("my-project") as monitor:
        await monitor.on_task_change(lambda e: print(f"Task changed: {e}"))
        # ... do work ...

Environment Variables:
    SURREAL_URL: WebSocket URL (ws:// or wss://)
    SURREAL_NAMESPACE: Namespace for isolation
    SURREAL_USER: Authentication username
    SURREAL_PASS: Authentication password
    SURREAL_DATABASE: Default database name
    SURREAL_POOL_SIZE: Connection pool size
    SURREAL_LIVE_QUERIES: Enable live queries (true/false)
"""

from .config import (
    SurrealConfig,
    get_config,
    set_config,
    is_surrealdb_enabled,
    require_db,
    DatabaseRequiredError,
)

from .connection import (
    Connection,
    ConnectionPool,
    ConnectionError,
    QueryError,
    get_connection,
    get_pool,
    close_all_pools,
)

from .schema import (
    SCHEMA_VERSION,
    apply_schema,
    ensure_schema,
    get_schema_version,
)

from .migrations import (
    BaseMigration,
    MigrationContext,
    MigrationRecord,
    MigrationStatus,
    MigrationError,
    MigrationRunner,
    get_pending_migrations,
    apply_migrations,
    rollback_migrations,
    get_migration_status,
)

from .live import (
    LiveEvent,
    EventType,
    LiveQueryManager,
    WorkflowMonitor,
    create_workflow_monitor,
)

from .repositories import (
    AuditRepository,
    get_audit_repository,
    WorkflowRepository,
    get_workflow_repository,
    TaskRepository,
    get_task_repository,
    CheckpointRepository,
    get_checkpoint_repository,
    SessionRepository,
    get_session_repository,
    BudgetRepository,
    get_budget_repository,
    PhaseOutputRepository,
    get_phase_output_repository,
    OutputType,
    LogsRepository,
    get_logs_repository,
    LogType,
)

__all__ = [
    # Config
    "SurrealConfig",
    "get_config",
    "set_config",
    "is_surrealdb_enabled",
    "require_db",
    "DatabaseRequiredError",
    # Connection
    "Connection",
    "ConnectionPool",
    "ConnectionError",
    "QueryError",
    "get_connection",
    "get_pool",
    "close_all_pools",
    # Schema
    "SCHEMA_VERSION",
    "apply_schema",
    "ensure_schema",
    "get_schema_version",
    # Migrations
    "BaseMigration",
    "MigrationContext",
    "MigrationRecord",
    "MigrationStatus",
    "MigrationError",
    "MigrationRunner",
    "get_pending_migrations",
    "apply_migrations",
    "rollback_migrations",
    "get_migration_status",
    # Live Queries
    "LiveEvent",
    "EventType",
    "LiveQueryManager",
    "WorkflowMonitor",
    "create_workflow_monitor",
    # Repositories
    "AuditRepository",
    "get_audit_repository",
    "WorkflowRepository",
    "get_workflow_repository",
    "TaskRepository",
    "get_task_repository",
    "CheckpointRepository",
    "get_checkpoint_repository",
    "SessionRepository",
    "get_session_repository",
    "BudgetRepository",
    "get_budget_repository",
    "PhaseOutputRepository",
    "get_phase_output_repository",
    "OutputType",
    "LogsRepository",
    "get_logs_repository",
    "LogType",
]
