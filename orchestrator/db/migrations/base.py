"""Base classes for the migration system.

Defines the core abstractions:
- BaseMigration: Abstract base class for all migrations
- MigrationContext: Context passed to migration up/down methods
- MigrationRecord: Record of an applied/rolled back migration
- MigrationStatus: Enum for migration states
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..connection import Connection

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base exception for migration errors."""

    pass


class MigrationStatus(str, Enum):
    """Status of a migration."""

    PENDING = "pending"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class MigrationRecord:
    """Record of a migration execution."""

    version: str
    name: str
    status: MigrationStatus
    applied_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    error: Optional[str] = None
    checksum: Optional[str] = None


@dataclass
class MigrationContext:
    """Context passed to migration up/down methods.

    Provides access to the database connection and utilities
    for executing migrations safely.
    """

    conn: Connection
    project_name: str
    dry_run: bool = False
    _executed_statements: list[str] = field(default_factory=list)

    async def execute(self, sql: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Execute a SurrealQL statement.

        In dry-run mode, logs the statement without executing.

        Args:
            sql: SurrealQL statement
            params: Optional parameters

        Returns:
            Query result (empty list in dry-run mode)
        """
        self._executed_statements.append(sql)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would execute: {sql[:200]}...")
            return []

        return await self.conn.query(sql, params)

    async def execute_batch(self, statements: list[str]) -> list[Any]:
        """Execute multiple statements in order.

        Args:
            statements: List of SurrealQL statements

        Returns:
            List of results
        """
        results = []
        for stmt in statements:
            result = await self.execute(stmt)
            results.append(result)
        return results

    async def table_exists(self, table: str) -> bool:
        """Check if a table exists.

        Args:
            table: Table name

        Returns:
            True if table exists
        """
        if self.dry_run:
            return True

        try:
            result = await self.conn.query(f"INFO FOR TABLE {table}")
            return bool(result)
        except Exception:
            return False

    async def field_exists(self, table: str, field_name: str) -> bool:
        """Check if a field exists on a table.

        Args:
            table: Table name
            field_name: Field name

        Returns:
            True if field exists
        """
        if self.dry_run:
            return True

        try:
            result = await self.conn.query(f"INFO FOR TABLE {table}")
            if result and isinstance(result, list) and result[0]:
                fields = result[0].get("fields", {})
                return field_name in fields
            return False
        except Exception:
            return False

    async def index_exists(self, table: str, index_name: str) -> bool:
        """Check if an index exists on a table.

        Args:
            table: Table name
            index_name: Index name

        Returns:
            True if index exists
        """
        if self.dry_run:
            return True

        try:
            result = await self.conn.query(f"INFO FOR TABLE {table}")
            if result and isinstance(result, list) and result[0]:
                indexes = result[0].get("indexes", {})
                return index_name in indexes
            return False
        except Exception:
            return False

    @property
    def executed_statements(self) -> list[str]:
        """Get list of executed statements."""
        return self._executed_statements.copy()


class BaseMigration(ABC):
    """Abstract base class for database migrations.

    Each migration must implement:
    - up(): Apply the migration
    - down(): Rollback the migration (optional, can raise NotImplementedError)

    Attributes:
        version: Unique version identifier (e.g., "0001")
        name: Human-readable migration name
        dependencies: List of version IDs this migration depends on
    """

    version: str
    name: str
    dependencies: list[str] = []

    def __init_subclass__(cls, **kwargs):
        """Validate subclass attributes."""
        super().__init_subclass__(**kwargs)

        # Check required attributes are defined
        if not getattr(cls, "version", None):
            raise TypeError(f"Migration {cls.__name__} must define 'version'")
        if not getattr(cls, "name", None):
            raise TypeError(f"Migration {cls.__name__} must define 'name'")

    @abstractmethod
    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration.

        Args:
            ctx: Migration context with database connection
        """
        pass

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback the migration.

        Default implementation raises NotImplementedError.
        Override to support rollback.

        Args:
            ctx: Migration context with database connection

        Raises:
            NotImplementedError: If rollback is not supported
        """
        raise NotImplementedError(f"Migration {self.version}_{self.name} does not support rollback")

    @property
    def full_name(self) -> str:
        """Get full migration name (version_name)."""
        return f"{self.version}_{self.name}"

    def get_checksum(self) -> str:
        """Calculate checksum of migration code.

        Used to detect if a migration has been modified after being applied.

        Returns:
            SHA256 hex digest of the migration module source
        """
        import inspect

        try:
            source = inspect.getsource(self.__class__)
            return hashlib.sha256(source.encode()).hexdigest()[:16]
        except Exception:
            return ""

    def __repr__(self) -> str:
        return f"<Migration {self.full_name}>"
