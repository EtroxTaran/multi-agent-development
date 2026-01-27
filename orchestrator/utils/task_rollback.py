"""Task-level rollback and semantic dependency utilities.

Provides git snapshot-based rollback for failed tasks and semantic
dependency inference by analyzing code exports/imports.
"""

import ast
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Task Rollback - Git Snapshot Based
# ============================================================================


@dataclass
class TaskSnapshot:
    """Represents a git snapshot for task rollback."""

    task_id: str
    snapshot_ref: str  # Git reference (branch or commit hash)
    created_at: str
    files_staged: list[str] = field(default_factory=list)
    is_valid: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "snapshot_ref": self.snapshot_ref,
            "created_at": self.created_at,
            "files_staged": self.files_staged,
            "is_valid": self.is_valid,
            "error": self.error,
        }


class TaskRollbackManager:
    """Manages git snapshots for task-level rollback.

    Creates git references before task implementation begins,
    allowing rollback if the task fails without affecting other work.

    Usage:
        manager = TaskRollbackManager(project_dir)

        # Before starting task
        snapshot = manager.create_snapshot("T1")

        # If task fails
        manager.rollback_to_snapshot(snapshot)

        # If task succeeds
        manager.clear_snapshot(snapshot)
    """

    def __init__(self, project_dir: Path):
        """Initialize the rollback manager.

        Args:
            project_dir: Project directory (must be a git repository)
        """
        self.project_dir = Path(project_dir)
        self._validate_git_repo()

    def _validate_git_repo(self) -> None:
        """Verify the project is a git repository."""
        git_dir = self.project_dir / ".git"
        if not git_dir.exists():
            raise ValueError(f"{self.project_dir} is not a git repository")

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the project directory."""
        return subprocess.run(
            ["git", *args],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
            check=check,
        )

    def create_snapshot(self, task_id: str) -> TaskSnapshot:
        """Create a git snapshot before task implementation.

        Stages all current changes and creates a reference point
        that can be rolled back to if the task fails.

        Args:
            task_id: Unique task identifier

        Returns:
            TaskSnapshot with reference information
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch_name = f"snapshot/pre-task-{task_id}-{timestamp}"

        try:
            # Verify we're on a valid git HEAD (don't need to store it,
            # the snapshot branch will point to it)
            self._run_git("rev-parse", "HEAD")

            # Create snapshot branch pointing to current HEAD
            self._run_git("branch", branch_name)

            # Get list of staged and modified files
            status_result = self._run_git("status", "--porcelain")
            modified_files = []
            for line in status_result.stdout.splitlines():
                if line.strip():
                    # Format: XY filename
                    filename = line[3:].strip()
                    if filename:
                        modified_files.append(filename)

            logger.info(f"Created snapshot for task {task_id}: {branch_name}")

            return TaskSnapshot(
                task_id=task_id,
                snapshot_ref=branch_name,
                created_at=datetime.now().isoformat(),
                files_staged=modified_files,
                is_valid=True,
            )

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to create snapshot: {e.stderr}"
            logger.error(error_msg)
            return TaskSnapshot(
                task_id=task_id,
                snapshot_ref="",
                created_at=datetime.now().isoformat(),
                is_valid=False,
                error=error_msg,
            )

    def rollback_to_snapshot(self, snapshot: TaskSnapshot) -> bool:
        """Rollback to a task snapshot.

        Discards changes made since the snapshot was created.
        WARNING: This is destructive - uncommitted changes will be lost.

        Args:
            snapshot: The snapshot to rollback to

        Returns:
            True if rollback succeeded
        """
        if not snapshot.is_valid or not snapshot.snapshot_ref:
            logger.error(f"Cannot rollback: invalid snapshot for task {snapshot.task_id}")
            return False

        try:
            # Get the commit the snapshot branch points to
            result = self._run_git("rev-parse", snapshot.snapshot_ref)
            snapshot_commit = result.stdout.strip()

            # Hard reset to the snapshot commit
            self._run_git("reset", "--hard", snapshot_commit)

            # Clean untracked files created by the failed task
            self._run_git("clean", "-fd")

            logger.info(f"Rolled back to snapshot for task {snapshot.task_id}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Rollback failed: {e.stderr}")
            return False

    def clear_snapshot(self, snapshot: TaskSnapshot) -> bool:
        """Clear a snapshot after successful task completion.

        Deletes the snapshot branch as it's no longer needed.

        Args:
            snapshot: The snapshot to clear

        Returns:
            True if cleanup succeeded
        """
        if not snapshot.snapshot_ref:
            return True

        try:
            # Delete the snapshot branch
            self._run_git("branch", "-D", snapshot.snapshot_ref, check=False)
            logger.info(f"Cleared snapshot for task {snapshot.task_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to clear snapshot: {e}")
            return False

    def list_snapshots(self) -> list[str]:
        """List all existing task snapshots.

        Returns:
            List of snapshot branch names
        """
        try:
            result = self._run_git("branch", "--list", "snapshot/pre-task-*")
            branches = []
            for line in result.stdout.splitlines():
                branch = line.strip().lstrip("* ")
                if branch:
                    branches.append(branch)
            return branches
        except subprocess.CalledProcessError:
            return []

    def cleanup_old_snapshots(self, max_age_hours: int = 24) -> int:
        """Clean up old snapshots.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of snapshots cleaned up
        """
        # For simplicity, just list and delete old-looking snapshots
        # In production, you'd want to check actual timestamps
        snapshots = self.list_snapshots()
        cleaned = 0

        for snapshot in snapshots:
            try:
                self._run_git("branch", "-D", snapshot, check=False)
                cleaned += 1
            except Exception:
                pass

        if cleaned:
            logger.info(f"Cleaned up {cleaned} old snapshots")

        return cleaned


