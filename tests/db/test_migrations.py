"""Tests for the database migration system."""

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.db.migrations.base import (
    BaseMigration,
    MigrationContext,
    MigrationError,
    MigrationRecord,
    MigrationStatus,
)
from orchestrator.db.migrations.registry import MigrationRegistry, discover_migrations
from orchestrator.db.migrations.runner import MigrationRunner


# Test Migrations for unit tests
class TestMigration001(BaseMigration):
    """Test migration 1."""

    version = "0001"
    name = "test_initial"
    dependencies = []

    async def up(self, ctx: MigrationContext) -> None:
        await ctx.execute("CREATE test_table SET name = 'test'")

    async def down(self, ctx: MigrationContext) -> None:
        await ctx.execute("REMOVE TABLE test_table")


class TestMigration002(BaseMigration):
    """Test migration 2."""

    version = "0002"
    name = "test_second"
    dependencies = ["0001"]

    async def up(self, ctx: MigrationContext) -> None:
        await ctx.execute("CREATE test_table2 SET name = 'test2'")

    async def down(self, ctx: MigrationContext) -> None:
        await ctx.execute("REMOVE TABLE test_table2")


class TestMigration003NoRollback(BaseMigration):
    """Test migration without rollback support."""

    version = "0003"
    name = "test_no_rollback"
    dependencies = ["0002"]

    async def up(self, ctx: MigrationContext) -> None:
        await ctx.execute("CREATE test_table3 SET name = 'test3'")

    # No down() method - uses default NotImplementedError


class TestBaseMigration:
    """Tests for BaseMigration class."""

    def test_migration_requires_version(self):
        """Test that migrations must define version."""
        with pytest.raises(TypeError, match="must define 'version'"):

            class BadMigration(BaseMigration):
                name = "bad"

                async def up(self, ctx):
                    pass

    def test_migration_requires_name(self):
        """Test that migrations must define name."""
        with pytest.raises(TypeError, match="must define 'name'"):

            class BadMigration(BaseMigration):
                version = "0001"

                async def up(self, ctx):
                    pass

    def test_full_name(self):
        """Test full_name property."""
        m = TestMigration001()
        assert m.full_name == "0001_test_initial"

    def test_get_checksum(self):
        """Test checksum generation."""
        m = TestMigration001()
        checksum = m.get_checksum()
        assert isinstance(checksum, str)
        assert len(checksum) == 16

    def test_repr(self):
        """Test string representation."""
        m = TestMigration001()
        assert repr(m) == "<Migration 0001_test_initial>"


