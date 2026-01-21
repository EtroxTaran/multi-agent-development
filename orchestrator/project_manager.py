"""Project management for the nested orchestration architecture.

This module handles project lifecycle management including:
- Listing projects
- Getting project status
- Spawning worker Claude instances
- Managing project workflow state

Projects are expected to be set up manually with:
- Documents/ folder containing product vision and architecture docs
- Context files (CLAUDE.md, GEMINI.md, .cursor/rules) - provided or generated
- .workflow/ folder for state tracking

File Boundary Enforcement:
The orchestrator can only write to:
- .workflow/**     - Workflow state and phase outputs
- .project-config.json - Project configuration

All other paths must be modified by worker Claude instances.
"""

import concurrent.futures
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .utils.boundaries import (
    ensure_orchestrator_can_write,
    OrchestratorBoundaryError,
)
from .utils.worktree import (
    WorktreeManager,
    WorktreeError,
)

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages projects in the nested orchestration architecture.

    Projects live in the `projects/` directory and each has its own
    context files, workflow state, and application code.
    """

    def __init__(self, root_dir: Path):
        """Initialize project manager.

        Args:
            root_dir: Root directory of meta-architect
        """
        self.root_dir = Path(root_dir).resolve()
        self.projects_dir = self.root_dir / "projects"

    def list_projects(self) -> list[dict]:
        """List all projects.

        Returns:
            List of project info dicts
        """
        if not self.projects_dir.exists():
            return []

        projects = []
        for project_dir in sorted(self.projects_dir.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith('.'):
                continue

            config = self._load_project_config(project_dir)
            state = self._load_project_state(project_dir)

            projects.append({
                "name": project_dir.name,
                "path": str(project_dir),
                "created_at": config.get("created_at") if config else None,
                "current_phase": state.get("current_phase", 0) if state else 0,
                "has_documents": (project_dir / "Documents").exists(),
                "has_product_spec": (project_dir / "PRODUCT.md").exists(),
                "has_claude_md": (project_dir / "CLAUDE.md").exists(),
                "has_gemini_md": (project_dir / "GEMINI.md").exists(),
                "has_cursor_rules": (project_dir / ".cursor" / "rules").exists(),
            })

        return projects

    def get_project(self, name: str = None, path: Path = None) -> Optional[Path]:
        """Get project directory by name or path.

        Supports two modes:
        1. Nested mode: Project name resolves to projects/<name>/
        2. External mode: Absolute path to any directory

        Args:
            name: Project name (for nested projects in projects/)
            path: Absolute path to external project directory

        Returns:
            Path to project directory or None if not found
        """
        if path:
            # External project mode
            external_path = Path(path).resolve()
            if external_path.exists() and external_path.is_dir():
                return external_path
            return None

        if name:
            # Nested project mode (existing behavior)
            project_dir = self.projects_dir / name
            if project_dir.exists() and project_dir.is_dir():
                return project_dir

        return None

    def is_external_project(self, project_dir: Path) -> bool:
        """Check if a project directory is external (not in projects/).

        Args:
            project_dir: Path to project directory

        Returns:
            True if the project is outside the projects/ directory
        """
        project_dir = Path(project_dir).resolve()
        try:
            # Check if it's under projects/
            project_dir.relative_to(self.projects_dir)
            return False
        except ValueError:
            return True

    def init_project(self, name: str) -> dict:
        """Initialize a project directory with basic structure.

        Creates the minimal project structure:
        - Documents/           (for product vision and architecture docs)
        - .workflow/           (for workflow state)
        - .workflow/phases/    (for phase outputs)

        Args:
            name: Project name

        Returns:
            Result dict with success status
        """
        project_dir = self.projects_dir / name

        if project_dir.exists():
            return {
                "success": False,
                "error": f"Project '{name}' already exists"
            }

        try:
            # Create project structure
            project_dir.mkdir(parents=True)
            (project_dir / "Documents").mkdir()
            (project_dir / ".workflow").mkdir()
            (project_dir / ".workflow" / "phases").mkdir()

            # Create initial config
            config = {
                "project_name": name,
                "created_at": datetime.now().isoformat(),
            }

            config_path = project_dir / ".project-config.json"
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            return {
                "success": True,
                "project_dir": str(project_dir),
                "message": f"Project '{name}' initialized. Add your Documents/ and context files."
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def spawn_worker_claude(
        self,
        project_name: str,
        prompt: str,
        allowed_tools: Optional[list[str]] = None,
        max_turns: Optional[int] = None,
        timeout: int = 600
    ) -> dict:
        """Spawn a worker Claude instance inside a project directory.

        This is used during Phase 3 (Implementation) to have a separate
        Claude instance write the application code.

        Args:
            project_name: Name of the project
            prompt: Prompt for the worker Claude
            allowed_tools: List of allowed tools (default: Read, Write, Edit, Bash)
            max_turns: Maximum turns for the worker
            timeout: Timeout in seconds

        Returns:
            Result dict with worker output
        """
        project_dir = self.get_project(project_name)
        if not project_dir:
            return {
                "success": False,
                "error": f"Project '{project_name}' not found"
            }

        # Build command
        cmd = ["claude", "-p", prompt, "--output-format", "json"]

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        else:
            # Default tools for implementation
            default_tools = [
                "Read", "Write", "Edit",
                "Bash(npm*)", "Bash(pytest*)", "Bash(python*)",
                "Bash(ls*)", "Bash(mkdir*)"
            ]
            cmd.extend(["--allowedTools", ",".join(default_tools)])

        if max_turns:
            cmd.extend(["--max-turns", str(max_turns)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_dir),
                timeout=timeout
            )

            # Try to parse JSON output
            output = result.stdout
            try:
                output_json = json.loads(output)
            except json.JSONDecodeError:
                output_json = {"raw_output": output}

            return {
                "success": result.returncode == 0,
                "output": output_json,
                "stderr": result.stderr if result.stderr else None
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Worker Claude timed out after {timeout} seconds"
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Claude CLI not found. Install with: npm install -g @anthropic/claude-cli"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_project_status(self, name: str) -> dict:
        """Get detailed status for a project.

        Args:
            name: Project name

        Returns:
            Status dict with phase information
        """
        project_dir = self.get_project(name)
        if not project_dir:
            return {"error": f"Project '{name}' not found"}

        config = self._load_project_config(project_dir)
        state = self._load_project_state(project_dir)

        # Check which files exist
        files_status = {
            "Documents/": (project_dir / "Documents").exists(),
            "PRODUCT.md": (project_dir / "PRODUCT.md").exists(),
            "CLAUDE.md": (project_dir / "CLAUDE.md").exists(),
            "GEMINI.md": (project_dir / "GEMINI.md").exists(),
            ".cursor/rules": (project_dir / ".cursor" / "rules").exists(),
        }

        # Check phase outputs
        phases_status = {}
        for phase in ["planning", "validation", "implementation", "verification", "completion"]:
            phase_dir = project_dir / ".workflow" / "phases" / phase
            phases_status[phase] = {
                "exists": phase_dir.exists(),
                "has_output": bool(list(phase_dir.glob("*"))) if phase_dir.exists() else False
            }

        return {
            "name": name,
            "path": str(project_dir),
            "config": config,
            "state": state,
            "files": files_status,
            "phases": phases_status
        }

    def _load_project_config(self, project_dir: Path) -> Optional[dict]:
        """Load project configuration.

        Args:
            project_dir: Path to project directory

        Returns:
            Config dict or None
        """
        config_path = project_dir / ".project-config.json"
        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _load_project_state(self, project_dir: Path) -> Optional[dict]:
        """Load project workflow state.

        Args:
            project_dir: Path to project directory

        Returns:
            State dict or None
        """
        state_path = project_dir / ".workflow" / "state.json"
        if not state_path.exists():
            return None

        try:
            with open(state_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def update_project_state(self, name: str, updates: dict) -> bool:
        """Update project workflow state.

        Args:
            name: Project name
            updates: Dict of updates to apply

        Returns:
            True if successful

        Raises:
            OrchestratorBoundaryError: If write violates boundaries (shouldn't happen
                for state.json but enforced for safety)
        """
        project_dir = self.get_project(name)
        if not project_dir:
            return False

        state_path = project_dir / ".workflow" / "state.json"

        # Validate boundary (should always pass for .workflow/)
        ensure_orchestrator_can_write(project_dir, state_path)

        # Ensure .workflow directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)

        state = self._load_project_state(project_dir) or {}

        # Apply updates
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()

        try:
            with open(state_path, "w") as f:
                json.dump(state, f, indent=2)
            return True
        except IOError:
            return False

    def safe_write_workflow_file(
        self,
        project_name: str,
        relative_path: str,
        content: str | dict,
    ) -> bool:
        """Safely write a file within .workflow/ directory.

        This method enforces boundary checks and ensures the orchestrator
        only writes to allowed paths.

        Args:
            project_name: Project name
            relative_path: Path relative to .workflow/ (e.g., "phases/planning/plan.json")
            content: Content to write (string or dict to be JSON-encoded)

        Returns:
            True if successful

        Raises:
            OrchestratorBoundaryError: If the write would violate boundaries
        """
        project_dir = self.get_project(project_name)
        if not project_dir:
            return False

        # Construct full path
        target_path = project_dir / ".workflow" / relative_path

        # Validate boundary
        ensure_orchestrator_can_write(project_dir, target_path)

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        try:
            if isinstance(content, dict):
                with open(target_path, "w") as f:
                    json.dump(content, f, indent=2)
            else:
                with open(target_path, "w") as f:
                    f.write(content)
            return True
        except IOError:
            return False

    def safe_write_project_config(
        self,
        project_name: str,
        config: dict,
    ) -> bool:
        """Safely write the .project-config.json file.

        Args:
            project_name: Project name
            config: Configuration dict

        Returns:
            True if successful

        Raises:
            OrchestratorBoundaryError: If the write would violate boundaries
        """
        project_dir = self.get_project(project_name)
        if not project_dir:
            return False

        target_path = project_dir / ".project-config.json"

        # Validate boundary
        ensure_orchestrator_can_write(project_dir, target_path)

        try:
            with open(target_path, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except IOError:
            return False

    def spawn_parallel_workers(
        self,
        project_name: str,
        tasks: list[dict],
        max_workers: int = 3,
        timeout: int = 600,
    ) -> list[dict]:
        """Spawn multiple workers in parallel using git worktrees.

        Each task is executed in an isolated git worktree, allowing multiple
        workers to operate simultaneously without file conflicts. Changes
        are merged back sequentially after completion.

        Args:
            project_name: Project name
            tasks: List of task dictionaries with prompt and metadata
            max_workers: Maximum number of parallel workers
            timeout: Timeout per worker in seconds

        Returns:
            List of result dictionaries for each task

        Note:
            This is an experimental feature. The project must be a git
            repository for worktrees to work.
        """
        project_dir = self.get_project(project_name)
        if not project_dir:
            return [{"success": False, "error": "Project not found"}]

        try:
            wt_manager = WorktreeManager(project_dir)
        except WorktreeError as e:
            return [{"success": False, "error": str(e)}]

        results = []

        try:
            # Limit tasks to max_workers
            tasks_to_run = tasks[:max_workers]
            worktrees = []

            # Create worktrees for each task
            for i, task in enumerate(tasks_to_run):
                try:
                    task_id = task.get("id", f"task-{i}")
                    worktree = wt_manager.create_worktree(f"{task_id}")
                    worktrees.append((worktree, task))
                except WorktreeError as e:
                    logger.error(f"Failed to create worktree for task {i}: {e}")
                    results.append({
                        "task_id": task.get("id"),
                        "success": False,
                        "error": str(e),
                    })

            # Execute tasks in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                for worktree, task in worktrees:
                    prompt = task.get("prompt", "")
                    future = executor.submit(
                        self._run_worker_in_worktree,
                        worktree,
                        prompt,
                        task.get("id", "unknown"),
                        timeout,
                    )
                    futures[future] = (worktree, task)

                # Collect results
                for future in concurrent.futures.as_completed(futures):
                    worktree, task = futures[future]
                    try:
                        result = future.result()
                        result["task_id"] = task.get("id")
                        results.append(result)

                        # Merge changes if successful
                        if result.get("success"):
                            try:
                                commit_msg = f"Task: {task.get('title', task.get('id', 'unknown'))}"
                                commit_hash = wt_manager.merge_worktree(worktree, commit_msg)
                                result["commit_hash"] = commit_hash
                            except WorktreeError as e:
                                logger.error(f"Failed to merge worktree: {e}")
                                result["merge_error"] = str(e)

                    except Exception as e:
                        logger.error(f"Worker failed: {e}")
                        results.append({
                            "task_id": task.get("id"),
                            "success": False,
                            "error": str(e),
                        })

        finally:
            # Always cleanup worktrees
            wt_manager.cleanup_worktrees()

        return results

    def _run_worker_in_worktree(
        self,
        worktree_path: Path,
        prompt: str,
        task_id: str,
        timeout: int,
    ) -> dict:
        """Run a worker Claude instance in a worktree.

        Args:
            worktree_path: Path to the worktree
            prompt: Prompt for the worker
            task_id: Task identifier
            timeout: Timeout in seconds

        Returns:
            Result dictionary
        """
        # Build command
        cmd = ["claude", "-p", prompt, "--output-format", "json"]

        # Default tools for implementation
        default_tools = [
            "Read", "Write", "Edit",
            "Bash(npm*)", "Bash(pytest*)", "Bash(python*)",
            "Bash(ls*)", "Bash(mkdir*)"
        ]
        cmd.extend(["--allowedTools", ",".join(default_tools)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(worktree_path),
                timeout=timeout
            )

            # Try to parse JSON output
            output = result.stdout
            try:
                output_json = json.loads(output)
            except json.JSONDecodeError:
                output_json = {"raw_output": output}

            return {
                "success": result.returncode == 0,
                "output": output_json,
                "stderr": result.stderr if result.stderr else None,
                "worktree": str(worktree_path),
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Worker timed out after {timeout} seconds",
                "worktree": str(worktree_path),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Claude CLI not found",
                "worktree": str(worktree_path),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "worktree": str(worktree_path),
            }
