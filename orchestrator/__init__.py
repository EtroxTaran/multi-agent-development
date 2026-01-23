"""Multi-Agent Orchestration System.

Coordinates Claude Code, Cursor CLI, and Gemini CLI through a 5-phase workflow.
"""

# Load environment variables from .env files FIRST
# This ensures SURREAL_URL and other config is available before any DB imports
from .utils.env_loader import load_env as _load_env

_load_env()

from .orchestrator import Orchestrator

__version__ = "0.1.0"

__all__ = ["Orchestrator", "__version__"]
