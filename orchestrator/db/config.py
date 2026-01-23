"""SurrealDB configuration.

Environment-based configuration for connecting to SurrealDB.
Supports both local development and remote Dokploy deployment.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Environment(str, Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class SurrealConfig:
    """SurrealDB connection configuration.

    Attributes:
        url: SurrealDB WebSocket URL (ws:// or wss://)
        namespace: SurrealDB namespace for isolation
        user: Authentication username
        password: Authentication password
        default_database: Default database name if not project-specific
        pool_size: Connection pool size
        connect_timeout: Connection timeout in seconds
        query_timeout: Query timeout in seconds
        retry_attempts: Number of retry attempts on connection failure
        retry_delay: Delay between retries in seconds
        enable_live_queries: Whether to enable live query subscriptions
    """

    url: str = field(default_factory=lambda: os.getenv("SURREAL_URL", "ws://localhost:8001/rpc"))
    namespace: str = field(default_factory=lambda: os.getenv("SURREAL_NAMESPACE", "orchestrator"))
    user: str = field(default_factory=lambda: os.getenv("SURREAL_USER", "root"))
    password: str = field(
        default_factory=lambda: os.getenv("SURREAL_PASS", "root")  # Default for local development
    )
    default_database: str = field(default_factory=lambda: os.getenv("SURREAL_DATABASE", "default"))
    pool_size: int = field(default_factory=lambda: int(os.getenv("SURREAL_POOL_SIZE", "5")))
    connect_timeout: float = field(
        default_factory=lambda: float(os.getenv("SURREAL_CONNECT_TIMEOUT", "10.0"))
    )
    query_timeout: float = field(
        default_factory=lambda: float(os.getenv("SURREAL_QUERY_TIMEOUT", "30.0"))
    )
    retry_attempts: int = field(
        default_factory=lambda: int(os.getenv("SURREAL_RETRY_ATTEMPTS", "3"))
    )
    retry_delay: float = field(
        default_factory=lambda: float(os.getenv("SURREAL_RETRY_DELAY", "1.0"))
    )
    enable_live_queries: bool = field(
        default_factory=lambda: os.getenv("SURREAL_LIVE_QUERIES", "true").lower() == "true"
    )
    skip_ssl_verify: bool = field(
        default_factory=lambda: os.getenv("SURREAL_SKIP_SSL_VERIFY", "false").lower() == "true"
    )

    @property
    def is_secure(self) -> bool:
        """Check if using secure WebSocket connection."""
        return self.url.startswith("wss://")

    @property
    def environment(self) -> Environment:
        """Detect environment from URL."""
        if "localhost" in self.url or "127.0.0.1" in self.url:
            return Environment.DEVELOPMENT
        elif "staging" in self.url:
            return Environment.STAGING
        return Environment.PRODUCTION

    def get_database_name(self, project_name: Optional[str] = None) -> str:
        """Get database name for a project.

        Args:
            project_name: Project name (uses default if None)

        Returns:
            Database name (sanitized for SurrealDB)
        """
        name = project_name or self.default_database
        # Sanitize: replace hyphens with underscores, lowercase
        return name.replace("-", "_").lower()

    def validate(self) -> list[str]:
        """Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.url:
            errors.append("SURREAL_URL is required")
        elif not self.url.startswith(("ws://", "wss://")):
            errors.append("SURREAL_URL must start with ws:// or wss://")

        if not self.namespace:
            errors.append("SURREAL_NAMESPACE is required")

        if not self.user:
            errors.append("SURREAL_USER is required")

        if self.environment == Environment.PRODUCTION:
            if not self.password:
                errors.append("SURREAL_PASS is required in production")
            if not self.is_secure:
                errors.append("Production should use wss:// (secure WebSocket)")

        return errors


# Global configuration instance
_config: Optional[SurrealConfig] = None


def get_config() -> SurrealConfig:
    """Get the global SurrealDB configuration.

    Returns:
        SurrealConfig instance
    """
    global _config
    if _config is None:
        _config = SurrealConfig()
    return _config


def set_config(config: SurrealConfig) -> None:
    """Set the global SurrealDB configuration.

    Args:
        config: Configuration to use
    """
    global _config
    _config = config


def is_surrealdb_enabled() -> bool:
    """Check if SurrealDB integration is enabled.

    For local development, SurrealDB is always enabled (uses localhost:8000).
    Set SURREAL_DISABLED=true to explicitly disable.

    Returns:
        True if SurrealDB should be used
    """
    # Explicit disable flag
    if os.getenv("SURREAL_DISABLED", "").lower() == "true":
        return False
    # Default: enabled (local or remote)
    return True


class DatabaseRequiredError(Exception):
    """Raised when SurrealDB is required but not configured."""

    pass


def require_db() -> None:
    """Ensure SurrealDB is configured. Raises if not.

    Raises:
        DatabaseRequiredError: If SurrealDB is explicitly disabled

    Usage:
        from orchestrator.db.config import require_db
        require_db()  # Raises if DB disabled
    """
    if not is_surrealdb_enabled():
        raise DatabaseRequiredError(
            "SurrealDB is required but explicitly disabled (SURREAL_DISABLED=true).\n"
            "Remove SURREAL_DISABLED or set it to 'false' to enable SurrealDB.\n"
            "For local development, run: docker-compose up -d"
        )


def get_project_database(project_name: Optional[str] = None) -> str:
    """Get the database name for a project.

    Each project gets its own database within the namespace for complete isolation.
    Database names are sanitized to be SurrealDB-compatible:
    - Hyphens replaced with underscores
    - Converted to lowercase
    - Invalid characters removed

    Args:
        project_name: Project name (uses default database if None)

    Returns:
        Sanitized database name for SurrealDB

    Examples:
        >>> get_project_database("my-app")
        'my_app'
        >>> get_project_database("My Project")
        'my_project'
        >>> get_project_database(None)
        'default'
    """
    config = get_config()

    if project_name is None:
        return config.default_database

    # Sanitize the project name for database naming
    import re

    # Replace hyphens and spaces with underscores
    safe_name = project_name.replace("-", "_").replace(" ", "_")
    # Remove any characters that aren't alphanumeric or underscore
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "", safe_name)
    # Convert to lowercase
    safe_name = safe_name.lower()
    # Ensure it starts with a letter (prefix with 'p_' if it starts with a number)
    if safe_name and safe_name[0].isdigit():
        safe_name = f"p_{safe_name}"
    # Default to 'default' if empty after sanitization
    if not safe_name:
        return config.default_database

    return safe_name


def sanitize_project_name(project_name: str) -> str:
    """Sanitize a project name for use as a database identifier.

    This is a convenience alias for get_project_database() for cases
    where you just need the sanitized name.

    Args:
        project_name: Raw project name

    Returns:
        Sanitized name suitable for database/table names
    """
    return get_project_database(project_name)