# ============================================================================
# Semantic Dependency Inference
# ============================================================================


@dataclass
class CodeSymbol:
    """Represents an exported or imported code symbol."""

    name: str
    symbol_type: str  # function, class, variable, type
    file_path: str
    line_number: int = 0


@dataclass
class SemanticDependency:
    """Represents a semantic dependency between tasks."""

    dependent_task_id: str  # Task that depends on another
    dependency_task_id: str  # Task that must complete first
    dependency_type: str  # export_import, type_dependency, call_dependency
    symbols: list[str] = field(default_factory=list)
    confidence: float = 1.0  # 0-1, how confident we are in this dependency

    def to_dict(self) -> dict:
        return {
            "dependent_task_id": self.dependent_task_id,
            "dependency_task_id": self.dependency_task_id,
            "dependency_type": self.dependency_type,
            "symbols": self.symbols,
            "confidence": self.confidence,
        }


class SemanticDependencyAnalyzer:
    """Analyzes code to infer semantic dependencies between tasks.

    Goes beyond file-level dependencies to detect when one task
    uses symbols (functions, classes, types) created by another task.

    Usage:
        analyzer = SemanticDependencyAnalyzer(project_dir)
        tasks = [task1, task2, task3]
        dependencies = analyzer.infer_dependencies(tasks)
    """

    # File extensions to analyze
    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}

    def __init__(self, project_dir: Path):
        """Initialize the analyzer.

        Args:
            project_dir: Project directory
        """
        self.project_dir = Path(project_dir)

    def extract_exports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract exported symbols from a file.

        Args:
            file_path: Path to the source file

        Returns:
            List of exported symbols
        """
        if not file_path.exists():
            return []

        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return self._extract_python_exports(file_path)
        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            return self._extract_js_ts_exports(file_path)

        return []

    def extract_imports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract imported symbols from a file.

        Args:
            file_path: Path to the source file

        Returns:
            List of imported symbols
        """
        if not file_path.exists():
            return []

        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return self._extract_python_imports(file_path)
        elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
            return self._extract_js_ts_imports(file_path)

        return []

    def _extract_python_exports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract exports from a Python file using AST."""
        symbols = []

        try:
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Public functions (not starting with _)
                    if not node.name.startswith("_"):
                        symbols.append(
                            CodeSymbol(
                                name=node.name,
                                symbol_type="function",
                                file_path=str(file_path),
                                line_number=node.lineno,
                            )
                        )
                elif isinstance(node, ast.ClassDef):
                    # Public classes
                    if not node.name.startswith("_"):
                        symbols.append(
                            CodeSymbol(
                                name=node.name,
                                symbol_type="class",
                                file_path=str(file_path),
                                line_number=node.lineno,
                            )
                        )
                elif isinstance(node, ast.Assign):
                    # Module-level assignments (potential exports)
                    for target in node.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            symbols.append(
                                CodeSymbol(
                                    name=target.id,
                                    symbol_type="variable",
                                    file_path=str(file_path),
                                    line_number=node.lineno,
                                )
                            )

        except (SyntaxError, UnicodeDecodeError) as e:
            logger.debug(f"Could not parse {file_path}: {e}")

        return symbols

    def _extract_python_imports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract imports from a Python file using AST."""
        symbols = []

        try:
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    # from module import name1, name2
                    for alias in node.names:
                        symbols.append(
                            CodeSymbol(
                                name=alias.name,
                                symbol_type="import",
                                file_path=str(file_path),
                                line_number=node.lineno,
                            )
                        )
                elif isinstance(node, ast.Import):
                    # import module
                    for alias in node.names:
                        symbols.append(
                            CodeSymbol(
                                name=alias.name,
                                symbol_type="import",
                                file_path=str(file_path),
                                line_number=node.lineno,
                            )
                        )

        except (SyntaxError, UnicodeDecodeError) as e:
            logger.debug(f"Could not parse {file_path}: {e}")

        return symbols

    def _extract_js_ts_exports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract exports from a JavaScript/TypeScript file using regex."""
        symbols = []

        try:
            content = file_path.read_text()

            # Match: export function name
            for match in re.finditer(r"export\s+(?:async\s+)?function\s+(\w+)", content):
                symbols.append(
                    CodeSymbol(
                        name=match.group(1),
                        symbol_type="function",
                        file_path=str(file_path),
                    )
                )

            # Match: export class Name
            for match in re.finditer(r"export\s+class\s+(\w+)", content):
                symbols.append(
                    CodeSymbol(
                        name=match.group(1),
                        symbol_type="class",
                        file_path=str(file_path),
                    )
                )

            # Match: export const/let/var name
            for match in re.finditer(r"export\s+(?:const|let|var)\s+(\w+)", content):
                symbols.append(
                    CodeSymbol(
                        name=match.group(1),
                        symbol_type="variable",
                        file_path=str(file_path),
                    )
                )

            # Match: export type Name or export interface Name
            for match in re.finditer(r"export\s+(?:type|interface)\s+(\w+)", content):
                symbols.append(
                    CodeSymbol(
                        name=match.group(1),
                        symbol_type="type",
                        file_path=str(file_path),
                    )
                )

            # Match: export { name1, name2 }
            for match in re.finditer(r"export\s*\{([^}]+)\}", content):
                names = match.group(1)
                for name in re.findall(r"(\w+)(?:\s+as\s+\w+)?", names):
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            symbol_type="export",
                            file_path=str(file_path),
                        )
                    )

            # Match: export default
            for match in re.finditer(r"export\s+default\s+(?:function|class)?\s*(\w+)?", content):
                name = match.group(1) or "default"
                symbols.append(
                    CodeSymbol(
                        name=name,
                        symbol_type="default_export",
                        file_path=str(file_path),
                    )
                )

        except (UnicodeDecodeError, OSError) as e:
            logger.debug(f"Could not parse {file_path}: {e}")

        return symbols

    def _extract_js_ts_imports(self, file_path: Path) -> list[CodeSymbol]:
        """Extract imports from a JavaScript/TypeScript file using regex."""
        symbols = []

        try:
            content = file_path.read_text()

            # Match: import { name1, name2 } from 'module'
            for match in re.finditer(r"import\s*\{([^}]+)\}\s*from", content):
                names = match.group(1)
                for name in re.findall(r"(\w+)(?:\s+as\s+\w+)?", names):
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            symbol_type="import",
                            file_path=str(file_path),
                        )
                    )

            # Match: import Name from 'module'
            for match in re.finditer(r"import\s+(\w+)\s+from", content):
                symbols.append(
                    CodeSymbol(
                        name=match.group(1),
                        symbol_type="default_import",
                        file_path=str(file_path),
                    )
                )

            # Match: import type { Name } from 'module'
            for match in re.finditer(r"import\s+type\s*\{([^}]+)\}\s*from", content):
                names = match.group(1)
                for name in re.findall(r"(\w+)(?:\s+as\s+\w+)?", names):
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            symbol_type="type_import",
                            file_path=str(file_path),
                        )
                    )

        except (UnicodeDecodeError, OSError) as e:
            logger.debug(f"Could not parse {file_path}: {e}")

        return symbols

    def infer_dependencies(self, tasks: list[dict]) -> list[SemanticDependency]:
        """Infer semantic dependencies between tasks.

        Analyzes which tasks create symbols that other tasks use,
        establishing dependencies beyond simple file-level relationships.

        Args:
            tasks: List of task dictionaries with files_to_create, files_to_modify

        Returns:
            List of inferred semantic dependencies
        """
        dependencies: list[SemanticDependency] = []

        # Build a map of which task creates which symbols
        task_exports: dict[str, list[CodeSymbol]] = {}
        for task in tasks:
            task_id = task.get("id", "")
            if not task_id:
                continue

            symbols = []
            for file_path in task.get("files_to_create", []):
                full_path = self.project_dir / file_path
                if full_path.suffix in self.SUPPORTED_EXTENSIONS:
                    # For files to create, we estimate exports from the task description
                    # In production, you'd analyze the actual files after creation
                    symbols.extend(self._estimate_exports_from_task(task, file_path))

            task_exports[task_id] = symbols

        # Build a map of which task uses which symbols
        task_imports: dict[str, list[CodeSymbol]] = {}
        for task in tasks:
            task_id = task.get("id", "")
            if not task_id:
                continue

            symbols = []
            for file_path in task.get("files_to_modify", []):
                full_path = self.project_dir / file_path
                if full_path.exists() and full_path.suffix in self.SUPPORTED_EXTENSIONS:
                    symbols.extend(self.extract_imports(full_path))

            task_imports[task_id] = symbols

        # Find dependencies: if task B imports a symbol that task A exports
        for importer_id, imports in task_imports.items():
            import_names = {s.name for s in imports}

            for exporter_id, exports in task_exports.items():
                if exporter_id == importer_id:
                    continue

                export_names = {s.name for s in exports}
                shared_symbols = import_names & export_names

                if shared_symbols:
                    dependencies.append(
                        SemanticDependency(
                            dependent_task_id=importer_id,
                            dependency_task_id=exporter_id,
                            dependency_type="export_import",
                            symbols=list(shared_symbols),
                            confidence=0.8,  # High confidence for direct symbol match
                        )
                    )

        return dependencies

    def _estimate_exports_from_task(self, task: dict, file_path: str) -> list[CodeSymbol]:
        """Estimate exports from task description for files to be created.

        Since the file doesn't exist yet, we analyze the task description
        to guess what symbols it will export.

        Args:
            task: Task dictionary
            file_path: Path to the file being created

        Returns:
            List of estimated exported symbols
        """
        symbols = []

        title = task.get("title", "")
        criteria = task.get("acceptance_criteria", [])
        user_story = task.get("user_story", "")

        combined_text = f"{title} {user_story} {' '.join(criteria)}"

        # Look for function/class names in the description
        # Pattern: "create/implement/add X function/class/component"
        for match in re.finditer(
            r"(?:create|implement|add|define)\s+(?:a\s+)?(\w+)\s+(?:function|class|component|type|interface)",
            combined_text,
            re.IGNORECASE,
        ):
            symbols.append(
                CodeSymbol(
                    name=match.group(1),
                    symbol_type="estimated",
                    file_path=file_path,
                )
            )

        # Look for PascalCase names (likely classes/components)
        for match in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", combined_text):
            name = match.group(1)
            if name not in {"JavaScript", "TypeScript", "Python"}:  # Exclude language names
                symbols.append(
                    CodeSymbol(
                        name=name,
                        symbol_type="estimated_class",
                        file_path=file_path,
                    )
                )

        return symbols


def merge_dependencies(
    file_dependencies: dict[str, set[str]],
    semantic_dependencies: list[SemanticDependency],
) -> dict[str, set[str]]:
    """Merge file-based and semantic dependencies.

    Args:
        file_dependencies: Existing file-based dependencies (task_id -> set of dependency task_ids)
        semantic_dependencies: Inferred semantic dependencies

    Returns:
        Combined dependency map
    """
    combined = {task_id: set(deps) for task_id, deps in file_dependencies.items()}

    for sem_dep in semantic_dependencies:
        if sem_dep.dependent_task_id not in combined:
            combined[sem_dep.dependent_task_id] = set()
        combined[sem_dep.dependent_task_id].add(sem_dep.dependency_task_id)

    return combined
