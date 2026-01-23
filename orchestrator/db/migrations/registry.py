"""Migration registry for discovering and ordering migrations.

Provides:
- Automatic discovery of migration modules
- Topological sorting based on dependencies
- Caching of discovered migrations
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Optional

from .base import BaseMigration, MigrationError

logger = logging.getLogger(__name__)

# Global registry cache
_registry: Optional["MigrationRegistry"] = None


class MigrationRegistry:
    """Registry for managing and ordering migrations.

    Discovers migrations from the versions/ directory and
    orders them based on version numbers and dependencies.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._migrations: dict[str, BaseMigration] = {}
        self._sorted: Optional[list[BaseMigration]] = None

    def register(self, migration: BaseMigration) -> None:
        """Register a migration.

        Args:
            migration: Migration instance to register

        Raises:
            MigrationError: If version already registered
        """
        if migration.version in self._migrations:
            existing = self._migrations[migration.version]
            raise MigrationError(
                f"Duplicate migration version {migration.version}: "
                f"{existing.name} and {migration.name}"
            )

        self._migrations[migration.version] = migration
        self._sorted = None  # Invalidate cache

    def get(self, version: str) -> Optional[BaseMigration]:
        """Get a migration by version.

        Args:
            version: Migration version

        Returns:
            Migration instance or None
        """
        return self._migrations.get(version)

    def get_all(self) -> list[BaseMigration]:
        """Get all migrations in order.

        Returns:
            List of migrations sorted by version and dependencies
        """
        if self._sorted is None:
            self._sorted = self._topological_sort()
        return self._sorted.copy()

    def get_versions(self) -> list[str]:
        """Get all registered versions in order.

        Returns:
            List of version strings
        """
        return [m.version for m in self.get_all()]

    def _topological_sort(self) -> list[BaseMigration]:
        """Sort migrations respecting dependencies.

        Uses Kahn's algorithm for topological sorting.

        Returns:
            Sorted list of migrations

        Raises:
            MigrationError: If circular dependencies detected
        """
        migrations = list(self._migrations.values())

        # Build dependency graph
        in_degree: dict[str, int] = {m.version: 0 for m in migrations}
        dependents: dict[str, list[str]] = {m.version: [] for m in migrations}

        for m in migrations:
            for dep in m.dependencies:
                if dep not in self._migrations:
                    logger.warning(f"Migration {m.version} depends on unknown version {dep}")
                    continue
                in_degree[m.version] += 1
                dependents[dep].append(m.version)

        # Start with migrations that have no dependencies
        queue = sorted([v for v, d in in_degree.items() if d == 0])
        result: list[BaseMigration] = []

        while queue:
            version = queue.pop(0)
            result.append(self._migrations[version])

            for dependent in sorted(dependents[version]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
            queue.sort()

        # Check for cycles
        if len(result) != len(migrations):
            remaining = set(in_degree.keys()) - {m.version for m in result}
            raise MigrationError(f"Circular dependency detected in migrations: {remaining}")

        return result


def discover_migrations(package_path: Optional[Path] = None) -> MigrationRegistry:
    """Discover all migrations in the versions package.

    Args:
        package_path: Optional path to versions package

    Returns:
        Registry with discovered migrations
    """
    registry = MigrationRegistry()

    # Import the versions package
    versions_package = "orchestrator.db.migrations.versions"

    try:
        versions_module = importlib.import_module(versions_package)
    except ImportError as e:
        logger.warning(f"Could not import versions package: {e}")
        return registry

    # Get the package path
    if package_path is None:
        package_path = Path(versions_module.__file__).parent

    # Discover migration modules
    for _, name, ispkg in pkgutil.iter_modules([str(package_path)]):
        if ispkg or not name.startswith("m_"):
            continue

        try:
            module = importlib.import_module(f"{versions_package}.{name}")

            # Find migration class in module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseMigration)
                    and attr is not BaseMigration
                ):
                    migration = attr()
                    registry.register(migration)
                    logger.debug(f"Discovered migration: {migration.full_name}")
                    break

        except Exception as e:
            logger.error(f"Failed to load migration {name}: {e}")

    return registry


def get_registry(refresh: bool = False) -> MigrationRegistry:
    """Get the global migration registry.

    Args:
        refresh: Force re-discovery of migrations

    Returns:
        Migration registry
    """
    global _registry

    if _registry is None or refresh:
        _registry = discover_migrations()

    return _registry
