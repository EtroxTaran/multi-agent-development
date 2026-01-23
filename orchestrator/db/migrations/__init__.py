"""Database migration system for SurrealDB schema management.

Provides a formal migration framework with:
- Versioned migrations with dependencies
- Up/down migration support
- CLI operations for apply/rollback/status
- Dry-run mode for testing
- Migration history tracking

Usage:
    from orchestrator.db.migrations import (
        MigrationRunner,
        get_pending_migrations,
        apply_migrations,
        rollback_migrations,
    )

    # Check pending migrations
    pending = await get_pending_migrations("my-project")

    # Apply all pending
    results = await apply_migrations("my-project")

    # Rollback last migration
    results = await rollback_migrations("my-project", steps=1)

CLI Usage:
    python -m orchestrator.db.migrations migrate --project my-app
    python -m orchestrator.db.migrations rollback --project my-app --steps 1
    python -m orchestrator.db.migrations status --project my-app
    python -m orchestrator.db.migrations create add_new_feature
"""

from .base import (
    BaseMigration,
    MigrationContext,
    MigrationRecord,
    MigrationStatus,
    MigrationError,
)

from .registry import (
    MigrationRegistry,
    get_registry,
    discover_migrations,
)

from .runner import (
    MigrationRunner,
    get_pending_migrations,
    apply_migrations,
    rollback_migrations,
    get_migration_status,
)

__all__ = [
    # Base classes
    "BaseMigration",
    "MigrationContext",
    "MigrationRecord",
    "MigrationStatus",
    "MigrationError",
    # Registry
    "MigrationRegistry",
    "get_registry",
    "discover_migrations",
    # Runner
    "MigrationRunner",
    "get_pending_migrations",
    "apply_migrations",
    "rollback_migrations",
    "get_migration_status",
]
