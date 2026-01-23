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
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy(str, Enum):
    """Strategy for handling merge conflicts during worktree merging.

    Attributes:
        ABORT: Fail immediately on conflict (default, safest)
        OURS: Accept worktree changes, discard main branch changes
        THEIRS: Accept main branch changes, discard worktree changes
        QUEUE: Queue for sequential merge (caller handles manually)
    """

    ABORT = "abort"
    OURS = "ours"
    THEIRS = "theirs"
    QUEUE = "queue"


class WorktreeError(Exception):
    """Raised when a worktree operation fails."""

    pass


@dataclass
class MergeConflictError(WorktreeError):
    """Raised when a merge conflict occurs during worktree merging.

    Attributes:
        message: Error description
        conflicting_files: List of files with conflicts
        worktree_path: Path to the worktree that caused the conflict
        commit_hash: The commit hash that couldn't be merged
    """

    message: str
    conflicting_files: list[str] = field(default_factory=list)
    worktree_path: Optional[Path] = None
    commit_hash: Optional[str] = None

    def __str__(self) -> str:
        files_str = ", ".join(self.conflicting_files[:5])
        if len(self.conflicting_files) > 5:
            files_str += f"... and {len(self.conflicting_files) - 5} more"
        return f"{self.message}. Conflicting files: [{files_str}]"


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
        self._lock = threading.Lock()  # Thread safety for worktree list operations

        # Verify it's a git repository
        if not self._is_git_repo():
            raise WorktreeError(
                f"'{self.project_dir}' is not a git repository. " "Worktrees require git."
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

        worktree_created = False

        # Use lock to prevent race condition between exists() check and creation
        with self._lock:
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
                worktree_created = True

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
                raise WorktreeError(f"Failed to create worktree: {e.stderr}") from e
            except Exception as e:
                # Clean up orphaned worktree if creation succeeded but setup failed
                if worktree_created and worktree_path.exists():
                    logger.warning(
                        f"Cleaning up orphaned worktree after setup failure: {worktree_path}"
                    )
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", str(worktree_path)],
                            cwd=str(self.project_dir),
                            capture_output=True,
                            check=False,  # Don't raise if cleanup fails
                        )
                    except Exception:
                        pass  # Best-effort cleanup
                raise WorktreeError(f"Failed to setup worktree: {e}") from e

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

            # Remove from tracked list (thread-safe)
            with self._lock:
                self.worktrees = [wt for wt in self.worktrees if wt.path != worktree_path]

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
        # Get a copy of the list under lock for safe iteration
        with self._lock:
            worktrees_copy = list(self.worktrees)
        for wt in worktrees_copy:
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
        conflict_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.ABORT,
    ) -> Optional[str]:
        """Merge changes from a worktree back to main project.

        This:
        1. Commits any uncommitted changes in the worktree
        2. Gets the commit hash
        3. Cherry-picks the commit into the main project
        4. Handles conflicts according to conflict_strategy

        Args:
            worktree_path: Path to the worktree
            commit_message: Commit message for the changes
            allow_empty: If True, create empty commit if no changes
            conflict_strategy: Strategy for handling merge conflicts

        Returns:
            The cherry-picked commit hash, or None if no changes

        Raises:
            WorktreeError: If merge fails
            MergeConflictError: If conflict occurs and strategy is ABORT or QUEUE
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
                    logger.info(f"Worktree {worktree_path.name} had no unique changes to merge")
                    return commit_hash  # Still return the commit hash
                elif (
                    "conflict" in cherry_pick_result.stderr.lower()
                    or "conflict" in cherry_pick_result.stdout.lower()
                ):
                    # Handle conflict based on strategy
                    return self._handle_conflict(
                        worktree_path=worktree_path,
                        commit_hash=commit_hash,
                        conflict_strategy=conflict_strategy,
                        stderr=cherry_pick_result.stderr,
                    )
                else:
                    raise WorktreeError(f"Failed to cherry-pick: {cherry_pick_result.stderr}")

            logger.info(f"Merged worktree {worktree_path.name} " f"(commit: {commit_hash[:8]})")
            return commit_hash

        except subprocess.CalledProcessError as e:
            raise WorktreeError(f"Failed to merge worktree: {e.stderr}") from e

    def _get_conflicting_files(self) -> list[str]:
        """Get list of files with merge conflicts.

        Returns:
            List of conflicting file paths
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            files = result.stdout.strip().split("\n") if result.stdout.strip() else []
            return [f for f in files if f]
        except subprocess.CalledProcessError:
            return []

    def _handle_conflict(
        self,
        worktree_path: Path,
        commit_hash: str,
        conflict_strategy: ConflictResolutionStrategy,
        stderr: str,
    ) -> Optional[str]:
        """Handle a merge conflict based on strategy.

        Args:
            worktree_path: Path to the worktree
            commit_hash: The commit that caused the conflict
            conflict_strategy: Strategy to apply
            stderr: Error output from cherry-pick

        Returns:
            Commit hash if resolved, None otherwise

        Raises:
            MergeConflictError: If strategy is ABORT or QUEUE
        """
        conflicting_files = self._get_conflicting_files()

        if conflict_strategy == ConflictResolutionStrategy.ABORT:
            # Abort cherry-pick and raise error
            subprocess.run(
                ["git", "cherry-pick", "--abort"],
                cwd=str(self.project_dir),
                capture_output=True,
            )
            raise MergeConflictError(
                message=f"Merge conflict occurred for worktree {worktree_path.name}",
                conflicting_files=conflicting_files,
                worktree_path=worktree_path,
                commit_hash=commit_hash,
            )

        elif conflict_strategy == ConflictResolutionStrategy.OURS:
            # Accept worktree changes (ours = the cherry-picked changes)
            logger.info("Resolving conflict with OURS strategy (worktree wins)")
            for file_path in conflicting_files:
                subprocess.run(
                    ["git", "checkout", "--ours", file_path],
                    cwd=str(self.project_dir),
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "add", file_path],
                    cwd=str(self.project_dir),
                    capture_output=True,
                )

            # Continue cherry-pick
            subprocess.run(
                ["git", "cherry-pick", "--continue"],
                cwd=str(self.project_dir),
                capture_output=True,
                env={**subprocess.os.environ, "GIT_EDITOR": "true"},
            )
            logger.info(f"Resolved conflict with OURS strategy for {worktree_path.name}")
            return commit_hash

        elif conflict_strategy == ConflictResolutionStrategy.THEIRS:
            # Accept main branch changes (theirs = current branch)
            logger.info("Resolving conflict with THEIRS strategy (main wins)")
            for file_path in conflicting_files:
                subprocess.run(
                    ["git", "checkout", "--theirs", file_path],
                    cwd=str(self.project_dir),
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "add", file_path],
                    cwd=str(self.project_dir),
                    capture_output=True,
                )

            # Continue cherry-pick
            subprocess.run(
                ["git", "cherry-pick", "--continue"],
                cwd=str(self.project_dir),
                capture_output=True,
                env={**subprocess.os.environ, "GIT_EDITOR": "true"},
            )
            logger.info(f"Resolved conflict with THEIRS strategy for {worktree_path.name}")
            return commit_hash

        elif conflict_strategy == ConflictResolutionStrategy.QUEUE:
            # Queue for manual resolution - abort and raise
            subprocess.run(
                ["git", "cherry-pick", "--abort"],
                cwd=str(self.project_dir),
                capture_output=True,
            )
            raise MergeConflictError(
                message=f"Merge conflict queued for manual resolution: {worktree_path.name}",
                conflicting_files=conflicting_files,
                worktree_path=worktree_path,
                commit_hash=commit_hash,
            )

        return None

    def merge_worktrees_sequential(
        self,
        worktrees: list[tuple[Path, str]],
        conflict_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.ABORT,
    ) -> list[dict]:
        """Merge multiple worktrees sequentially.

        This method merges worktrees one-by-one, allowing for better conflict
        resolution as each merge is applied before the next.

        Args:
            worktrees: List of (worktree_path, commit_message) tuples
            conflict_strategy: Strategy for handling merge conflicts

        Returns:
            List of result dicts with keys: worktree_path, success, commit_hash, error
        """
        results = []

        for worktree_path, commit_message in worktrees:
            result = {
                "worktree_path": str(worktree_path),
                "success": False,
                "commit_hash": None,
                "error": None,
            }

            try:
                commit_hash = self.merge_worktree(
                    worktree_path=worktree_path,
                    commit_message=commit_message,
                    conflict_strategy=conflict_strategy,
                )
                result["success"] = True
                result["commit_hash"] = commit_hash
                logger.info(f"Sequential merge succeeded for {worktree_path}")

            except MergeConflictError as e:
                result["error"] = str(e)
                result["conflicting_files"] = e.conflicting_files
                logger.warning(f"Conflict during sequential merge: {e}")

                # If ABORT strategy, stop the entire sequence
                if conflict_strategy == ConflictResolutionStrategy.ABORT:
                    results.append(result)
                    break

            except WorktreeError as e:
                result["error"] = str(e)
                logger.error(f"Error during sequential merge: {e}")

            results.append(result)

        return results

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

    def cleanup_orphaned_worktrees(self) -> int:
        """Clean up orphaned worktrees from previous runs.

        Scans for worktree directories matching the pattern project-worker-*
        and removes them if they are not currently tracked.

        Returns:
            Number of orphaned worktrees removed
        """
        logger.info("Checking for orphaned worktrees...")

        # Get list of all git worktrees
        git_worktrees = self.list_worktrees()
        git_worktree_paths = {Path(wt["path"]).resolve() for wt in git_worktrees}

        # Identify our main project path to avoid deleting it
        project_path = self.project_dir.resolve()

        # Pattern for our worker worktrees
        worker_pattern = f"{self.project_dir.name}-worker-*"
        parent_dir = self.project_dir.parent

        removed_count = 0

        # Check all matching directories in parent
        for path in parent_dir.glob(worker_pattern):
            path = path.resolve()

            # Skip if it's the project dir itself (unlikely with pattern, but safe)
            if path == project_path:
                continue

            # If it's a directory and looks like one of our workers
            if path.is_dir():
                # Check if git knows about it
                is_known = path in git_worktree_paths

                # If git knows about it, remove it cleanly
                if is_known:
                    logger.info(f"Removing known orphaned worktree: {path}")
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", str(path)],
                            cwd=str(self.project_dir),
                            capture_output=True,
                            check=True,
                        )
                        removed_count += 1
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to remove worktree {path}: {e}")

                # If git doesn't know about it but it exists on disk,
                # it might be a left-over directory.
                # Be careful not to delete random directories.
                # Only delete if it matches our specific UUID pattern length or format
                # For now, we only delete if it WAS a git worktree or we are sure.
                # To be safe, we mainly rely on 'git worktree prune' which is called in cleanup_worktrees
                pass

        # Prune any stale references
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(self.project_dir),
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

        return removed_count

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup worktrees."""
        self.cleanup_worktrees(force=True)
        return False