class TestMigrationContext:
    """Tests for MigrationContext class."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = AsyncMock()
        conn.query = AsyncMock(return_value=[])
        return conn

    @pytest.fixture
    def ctx(self, mock_conn):
        """Create a migration context."""
        return MigrationContext(
            conn=mock_conn,
            project_name="test-project",
            dry_run=False,
        )

    @pytest.fixture
    def dry_run_ctx(self, mock_conn):
        """Create a dry-run migration context."""
        return MigrationContext(
            conn=mock_conn,
            project_name="test-project",
            dry_run=True,
        )

    @pytest.mark.asyncio
    async def test_execute(self, ctx, mock_conn):
        """Test execute method."""
        await ctx.execute("CREATE table SET x = 1")
        mock_conn.query.assert_called_once_with("CREATE table SET x = 1", None)

    @pytest.mark.asyncio
    async def test_execute_dry_run(self, dry_run_ctx, mock_conn):
        """Test execute in dry-run mode."""
        result = await dry_run_ctx.execute("CREATE table SET x = 1")
        mock_conn.query.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_execute_batch(self, ctx, mock_conn):
        """Test execute_batch method."""
        statements = ["CREATE t1 SET x = 1", "CREATE t2 SET y = 2"]
        await ctx.execute_batch(statements)
        assert mock_conn.query.call_count == 2

    @pytest.mark.asyncio
    async def test_table_exists(self, ctx, mock_conn):
        """Test table_exists method."""
        mock_conn.query.return_value = [{"fields": {}, "indexes": {}}]
        # Use a real table name from the allowlist
        result = await ctx.table_exists("tasks")
        assert result is True

    @pytest.mark.asyncio
    async def test_table_not_exists(self, ctx, mock_conn):
        """Test table_exists when table doesn't exist."""
        mock_conn.query.side_effect = Exception("Table not found")
        # Use a real table name from the allowlist that doesn't exist in DB
        result = await ctx.table_exists("workflow_state")
        assert result is False

    @pytest.mark.asyncio
    async def test_field_exists(self, ctx, mock_conn):
        """Test field_exists method."""
        mock_conn.query.return_value = [{"fields": {"name": "string"}}]
        # Use real table and field names from the allowlist
        result = await ctx.field_exists("tasks", "name")
        assert result is True

    @pytest.mark.asyncio
    async def test_index_exists(self, ctx, mock_conn):
        """Test index_exists method."""
        mock_conn.query.return_value = [{"indexes": {"idx_name": "..."}}]
        # Use a real table name from the allowlist
        result = await ctx.index_exists("tasks", "idx_name")
        assert result is True

    def test_executed_statements_tracking(self, ctx):
        """Test that executed statements are tracked."""
        assert ctx.executed_statements == []
        # Manually add to test tracking
        ctx._executed_statements.append("TEST SQL")
        assert len(ctx.executed_statements) == 1
        assert "TEST SQL" in ctx.executed_statements


