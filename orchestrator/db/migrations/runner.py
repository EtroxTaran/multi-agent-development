"""Migration runner for applying and rolling back migrations.

Provides:
- Apply pending migrations
- Rollback applied migrations
- Migration status reporting
- Dry-run support
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..connection import get_connection
from .base import (
    BaseMigration,
    MigrationContext,
    MigrationError,
    MigrationRecord,
    MigrationStatus,
)
from .registry import get_registry, MigrationRegistry

logger = logging.getLogger(__name__)


# SQL for migrations tracking table
MIGRATIONS_TABLE_SQL = """
DEFINE TABLE IF NOT EXISTS _migrations SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON TABLE _migrations TYPE string;
DEFINE FIELD IF NOT EXISTS name ON TABLE _migrations TYPE string;
DEFINE FIELD IF NOT EXISTS status ON TABLE _migrations TYPE string;
DEFINE FIELD IF NOT EXISTS applied_at ON TABLE _migrations TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS rolled_back_at ON TABLE _migrations TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS execution_time_ms ON TABLE _migrations TYPE option<int>;
DEFINE FIELD IF NOT EXISTS error ON TABLE _migrations TYPE option<string>;
DEFINE FIELD IF NOT EXISTS checksum ON TABLE _migrations TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_migration_version ON TABLE _migrations COLUMNS version UNIQUE;
"""


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    success: bool
    applied: list[MigrationRecord]
    failed: Optional[MigrationRecord] = None
    dry_run: bool = False


class MigrationRunner:
    """Runner for executing migrations."""

    def __init__(
        self,
        project_name: str,
        registry: Optional[MigrationRegistry] = None,
    ):
        """Initialize the runner.

        Args:
            project_name: Project database name
            registry: Optional migration registry (uses global if not provided)
        """
        self.project_name = project_name
        self.registry = registry or get_registry()

    async def _ensure_migrations_table(self, ctx: MigrationContext) -> None:
        """Ensure the migrations tracking table exists."""
        await ctx.execute(MIGRATIONS_TABLE_SQL)

    async def _get_applied_versions(self, ctx: MigrationContext) -> set[str]:
        """Get set of applied migration versions.

        Args:
            ctx: Migration context

        Returns:
            Set of applied version strings
        """
        if ctx.dry_run:
            return set()

        result = await ctx.conn.query(
            "SELECT version FROM _migrations WHERE status = $status",
            {"status": MigrationStatus.APPLIED.value},
        )
        return {r["version"] for r in result} if result else set()

    async def _record_migration(
        self,
        ctx: MigrationContext,
        migration: BaseMigration,
        status: MigrationStatus,
        execution_time_ms: int,
        error: Optional[str] = None,
    ) -> None:
        """Record migration execution in tracking table.

        Args:
            ctx: Migration context
            migration: Migration that was executed
            status: Result status
            execution_time_ms: Execution time in milliseconds
            error: Optional error message
        """
        if ctx.dry_run:
            return

        now = datetime.utcnow().isoformat() + "Z"

        # Check if record exists
        existing = await ctx.conn.query(
            "SELECT * FROM _migrations WHERE version = $version",
            {"version": migration.version},
        )

        data = {
            "version": migration.version,
            "name": migration.name,
            "status": status.value,
            "execution_time_ms": execution_time_ms,
            "checksum": migration.get_checksum(),
            "error": error,
        }

        if status == MigrationStatus.APPLIED:
            data["applied_at"] = now
        elif status == MigrationStatus.ROLLED_BACK:
            data["rolled_back_at"] = now

        if existing:
            await ctx.conn.query(
                "UPDATE _migrations SET status = $status, "
                "execution_time_ms = $execution_time_ms, "
                "checksum = $checksum, "
                "error = $error, "
                + ("applied_at = $applied_at " if "applied_at" in data else "")
                + ("rolled_back_at = $rolled_back_at " if "rolled_back_at" in data else "")
                + "WHERE version = $version",
                data,
            )
        else:
            await ctx.conn.query(
                "CREATE _migrations CONTENT $data",
                {"data": data},
            )

    async def get_pending_migrations(self) -> list[BaseMigration]:
        """Get list of pending migrations.

        Returns:
            List of migrations that haven't been applied
        """
        async with get_connection(self.project_name) as conn:
            ctx = MigrationContext(
                conn=conn,
                project_name=self.project_name,
                dry_run=True,
            )
            await self._ensure_migrations_table(ctx)

            # Get applied versions
            ctx.dry_run = False  # Need real data
            applied = await self._get_applied_versions(ctx)

            # Filter to pending
            all_migrations = self.registry.get_all()
            return [m for m in all_migrations if m.version not in applied]

    async def get_status(self) -> list[MigrationRecord]:
        """Get status of all migrations.

        Returns:
            List of migration records with status
        """
        records: list[MigrationRecord] = []

        async with get_connection(self.project_name) as conn:
            ctx = MigrationContext(
                conn=conn,
                project_name=self.project_name,
                dry_run=False,
            )
            await self._ensure_migrations_table(ctx)

            # Get all applied/rolled back records
            result = await conn.query("SELECT * FROM _migrations ORDER BY version")
            applied_map = {r["version"]: r for r in result} if result else {}

            # Build status for all migrations
            for migration in self.registry.get_all():
                if migration.version in applied_map:
                    record = applied_map[migration.version]
                    records.append(
                        MigrationRecord(
                            version=record["version"],
                            name=record["name"],
                            status=MigrationStatus(record["status"]),
                            applied_at=(
                                datetime.fromisoformat(record["applied_at"].rstrip("Z"))
                                if record.get("applied_at")
                                else None
                            ),
                            rolled_back_at=(
                                datetime.fromisoformat(record["rolled_back_at"].rstrip("Z"))
                                if record.get("rolled_back_at")
                                else None
                            ),
                            execution_time_ms=record.get("execution_time_ms"),
                            error=record.get("error"),
                            checksum=record.get("checksum"),
                        )
                    )
                else:
                    records.append(
                        MigrationRecord(
                            version=migration.version,
                            name=migration.name,
                            status=MigrationStatus.PENDING,
                        )
                    )

        return records

    async def apply(
        self,
        target_version: Optional[str] = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Apply pending migrations.

        Args:
            target_version: Optional target version (applies up to and including)
            dry_run: If True, don't actually execute migrations

        Returns:
            Migration result with applied/failed records
        """
        applied: list[MigrationRecord] = []

        async with get_connection(self.project_name) as conn:
            ctx = MigrationContext(
                conn=conn,
                project_name=self.project_name,
                dry_run=dry_run,
            )

            await self._ensure_migrations_table(ctx)
            applied_versions = await self._get_applied_versions(ctx)

            for migration in self.registry.get_all():
                # Skip already applied
                if migration.version in applied_versions:
                    continue

                # Stop if past target
                if target_version and migration.version > target_version:
                    break

                # Check dependencies
                for dep in migration.dependencies:
                    if dep not in applied_versions and dep not in {
                        r.version for r in applied
                    }:
                        return MigrationResult(
                            success=False,
                            applied=applied,
                            failed=MigrationRecord(
                                version=migration.version,
                                name=migration.name,
                                status=MigrationStatus.FAILED,
                                error=f"Missing dependency: {dep}",
                            ),
                            dry_run=dry_run,
                        )

                # Execute migration
                logger.info(
                    f"{'[DRY-RUN] ' if dry_run else ''}Applying migration "
                    f"{migration.full_name}..."
                )

                start_time = time.time()
                try:
                    await migration.up(ctx)
                    execution_time_ms = int((time.time() - start_time) * 1000)

                    record = MigrationRecord(
                        version=migration.version,
                        name=migration.name,
                        status=MigrationStatus.APPLIED,
                        applied_at=datetime.utcnow(),
                        execution_time_ms=execution_time_ms,
                        checksum=migration.get_checksum(),
                    )
                    applied.append(record)

                    await self._record_migration(
                        ctx,
                        migration,
                        MigrationStatus.APPLIED,
                        execution_time_ms,
                    )

                    logger.info(
                        f"{'[DRY-RUN] ' if dry_run else ''}Applied "
                        f"{migration.full_name} in {execution_time_ms}ms"
                    )

                except Exception as e:
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    error_msg = str(e)

                    await self._record_migration(
                        ctx,
                        migration,
                        MigrationStatus.FAILED,
                        execution_time_ms,
                        error_msg,
                    )

                    logger.error(
                        f"Failed to apply migration {migration.full_name}: {error_msg}"
                    )

                    return MigrationResult(
                        success=False,
                        applied=applied,
                        failed=MigrationRecord(
                            version=migration.version,
                            name=migration.name,
                            status=MigrationStatus.FAILED,
                            execution_time_ms=execution_time_ms,
                            error=error_msg,
                        ),
                        dry_run=dry_run,
                    )

        return MigrationResult(
            success=True,
            applied=applied,
            dry_run=dry_run,
        )

    async def rollback(
        self,
        steps: int = 1,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Rollback applied migrations.

        Args:
            steps: Number of migrations to rollback
            dry_run: If True, don't actually execute rollback

        Returns:
            Migration result with rolled back/failed records
        """
        rolled_back: list[MigrationRecord] = []

        async with get_connection(self.project_name) as conn:
            ctx = MigrationContext(
                conn=conn,
                project_name=self.project_name,
                dry_run=dry_run,
            )

            await self._ensure_migrations_table(ctx)

            # Get applied migrations in reverse order
            result = await conn.query(
                "SELECT * FROM _migrations WHERE status = $status "
                "ORDER BY version DESC LIMIT $limit",
                {"status": MigrationStatus.APPLIED.value, "limit": steps},
            )

            if not result:
                logger.info("No migrations to rollback")
                return MigrationResult(success=True, applied=[], dry_run=dry_run)

            for record in result:
                migration = self.registry.get(record["version"])
                if not migration:
                    logger.warning(
                        f"Migration {record['version']} not found in registry, skipping"
                    )
                    continue

                logger.info(
                    f"{'[DRY-RUN] ' if dry_run else ''}Rolling back "
                    f"{migration.full_name}..."
                )

                start_time = time.time()
                try:
                    await migration.down(ctx)
                    execution_time_ms = int((time.time() - start_time) * 1000)

                    rollback_record = MigrationRecord(
                        version=migration.version,
                        name=migration.name,
                        status=MigrationStatus.ROLLED_BACK,
                        rolled_back_at=datetime.utcnow(),
                        execution_time_ms=execution_time_ms,
                        checksum=migration.get_checksum(),
                    )
                    rolled_back.append(rollback_record)

                    await self._record_migration(
                        ctx,
                        migration,
                        MigrationStatus.ROLLED_BACK,
                        execution_time_ms,
                    )

                    logger.info(
                        f"{'[DRY-RUN] ' if dry_run else ''}Rolled back "
                        f"{migration.full_name} in {execution_time_ms}ms"
                    )

                except NotImplementedError:
                    logger.error(
                        f"Migration {migration.full_name} does not support rollback"
                    )
                    return MigrationResult(
                        success=False,
                        applied=rolled_back,
                        failed=MigrationRecord(
                            version=migration.version,
                            name=migration.name,
                            status=MigrationStatus.FAILED,
                            error="Rollback not supported",
                        ),
                        dry_run=dry_run,
                    )

                except Exception as e:
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    error_msg = str(e)

                    logger.error(
                        f"Failed to rollback migration {migration.full_name}: {error_msg}"
                    )

                    return MigrationResult(
                        success=False,
                        applied=rolled_back,
                        failed=MigrationRecord(
                            version=migration.version,
                            name=migration.name,
                            status=MigrationStatus.FAILED,
                            execution_time_ms=execution_time_ms,
                            error=error_msg,
                        ),
                        dry_run=dry_run,
                    )

        return MigrationResult(
            success=True,
            applied=rolled_back,
            dry_run=dry_run,
        )


# Convenience functions


async def get_pending_migrations(project_name: str) -> list[BaseMigration]:
    """Get pending migrations for a project.

    Args:
        project_name: Project name

    Returns:
        List of pending migrations
    """
    runner = MigrationRunner(project_name)
    return await runner.get_pending_migrations()


async def apply_migrations(
    project_name: str,
    target_version: Optional[str] = None,
    dry_run: bool = False,
) -> MigrationResult:
    """Apply pending migrations for a project.

    Args:
        project_name: Project name
        target_version: Optional target version
        dry_run: If True, don't execute migrations

    Returns:
        Migration result
    """
    runner = MigrationRunner(project_name)
    return await runner.apply(target_version=target_version, dry_run=dry_run)


async def rollback_migrations(
    project_name: str,
    steps: int = 1,
    dry_run: bool = False,
) -> MigrationResult:
    """Rollback migrations for a project.

    Args:
        project_name: Project name
        steps: Number of migrations to rollback
        dry_run: If True, don't execute rollback

    Returns:
        Migration result
    """
    runner = MigrationRunner(project_name)
    return await runner.rollback(steps=steps, dry_run=dry_run)


async def get_migration_status(project_name: str) -> list[MigrationRecord]:
    """Get migration status for a project.

    Args:
        project_name: Project name

    Returns:
        List of migration records with status
    """
    runner = MigrationRunner(project_name)
    return await runner.get_status()
