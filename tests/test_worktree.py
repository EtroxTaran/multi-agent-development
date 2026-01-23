"""Tests for git worktree management."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from orchestrator.utils.worktree import WorktreeError, WorktreeInfo, WorktreeManager


@pytest.fixture
def git_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "test-repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=str(repo_dir),
            capture_output=True,
            check=True,
        )

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo_dir),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(repo_dir),
            capture_output=True,
            check=True,
        )

        # Create initial commit
        test_file = repo_dir / "README.md"
        test_file.write_text("# Test Repository\n")

        subprocess.run(
            ["git", "add", "."],
            cwd=str(repo_dir),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(repo_dir),
            capture_output=True,
            check=True,
        )

        yield repo_dir


@pytest.fixture
def non_git_dir():
    """Create a temporary non-git directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestWorktreeManagerInit:
    """Tests for WorktreeManager initialization."""

    def test_init_with_git_repo(self, git_repo):
        """WorktreeManager initializes with a git repository."""
        manager = WorktreeManager(git_repo)
        assert manager.project_dir == git_repo
        assert manager.worktrees == []

    def test_init_with_non_git_dir(self, non_git_dir):
        """WorktreeManager raises error for non-git directory."""
        with pytest.raises(WorktreeError) as exc_info:
            WorktreeManager(non_git_dir)
        assert "not a git repository" in str(exc_info.value)


class TestCreateWorktree:
    """Tests for worktree creation."""

    def test_create_worktree(self, git_repo):
        """Creates a worktree successfully."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("test-1")

            assert worktree_path.exists()
            assert worktree_path.name == f"{git_repo.name}-worker-test-1"
            assert len(manager.worktrees) == 1
            assert manager.worktrees[0].path == worktree_path
        finally:
            manager.cleanup_worktrees()

    def test_create_worktree_auto_suffix(self, git_repo):
        """Creates worktree with auto-generated suffix."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree()

            assert worktree_path.exists()
            assert "worker" in worktree_path.name
        finally:
            manager.cleanup_worktrees()

    def test_create_multiple_worktrees(self, git_repo):
        """Creates multiple worktrees."""
        manager = WorktreeManager(git_repo)

        try:
            wt1 = manager.create_worktree("task-1")
            wt2 = manager.create_worktree("task-2")

            assert wt1.exists()
            assert wt2.exists()
            assert wt1 != wt2
            assert len(manager.worktrees) == 2
        finally:
            manager.cleanup_worktrees()

    def test_create_duplicate_worktree_fails(self, git_repo):
        """Creating worktree with same suffix fails."""
        manager = WorktreeManager(git_repo)

        try:
            manager.create_worktree("same")
            with pytest.raises(WorktreeError) as exc_info:
                manager.create_worktree("same")
            assert "already exists" in str(exc_info.value)
        finally:
            manager.cleanup_worktrees()


class TestRemoveWorktree:
    """Tests for worktree removal."""

    def test_remove_worktree(self, git_repo):
        """Removes a worktree successfully."""
        manager = WorktreeManager(git_repo)
        worktree_path = manager.create_worktree("remove-test")

        assert worktree_path.exists()
        result = manager.remove_worktree(worktree_path)

        assert result is True
        assert not worktree_path.exists()
        assert len(manager.worktrees) == 0

    def test_remove_nonexistent_worktree(self, git_repo):
        """Removing nonexistent worktree returns False."""
        manager = WorktreeManager(git_repo)
        fake_path = git_repo.parent / "nonexistent-worktree"

        result = manager.remove_worktree(fake_path)
        assert result is False


class TestCleanupWorktrees:
    """Tests for cleanup functionality."""

    def test_cleanup_all_worktrees(self, git_repo):
        """Cleans up all created worktrees."""
        manager = WorktreeManager(git_repo)

        # Create multiple worktrees
        wt1 = manager.create_worktree("cleanup-1")
        wt2 = manager.create_worktree("cleanup-2")
        wt3 = manager.create_worktree("cleanup-3")

        assert wt1.exists()
        assert wt2.exists()
        assert wt3.exists()

        removed = manager.cleanup_worktrees()

        assert removed == 3
        assert not wt1.exists()
        assert not wt2.exists()
        assert not wt3.exists()
        assert len(manager.worktrees) == 0

    def test_context_manager_cleanup(self, git_repo):
        """Context manager cleans up on exit."""
        worktree_path = None

        with WorktreeManager(git_repo) as manager:
            worktree_path = manager.create_worktree("context-test")
            assert worktree_path.exists()

        # Should be cleaned up after context exit
        assert not worktree_path.exists()


