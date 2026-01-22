"""File boundary enforcement for orchestrator.

The orchestrator should only write to specific paths within a project directory.
This module enforces those boundaries to prevent accidental modification of
application code (which should only be modified by worker Claude instances).

Orchestrator-writable paths:
- .workflow/**     - Workflow state and phase outputs
- .project-config.json - Project configuration
- Docs/**          - Documentation (can reorganize/improve)

Everything else (src/, tests/, CLAUDE.md, PRODUCT.md in root, etc.) is worker-only.
"""

import fnmatch
from pathlib import Path
from typing import Optional


class OrchestratorBoundaryError(Exception):
    """Raised when orchestrator attempts to write outside allowed boundaries."""

    def __init__(self, path: Path, project_dir: Path, message: Optional[str] = None):
        self.path = path
        self.project_dir = project_dir
        if message:
            super().__init__(message)
        else:
            super().__init__(
                f"Orchestrator cannot write to '{path.relative_to(project_dir)}'. "
                f"Only .workflow/ and .project-config.json are writable by orchestrator."
            )


# Patterns for paths the orchestrator is allowed to write to
ORCHESTRATOR_WRITABLE_PATTERNS = [
    ".workflow/**",
    ".workflow",
    ".project-config.json",
    "Docs/**",
    "Docs",
]

# Patterns for paths that are explicitly forbidden (even if they match above)
ORCHESTRATOR_FORBIDDEN_PATTERNS = [
    "src/**",
    "tests/**",
    "test/**",
    "lib/**",
    "app/**",
    "*.py",  # Python source files at root
    "*.ts",
    "*.js",
    "*.tsx",
    "*.jsx",
    "*.go",
    "*.rs",
    "CLAUDE.md",
    "GEMINI.md",
    "PRODUCT.md",
    ".cursor/**",
]


def validate_orchestrator_write(project_dir: Path, target_path: Path) -> bool:
    """Check if orchestrator is allowed to write to a path.

    Args:
        project_dir: Root directory of the project
        target_path: Path the orchestrator wants to write to

    Returns:
        True if the write is allowed, False otherwise
    """
    # Resolve paths to handle relative paths and symlinks
    project_dir = Path(project_dir).resolve()
    target_path = Path(target_path).resolve()

    # Ensure target is within project directory
    try:
        relative = target_path.relative_to(project_dir)
    except ValueError:
        # Path is outside project directory
        return False

    # Check for symlinks in the path that could escape the project
    # This prevents TOCTOU attacks where symlinks change after validation
    if not _validate_no_escaping_symlinks(project_dir, target_path):
        return False

    relative_str = str(relative)

    # Check against forbidden patterns first
    for pattern in ORCHESTRATOR_FORBIDDEN_PATTERNS:
        if _matches_pattern(relative_str, pattern):
            return False

    # Check against allowed patterns
    for pattern in ORCHESTRATOR_WRITABLE_PATTERNS:
        if _matches_pattern(relative_str, pattern):
            return True

    # Default: deny
    return False


def _validate_no_escaping_symlinks(project_dir: Path, target_path: Path) -> bool:
    """Check that no symlinks in the path escape the project directory.

    This prevents TOCTOU (time-of-check-time-of-use) attacks where
    a symlink is created/modified between validation and the actual write.

    Args:
        project_dir: Root directory of the project
        target_path: Path to validate

    Returns:
        True if all symlinks (if any) stay within project directory
    """
    project_dir = Path(project_dir).resolve()

    # Check each component of the path from project_dir to target
    current = project_dir
    try:
        relative = target_path.relative_to(project_dir)
    except ValueError:
        return False

    for part in relative.parts:
        current = current / part

        # Check if this component is a symlink
        if current.is_symlink():
            # Resolve the symlink and check if it stays within project
            try:
                resolved = current.resolve()
                resolved.relative_to(project_dir)
            except ValueError:
                # Symlink escapes project directory
                return False
            except OSError:
                # Broken symlink or permission error
                return False

    return True


def _matches_pattern(path_str: str, pattern: str) -> bool:
    """Check if a path matches a glob pattern.

    Args:
        path_str: Path string to check
        pattern: Glob pattern (supports ** for directory traversal)

    Returns:
        True if the path matches the pattern
    """
    # Handle ** patterns for directory traversal
    if "**" in pattern:
        # Convert to fnmatch-compatible pattern
        # ** matches any number of directories
        parts = pattern.split("**")
        if len(parts) == 2:
            prefix, suffix = parts
            prefix = prefix.rstrip("/")
            suffix = suffix.lstrip("/")

            # Check if path starts with prefix
            if prefix:
                if not path_str.startswith(prefix):
                    return False
                # Remove prefix from path for suffix matching
                remaining = path_str[len(prefix):].lstrip("/")
            else:
                remaining = path_str

            # If no suffix, any path under prefix matches
            if not suffix:
                return True

            # Check if remaining path ends with suffix or matches suffix
            if fnmatch.fnmatch(remaining, f"*{suffix}"):
                return True
            if fnmatch.fnmatch(remaining, f"*/{suffix}"):
                return True
            if remaining == suffix:
                return True

            return False

    # Simple glob matching
    return fnmatch.fnmatch(path_str, pattern)


def ensure_orchestrator_can_write(project_dir: Path, target_path: Path) -> None:
    """Validate that orchestrator can write to path, raising error if not.

    Args:
        project_dir: Root directory of the project
        target_path: Path the orchestrator wants to write to

    Raises:
        OrchestratorBoundaryError: If the write is not allowed
    """
    if not validate_orchestrator_write(project_dir, target_path):
        raise OrchestratorBoundaryError(target_path, project_dir)


def get_writable_paths_info() -> dict:
    """Get information about orchestrator writable paths.

    Returns:
        Dictionary with writable and forbidden pattern information
    """
    return {
        "writable_patterns": ORCHESTRATOR_WRITABLE_PATTERNS.copy(),
        "forbidden_patterns": ORCHESTRATOR_FORBIDDEN_PATTERNS.copy(),
        "description": (
            "Orchestrator can write to .workflow/, .project-config.json, and Docs/. "
            "All other paths (src/, tests/, application code) must be modified by workers."
        ),
    }


def is_workflow_path(project_dir: Path, target_path: Path) -> bool:
    """Check if a path is within the .workflow directory.

    Args:
        project_dir: Root directory of the project
        target_path: Path to check

    Returns:
        True if path is within .workflow/
    """
    project_dir = Path(project_dir).resolve()
    target_path = Path(target_path).resolve()

    try:
        relative = target_path.relative_to(project_dir)
    except ValueError:
        return False

    return str(relative).startswith(".workflow")


def is_project_config(project_dir: Path, target_path: Path) -> bool:
    """Check if a path is the project config file.

    Args:
        project_dir: Root directory of the project
        target_path: Path to check

    Returns:
        True if path is .project-config.json
    """
    project_dir = Path(project_dir).resolve()
    target_path = Path(target_path).resolve()

    try:
        relative = target_path.relative_to(project_dir)
    except ValueError:
        return False

    return str(relative) == ".project-config.json"
