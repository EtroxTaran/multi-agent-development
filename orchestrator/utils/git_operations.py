"""Git operations manager for efficient batched git operations."""

import subprocess
from pathlib import Path
from typing import Optional


class GitOperationsManager:
    """Manages git operations with caching and batching for performance.

    Reduces subprocess overhead by:
    - Caching repository detection result
    - Combining multiple git commands into single subprocess calls
    - Using shell scripts for atomic multi-step operations
    """

    def __init__(self, project_dir: Path):
        """Initialize the git operations manager.

        Args:
            project_dir: Root directory of the git repository
        """
        self.project_dir = project_dir
        self._is_repo: Optional[bool] = None  # Cached repo detection

    def is_git_repo(self) -> bool:
        """Check if the project directory is inside a git repository.

        Result is cached after the first call to avoid repeated subprocess calls.

        Returns:
            True if inside a git repository, False otherwise
        """
        if self._is_repo is None:
            self._is_repo = self._check_git_repo()
        return self._is_repo

    def _check_git_repo(self) -> bool:
        """Actually check if directory is a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def auto_commit(self, message: str) -> Optional[str]:
        """Perform status check, add, commit, and get hash in a single subprocess.

        This batches what would normally be 4-5 separate git commands into one
        shell script execution, significantly reducing subprocess overhead.

        Args:
            message: Commit message

        Returns:
            Commit hash (first 8 chars) if commit was made, None otherwise
        """
        if not self.is_git_repo():
            return None

        # Combined shell script:
        # 1. Check if there are changes (status --porcelain)
        # 2. If changes exist, add all and commit
        # 3. Output the commit hash
        # Security: Message passed via GIT_COMMIT_MSG env var to avoid shell injection
        script = '''
        if [ -n "$(git status --porcelain)" ]; then
            git add -A && git commit -m "$GIT_COMMIT_MSG" && git rev-parse HEAD
        fi
        '''

        try:
            # Pass commit message via environment variable for safety
            env = {**__import__('os').environ, 'GIT_COMMIT_MSG': message}
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Return first 8 chars of commit hash
                return result.stdout.strip()[:8]
            return None

        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None

    def get_status(self) -> Optional[str]:
        """Get git status in porcelain format.

        Returns:
            Status output or None on error
        """
        if not self.is_git_repo():
            return None

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes.

        Returns:
            True if there are changes, False otherwise
        """
        status = self.get_status()
        return bool(status)

    def reset_hard(self, target: str) -> bool:
        """Reset repository to a specific commit.

        Args:
            target: Commit hash or ref to reset to

        Returns:
            True if reset succeeded, False otherwise
        """
        if not self.is_git_repo():
            return False

        try:
            result = subprocess.run(
                ["git", "reset", "--hard", target],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_changed_files(self, base_ref: str = "HEAD~1") -> list[str]:
        """Get list of files changed compared to a base reference.

        Args:
            base_ref: Git reference to compare against (default: HEAD~1)

        Returns:
            List of changed file paths
        """
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().split("\n")
            return []
        except Exception:
            return []

    def invalidate_cache(self) -> None:
        """Invalidate the cached repo detection.

        Call this if the repository state may have changed externally.
        """
        self._is_repo = None
