"""Application configuration."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    reload: bool = Field(default=False, description="Auto-reload on changes")

    # CORS settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins",
    )

    # Conductor settings
    conductor_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent.parent.parent,
        description="Conductor root directory",
    )
    projects_dir: Optional[Path] = Field(
        default=None,
        description="Projects directory (defaults to conductor_root/projects)",
        validation_alias="PROJECTS_DIR",
    )

    # Database settings
    use_surrealdb: bool = Field(default=True, description="Use SurrealDB")
    surrealdb_url: str = Field(
        default="ws://localhost:8001/rpc",
        description="SurrealDB connection URL",
    )
    surrealdb_namespace: str = Field(default="conductor", description="SurrealDB namespace")
    surrealdb_database: str = Field(default="dashboard", description="SurrealDB database")

    # WebSocket settings
    ws_heartbeat_interval: int = Field(
        default=30, description="WebSocket heartbeat interval in seconds"
    )

    # Chat settings
    claude_timeout: int = Field(default=300, description="Claude CLI timeout in seconds")

    @property
    def projects_path(self) -> Path:
        """Get projects directory path."""
        if self.projects_dir:
            return self.projects_dir
        return self.conductor_root / "projects"

    # AI settings
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API Key")

    # Orchestrator settings
    orchestrator_api_url: Optional[str] = Field(
        default="http://localhost:8090", description="Orchestrator API URL"
    )

    # Environment
    node_env: str = Field(default="development", description="Node environment")

    class Config:
        """Pydantic config."""

        env_prefix = "DASHBOARD_"
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def configure(
    conductor_root: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
    **kwargs,
) -> Settings:
    """Configure settings.

    Args:
        conductor_root: Conductor root directory
        projects_dir: Projects directory
        **kwargs: Additional settings

    Returns:
        Settings instance
    """
    global _settings

    config = {}
    if conductor_root:
        config["conductor_root"] = conductor_root
    if projects_dir:
        config["projects_dir"] = projects_dir
    config.update(kwargs)

    _settings = Settings(**config)
    return _settings
