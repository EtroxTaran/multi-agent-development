"""Logging setup helper."""

import logging
from pathlib import Path
from orchestrator.utils.logging import OrchestrationLogger, LogLevel

def setup_logging(project_dir: Path, debug: bool = False) -> None:
    """Setup logging configuration.
    
    Args:
        project_dir: Project directory
        debug: Enable debug logging
    """
    level = LogLevel.DEBUG if debug else LogLevel.INFO
    logger = OrchestrationLogger(
        workflow_dir=project_dir / ".workflow",
        min_level=level,
        console_output=True
    )
    
    # Configure python logging to redirect to our logger
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
