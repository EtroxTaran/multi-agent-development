"""Git worktree management for parallel worker execution.

Git worktrees allow multiple workers to operate on isolated copies of the
repository simultaneously, avoiding file conflicts during parallel execution.

Each worker gets its own worktree (a separate working directory linked to
the same git repository), implements its task, and changes are merged back
to the main project directory.

Example usage:
    manager = WorktreeManager(project_dir)
    try:
        # Create worktrees for parallel tasks
        wt1 = manager.create_worktree("task-1")
        wt2 = manager.create_worktree("task-2")

        # Workers operate in their worktrees...
        # ...

        # Merge changes back
        manager.merge_worktree(wt1, "Implement task 1")
        manager.merge_worktree(wt2, "Implement task 2")
    finally:
        # Always cleanup
        manager.cleanup_worktrees()
"""

import logging
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WorktreeError(Exception):
    """Raised when a worktree operation fails."""

    pass


@dataclass
class WorktreeInfo:
    """Information about a created worktree."""

    path: Path
    suffix: str
    branch: Optional[str] = None
    commit: Optional[str] = None


class WorktreeManager:
    """Manages git worktrees for parallel worker execution.

    Worktrees are created as siblings to the project directory:
        project/
        project-worker-abc123/
        project-worker-def456/

    This ensures workers have isolated working directories while sharing
    the same git history.
    """

    def __init__(self, project_dir: Path):
        """Initialize worktree manager.

        Args:
            project_dir: Root directory of the project (must be a git repo)

        Raises:
            WorktreeError: If project_dir is not a git repository
        """
        self.project_dir = Path(project_dir).resolve()
        self.worktrees: list[WorktreeInfo] = []

        # Verify it's a git repository
        if not self._is_git_repo():
            raise WorktreeError(
                f"'{self.project_dir}' is not a git repository. "
                "Worktrees require git."
            )

    def _is_git_repo(self) -> bool:
        """Check if the project directory is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _get_current_commit(self) -> str:
        """Get the current HEAD commit hash."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def create_worktree(self, suffix: str = None) -> Path:
        """Create a new worktree for a worker.

        Creates a worktree at a sibling directory to the project, based on
        the current HEAD commit.

        Args:
            suffix: Optional suffix for the worktree name. If not provided,
                    a random UUID prefix is used.

        Returns:
            Path to the created worktree directory

        Raises:
            WorktreeError: If worktree creation fails
        """
        suffix = suffix or str(uuid.uuid4())[:8]
        worktree_path = self.project_dir.parent / f"{self.project_dir.name}-worker-{suffix}"

        # Don't create if it already exists
        if worktree_path.exists():
            raise WorktreeError(
                f"Worktree path '{worktree_path}' already exists. "
                "Use a different suffix or cleanup existing worktrees."
            )

        try:
            # Create worktree at HEAD
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "HEAD"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                check=True,
            )

            commit = self._get_current_commit()
            info = WorktreeInfo(
                path=worktree_path,
                suffix=suffix,
                commit=commit,
            )
            self.worktrees.append(info)

            logger.info(f"Created worktree at {worktree_path} (commit: {commit[:8]})")
            return worktree_path

        except subprocess.CalledProcessError as e:
            raise WorktreeError(
                f"Failed to create worktree: {e.stderr}"
            ) from e

    def remove_worktree(self, worktree_path: Path, force: bool = False) -> bool:
        """Remove a single worktree.

        Args:
            worktree_path: Path to the worktree to remove
            force: If True, force removal even with uncommitted changes

        Returns:
            True if successful
        """
        worktree_path = Path(worktree_path).resolve()

        try:
            cmd = ["git", "worktree", "remove", str(worktree_path)]
            if force:
                cmd.append("--force")

            subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                check=True,
            )

            # Remove from tracked list
            self.worktrees = [
                wt for wt in self.worktrees
                if wt.path != worktree_path
            ]

            logger.info(f"Removed worktree at {worktree_path}")
            return True

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to remove worktree {worktree_path}: {e.stderr}")
            return False

    def cleanup_worktrees(self, force: bool = True) -> int:
        """Remove all created worktrees.

        Args:
            force: If True, force removal even with uncommitted changes

        Returns:
            Number of worktrees successfully removed
        """
        removed = 0
        for wt in list(self.worktrees):
            if self.remove_worktree(wt.path, force=force):
                removed += 1

        # Also prune any stale worktrees
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(self.project_dir),
                capture_output=True,
                check=False,
            )
        except Exception as e:
            logger.warning(f"Failed to prune worktrees: {e}")

        return removed

    def merge_worktree(
        self,
        worktree_path: Path,
        commit_message: str,
        allow_empty: bool = True,
    ) -> Optional[str]:
        """Merge changes from a worktree back to main project.

        This:
        1. Commits any uncommitted changes in the worktree
        2. Gets the commit hash
        3. Cherry-picks the commit into the main project

        Args:
            worktree_path: Path to the worktree
            commit_message: Commit message for the changes
            allow_empty: If True, create empty commit if no changes

        Returns:
            The cherry-picked commit hash, or None if no changes

        Raises:
            WorktreeError: If merge fails
        """
        worktree_path = Path(worktree_path).resolve()

        try:
            # Stage all changes in worktree
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(worktree_path),
                check=True,
                capture_output=True,
            )

            # Check if there are changes to commit
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                check=True,
            )

            if not status_result.stdout.strip() and not allow_empty:
                logger.info(f"No changes in worktree {worktree_path}")
                return None

            # Commit changes
            commit_cmd = ["git", "commit", "-m", commit_message]
            if allow_empty:
                commit_cmd.append("--allow-empty")

            subprocess.run(
                commit_cmd,
                cwd=str(worktree_path),
                capture_output=True,
                check=True,
            )

            # Get the commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                check=True,
            )
            commit_hash = result.stdout.strip()

            # Cherry-pick into main project
            # Use --allow-empty to handle empty commits (when no actual file changes)
            cherry_pick_result = subprocess.run(
                ["git", "cherry-pick", "--allow-empty", commit_hash],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
            )

            if cherry_pick_result.returncode != 0:
                # If cherry-pick fails, it might be because there are no changes
                # (e.g., same commit content). Try to abort and return None.
                if "empty" in cherry_pick_result.stderr.lower():
                    subprocess.run(
                        ["git", "cherry-pick", "--abort"],
                        cwd=str(self.project_dir),
                        capture_output=True,
                    )
                    logger.info(
                        f"Worktree {worktree_path.name} had no unique changes to merge"
                    )
                    return commit_hash  # Still return the commit hash
                else:
                    raise WorktreeError(
                        f"Failed to cherry-pick: {cherry_pick_result.stderr}"
                    )

            logger.info(
                f"Merged worktree {worktree_path.name} "
                f"(commit: {commit_hash[:8]})"
            )
            return commit_hash

        except subprocess.CalledProcessError as e:
            raise WorktreeError(
                f"Failed to merge worktree: {e.stderr}"
            ) from e

    def get_worktree_status(self, worktree_path: Path) -> dict:
        """Get the git status of a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            Dict with status information
        """
        worktree_path = Path(worktree_path).resolve()

        try:
            # Get status
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                check=True,
            )

            # Get current commit
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                check=True,
            )

            lines = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []

            return {
                "path": str(worktree_path),
                "commit": commit_result.stdout.strip(),
                "has_changes": len(lines) > 0,
                "changed_files": len(lines),
                "status_lines": lines,
            }

        except subprocess.CalledProcessError as e:
            return {
                "path": str(worktree_path),
                "error": str(e),
            }

    def list_worktrees(self) -> list[dict]:
        """List all worktrees for this repository.

        Returns:
            List of worktree information dicts
        """
        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                check=True,
            )

            worktrees = []
            current = {}

            for line in result.stdout.strip().split("\n"):
                if not line:
                    if current:
                        worktrees.append(current)
                        current = {}
                    continue

                if line.startswith("worktree "):
                    current["path"] = line[9:]
                elif line.startswith("HEAD "):
                    current["commit"] = line[5:]
                elif line.startswith("branch "):
                    current["branch"] = line[7:]
                elif line == "detached":
                    current["detached"] = True

            if current:
                worktrees.append(current)

            return worktrees

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list worktrees: {e}")
            return []

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup worktrees."""
        self.cleanup_worktrees(force=True)
        return False
