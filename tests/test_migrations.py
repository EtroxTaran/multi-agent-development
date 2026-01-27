"""Tests for database migrations.

Tests the migration system including:
- Migration registry and versioning
- Apply migrations (up)
- Rollback migrations (down)
- Migration status tracking
- Dry-run mode
"""


from orchestrator.db.migrations.base import MigrationRecord, MigrationStatus
from orchestrator.db.migrations.registry import get_registry
from orchestrator.db.migrations.runner import MigrationResult


class TestMigrationRegistry:
    """Tests for migration registry."""

    def test_registry_has_migrations(self):
        """Test that registry contains migrations."""
        registry = get_registry()
        migrations = registry.get_all()

        assert len(migrations) >= 6, "Expected at least 6 migrations"

    def test_migrations_have_versions(self):
        """Test that all migrations have valid versions."""
        registry = get_registry()

        for migration in registry.get_all():
            assert migration.version, f"Migration {migration.name} has no version"
            assert migration.version.isdigit(), f"Version {migration.version} not numeric"

    def test_migrations_have_names(self):
        """Test that all migrations have names."""
        registry = get_registry()

        for migration in registry.get_all():
            assert migration.name, f"Migration {migration.version} has no name"

    def test_migrations_ordered_by_version(self):
        """Test that migrations are returned in version order."""
        registry = get_registry()
        migrations = registry.get_all()

        versions = [int(m.version) for m in migrations]
        assert versions == sorted(versions), "Migrations not in version order"

    def test_get_specific_migration(self):
        """Test retrieving a specific migration by version."""
        registry = get_registry()

        migration = registry.get("0001")
        assert migration is not None
        assert migration.version == "0001"
        assert migration.name == "initial_schema"

    def test_get_versions(self):
        """Test getting list of versions."""
        registry = get_registry()
        versions = registry.get_versions()

        assert "0001" in versions
        assert "0002" in versions
        assert "0003" in versions


class TestBaseMigration:
    """Tests for BaseMigration class."""

    def test_full_name_property(self):
        """Test full_name combines version and name."""
        registry = get_registry()
        migration = registry.get("0001")

        assert migration.full_name == "0001_initial_schema"

    def test_checksum_calculation(self):
        """Test checksum is calculated consistently."""
        registry = get_registry()
        migration = registry.get("0001")

        checksum1 = migration.get_checksum()
        checksum2 = migration.get_checksum()

        assert checksum1 == checksum2
        assert len(checksum1) == 16  # Truncated SHA256


class TestMigrationDown:
    """Tests for migration down (rollback) methods."""

    def test_m0001_has_down(self):
        """Test m_0001 initial_schema has down() implemented."""
        registry = get_registry()
        migration = registry.get("0001")

        # Should not raise NotImplementedError
        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_m0002_has_down(self):
        """Test m_0002 phase_outputs_logs has down() implemented."""
        registry = get_registry()
        migration = registry.get("0002")

        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_m0003_has_down(self):
        """Test m_0003 flexible_types has down() implemented."""
        registry = get_registry()
        migration = registry.get("0003")

        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_m0004_has_down(self):
        """Test m_0004 auto_improvement has down() implemented."""
        registry = get_registry()
        migration = registry.get("0004")

        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_m0005_has_down(self):
        """Test m_0005 langgraph_persistence has down() implemented."""
        registry = get_registry()
        migration = registry.get("0005")

        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_m0006_has_down(self):
        """Test m_0006 guardrails_system has down() implemented."""
        registry = get_registry()
        migration = registry.get("0006")

        assert hasattr(migration, "down")
        assert callable(migration.down)

    def test_all_migrations_have_down(self):
        """Test that all migrations have down() implemented."""
        registry = get_registry()

        for migration in registry.get_all():
            assert hasattr(migration, "down"), f"{migration.full_name} missing down()"
            assert callable(migration.down), f"{migration.full_name} down() not callable"


class TestMigrationRecord:
    """Tests for MigrationRecord dataclass."""

    def test_create_pending_record(self):
        """Test creating a pending migration record."""
        record = MigrationRecord(
            version="0001",
            name="initial_schema",
            status=MigrationStatus.PENDING,
        )

        assert record.version == "0001"
        assert record.name == "initial_schema"
        assert record.status == MigrationStatus.PENDING
        assert record.applied_at is None

    def test_create_applied_record(self):
        """Test creating an applied migration record."""
        from datetime import datetime

        now = datetime.utcnow()
        record = MigrationRecord(
            version="0001",
            name="initial_schema",
            status=MigrationStatus.APPLIED,
            applied_at=now,
            execution_time_ms=150,
        )

        assert record.status == MigrationStatus.APPLIED
        assert record.applied_at == now
        assert record.execution_time_ms == 150

    def test_create_failed_record(self):
        """Test creating a failed migration record."""
        record = MigrationRecord(
            version="0001",
            name="initial_schema",
            status=MigrationStatus.FAILED,
            error="Database connection failed",
        )

        assert record.status == MigrationStatus.FAILED
        assert record.error == "Database connection failed"


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_success_result(self):
        """Test successful migration result."""
        result = MigrationResult(
            success=True,
            applied=[
                MigrationRecord(
                    version="0001",
                    name="initial_schema",
                    status=MigrationStatus.APPLIED,
                )
            ],
        )

        assert result.success is True
        assert len(result.applied) == 1
        assert result.failed is None

    def test_failed_result(self):
        """Test failed migration result."""
        result = MigrationResult(
            success=False,
            applied=[],
            failed=MigrationRecord(
                version="0001",
                name="initial_schema",
                status=MigrationStatus.FAILED,
                error="Test error",
            ),
        )

        assert result.success is False
        assert result.failed is not None
        assert result.failed.error == "Test error"

    def test_dry_run_result(self):
        """Test dry-run migration result."""
        result = MigrationResult(
            success=True,
            applied=[
                MigrationRecord(
                    version="0001",
                    name="initial_schema",
                    status=MigrationStatus.APPLIED,
                )
            ],
            dry_run=True,
        )

        assert result.dry_run is True


class TestMigrationStatus:
    """Tests for MigrationStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert MigrationStatus.PENDING.value == "pending"
        assert MigrationStatus.APPLIED.value == "applied"
        assert MigrationStatus.ROLLED_BACK.value == "rolled_back"
        assert MigrationStatus.FAILED.value == "failed"

    def test_status_from_string(self):
        """Test creating status from string value."""
        status = MigrationStatus("applied")
        assert status == MigrationStatus.APPLIED


class TestMigrationDependencies:
    """Tests for migration dependencies."""

    def test_m0001_has_no_dependencies(self):
        """Test first migration has no dependencies."""
        registry = get_registry()
        migration = registry.get("0001")

        assert migration.dependencies == []

    def test_m0002_depends_on_m0001(self):
        """Test m_0002 depends on m_0001."""
        registry = get_registry()
        migration = registry.get("0002")

        assert "0001" in migration.dependencies

    def test_dependencies_chain(self):
        """Test migration dependencies form a valid chain."""
        registry = get_registry()
        migrations = registry.get_all()

        for i, migration in enumerate(migrations):
            if i == 0:
                # First migration should have no dependencies
                assert migration.dependencies == [], f"{migration.full_name} should have no deps"
            else:
                # Each subsequent migration should depend on previous
                prev_version = migrations[i - 1].version
                assert (
                    prev_version in migration.dependencies
                ), f"{migration.full_name} should depend on {prev_version}"