class TestMergeWorktree:
    """Tests for merging worktree changes."""

    def test_merge_worktree_with_changes(self, git_repo):
        """Merges worktree changes back to main."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("merge-test")

            # Make changes in worktree
            new_file = worktree_path / "new_feature.py"
            new_file.write_text("# New feature\nprint('hello')\n")

            # Merge changes
            commit_hash = manager.merge_worktree(worktree_path, "Add new feature")

            assert commit_hash is not None
            assert len(commit_hash) == 40  # Full SHA

            # Verify change is in main repo
            assert (git_repo / "new_feature.py").exists()

        finally:
            manager.cleanup_worktrees()

    def test_merge_worktree_no_changes(self, git_repo):
        """Merging worktree with no changes creates empty commit if allowed."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("no-changes")

            # Merge without making changes (allow_empty=True by default)
            commit_hash = manager.merge_worktree(worktree_path, "Empty commit")

            assert commit_hash is not None

        finally:
            manager.cleanup_worktrees()

    def test_merge_worktree_no_changes_not_allowed(self, git_repo):
        """Returns None when no changes and allow_empty=False."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("no-changes-strict")

            # Merge without making changes
            commit_hash = manager.merge_worktree(
                worktree_path, "Should not create commit", allow_empty=False
            )

            assert commit_hash is None

        finally:
            manager.cleanup_worktrees()


class TestWorktreeStatus:
    """Tests for worktree status checking."""

    def test_get_worktree_status_clean(self, git_repo):
        """Gets status of a clean worktree."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("status-clean")
            status = manager.get_worktree_status(worktree_path)

            assert status["path"] == str(worktree_path)
            assert status["has_changes"] is False
            assert status["changed_files"] == 0
            assert "commit" in status

        finally:
            manager.cleanup_worktrees()

    def test_get_worktree_status_with_changes(self, git_repo):
        """Gets status of worktree with changes."""
        manager = WorktreeManager(git_repo)

        try:
            worktree_path = manager.create_worktree("status-dirty")

            # Make changes
            new_file = worktree_path / "untracked.txt"
            new_file.write_text("untracked content")

            status = manager.get_worktree_status(worktree_path)

            assert status["has_changes"] is True
            assert status["changed_files"] > 0

        finally:
            manager.cleanup_worktrees()


class TestListWorktrees:
    """Tests for listing worktrees."""

    def test_list_worktrees(self, git_repo):
        """Lists all worktrees for repository."""
        manager = WorktreeManager(git_repo)

        try:
            manager.create_worktree("list-1")
            manager.create_worktree("list-2")

            worktrees = manager.list_worktrees()

            # Should include main worktree + 2 created
            assert len(worktrees) >= 2

            # Check structure
            for wt in worktrees:
                assert "path" in wt
                assert "commit" in wt

        finally:
            manager.cleanup_worktrees()


class TestWorktreeInfo:
    """Tests for WorktreeInfo dataclass."""

    def test_worktree_info_creation(self):
        """WorktreeInfo stores worktree metadata."""
        info = WorktreeInfo(
            path=Path("/tmp/test"),
            suffix="test-1",
            branch="feature-branch",
            commit="abc123",
        )

        assert info.path == Path("/tmp/test")
        assert info.suffix == "test-1"
        assert info.branch == "feature-branch"
        assert info.commit == "abc123"

    def test_worktree_info_defaults(self):
        """WorktreeInfo has sensible defaults."""
        info = WorktreeInfo(
            path=Path("/tmp/test"),
            suffix="test-1",
        )

        assert info.branch is None
        assert info.commit is None


class TestWorktreeError:
    """Tests for WorktreeError exception."""

    def test_worktree_error_message(self):
        """WorktreeError stores message."""
        error = WorktreeError("Test error message")
        assert str(error) == "Test error message"

    def test_worktree_error_is_exception(self):
        """WorktreeError is an Exception."""
        error = WorktreeError("Test")
        assert isinstance(error, Exception)