class TestMigrationRegistry:
    """Tests for MigrationRegistry class."""

    def test_register_migration(self):
        """Test registering a migration."""
        registry = MigrationRegistry()
        m = TestMigration001()
        registry.register(m)
        assert registry.get("0001") is m

    def test_register_duplicate_fails(self):
        """Test that duplicate versions raise error."""
        registry = MigrationRegistry()
        m1 = TestMigration001()
        registry.register(m1)

        # Create another migration with same version
        class DuplicateMigration(BaseMigration):
            version = "0001"
            name = "duplicate"

            async def up(self, ctx):
                pass

        with pytest.raises(MigrationError, match="Duplicate migration version"):
            registry.register(DuplicateMigration())

    def test_get_all_sorted(self):
        """Test that get_all returns sorted migrations."""
        registry = MigrationRegistry()
        m2 = TestMigration002()
        m1 = TestMigration001()

        # Register in wrong order
        registry.register(m2)
        registry.register(m1)

        all_migrations = registry.get_all()
        assert len(all_migrations) == 2
        assert all_migrations[0].version == "0001"
        assert all_migrations[1].version == "0002"

    def test_get_versions(self):
        """Test get_versions method."""
        registry = MigrationRegistry()
        registry.register(TestMigration001())
        registry.register(TestMigration002())

        versions = registry.get_versions()
        assert versions == ["0001", "0002"]

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are detected."""

        class CyclicA(BaseMigration):
            version = "A"
            name = "cyclic_a"
            dependencies = ["B"]

            async def up(self, ctx):
                pass

        class CyclicB(BaseMigration):
            version = "B"
            name = "cyclic_b"
            dependencies = ["A"]

            async def up(self, ctx):
                pass

        registry = MigrationRegistry()
        registry.register(CyclicA())
        registry.register(CyclicB())

        with pytest.raises(MigrationError, match="Circular dependency"):
            registry.get_all()


class TestMigrationRunner:
    """Tests for MigrationRunner class."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = MigrationRegistry()
        registry.register(TestMigration001())
        registry.register(TestMigration002())
        return registry

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection."""
        conn = AsyncMock()
        conn.query = AsyncMock(return_value=[])
        return conn

    @pytest.mark.asyncio
    async def test_get_pending_migrations(self, mock_registry, mock_conn):
        """Test getting pending migrations."""
        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=mock_registry)
            pending = await runner.get_pending_migrations()

            assert len(pending) == 2
            assert pending[0].version == "0001"
            assert pending[1].version == "0002"

    @pytest.mark.asyncio
    async def test_apply_migrations(self, mock_registry, mock_conn):
        """Test applying migrations."""
        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=mock_registry)
            result = await runner.apply()

            assert result.success is True
            assert len(result.applied) == 2
            assert result.applied[0].version == "0001"
            assert result.applied[1].version == "0002"

    @pytest.mark.asyncio
    async def test_apply_dry_run(self, mock_registry, mock_conn):
        """Test dry-run mode."""
        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=mock_registry)
            result = await runner.apply(dry_run=True)

            assert result.success is True
            assert result.dry_run is True
            assert len(result.applied) == 2

    @pytest.mark.asyncio
    async def test_apply_with_target_version(self, mock_registry, mock_conn):
        """Test applying up to target version."""
        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=mock_registry)
            result = await runner.apply(target_version="0001")

            assert result.success is True
            assert len(result.applied) == 1
            assert result.applied[0].version == "0001"

    @pytest.mark.asyncio
    async def test_rollback_migrations(self, mock_registry, mock_conn):
        """Test rolling back migrations."""
        # Simulate that only 1 migration is returned (respecting LIMIT)
        mock_conn.query.return_value = [
            {"version": "0002", "name": "test_second", "status": "applied"},
        ]

        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=mock_registry)
            result = await runner.rollback(steps=1)

            assert result.success is True
            assert len(result.applied) == 1
            assert result.applied[0].version == "0002"

    @pytest.mark.asyncio
    async def test_rollback_not_supported(self, mock_conn):
        """Test rollback when migration doesn't support it."""
        registry = MigrationRegistry()
        registry.register(TestMigration001())
        registry.register(TestMigration002())
        registry.register(TestMigration003NoRollback())

        # Simulate that 0003 is applied
        mock_conn.query.return_value = [
            {"version": "0003", "name": "test_no_rollback", "status": "applied"},
        ]

        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=registry)
            result = await runner.rollback(steps=1)

            assert result.success is False
            assert result.failed is not None
            assert result.failed.version == "0003"
            assert "Rollback not supported" in result.failed.error

    @pytest.mark.asyncio
    async def test_migration_failure_handling(self, mock_conn):
        """Test handling of migration failures."""

        class FailingMigration(BaseMigration):
            version = "0001"
            name = "failing"
            dependencies = []

            async def up(self, ctx: MigrationContext) -> None:
                raise RuntimeError("Migration failed!")

        registry = MigrationRegistry()
        registry.register(FailingMigration())

        with patch("orchestrator.db.migrations.runner.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            runner = MigrationRunner("test-project", registry=registry)
            result = await runner.apply()

            assert result.success is False
            assert result.failed is not None
            assert result.failed.version == "0001"
            assert "Migration failed!" in result.failed.error


class TestDiscoverMigrations:
    """Tests for migration discovery."""

    def test_discover_real_migrations(self):
        """Test discovering real migration files."""
        registry = discover_migrations()

        # Should discover our actual migrations
        versions = registry.get_versions()
        assert "0001" in versions
        assert "0002" in versions
        assert "0003" in versions
        assert "0004" in versions


class TestMigrationStatus:
    """Tests for MigrationStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert MigrationStatus.PENDING.value == "pending"
        assert MigrationStatus.APPLIED.value == "applied"
        assert MigrationStatus.ROLLED_BACK.value == "rolled_back"
        assert MigrationStatus.FAILED.value == "failed"


class TestMigrationRecord:
    """Tests for MigrationRecord dataclass."""

    def test_record_creation(self):
        """Test creating a migration record."""
        record = MigrationRecord(
            version="0001",
            name="test",
            status=MigrationStatus.APPLIED,
        )
        assert record.version == "0001"
        assert record.name == "test"
        assert record.status == MigrationStatus.APPLIED
        assert record.applied_at is None
        assert record.error is None
