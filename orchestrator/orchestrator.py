"""Main orchestrator for the multi-agent workflow.

Supports nested architecture where projects live in projects/<name>/ and
the orchestrator coordinates without directly writing application code.

Uses LangGraph for graph-based workflow execution with native parallelism.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .db.config import DatabaseRequiredError
from .project_manager import ProjectManager
from .storage.workflow_adapter import get_workflow_storage
from .utils.git_operations import GitOperationsManager
from .utils.handoff import generate_handoff
from .utils.log_manager import LogManager, should_auto_cleanup
from .utils.log_manager import load_config as load_log_config
from .utils.logging import LogLevel, OrchestrationLogger


def is_langgraph_enabled() -> bool:
    """Check if LangGraph mode is enabled via environment variable.

    Returns:
        True if ORCHESTRATOR_USE_LANGGRAPH is set to 'true' or '1'
    """
    return os.environ.get("ORCHESTRATOR_USE_LANGGRAPH", "").lower() in ("true", "1")


async def validate_db_connection(project_name: str) -> None:
    """Validate database is available and schema is applied.

    This function should be called before starting any workflow
    to ensure fail-fast behavior if the database is unavailable.

    Args:
        project_name: Project name for database selection

    Raises:
        DatabaseRequiredError: If database is not available or query fails
    """
    try:
        from .db import ensure_schema, get_connection

        # Test connection with a simple query
        async with get_connection(project_name) as conn:
            await conn.query("RETURN 1")

        # Ensure schema is applied
        await ensure_schema(project_name)

    except DatabaseRequiredError:
        raise
    except Exception as e:
        raise DatabaseRequiredError(
            f"SurrealDB connection failed: {e}\n"
            f"Ensure SURREAL_URL is set and the database is accessible."
        ) from e


class Orchestrator:
    """Multi-agent workflow orchestrator.

    Coordinates Claude Code, Cursor CLI, and Gemini CLI through a 5-phase workflow:
    1. Planning (Claude)
    2. Validation (Cursor + Gemini parallel)
    3. Implementation (Claude)
    4. Verification (Cursor + Gemini parallel)
    5. Completion (Summary)

    Features:
    - Auto-retry on failures (configurable max attempts)
    - Auto-commit after each successful phase
    - State persistence for resumability
    - Structured logging
    """

    PHASE_NAMES = [
        (1, "planning"),
        (2, "validation"),
        (3, "implementation"),
        (4, "verification"),
        (5, "completion"),
    ]

    def __init__(
        self,
        project_dir: str | Path,
        max_retries: int = 3,
        auto_commit: bool = True,
        console_output: bool = True,
        log_level: LogLevel = LogLevel.INFO,
    ):
        """Initialize the orchestrator.

        Args:
            project_dir: Root directory of the project
            max_retries: Maximum retry attempts per phase
            auto_commit: Whether to auto-commit after phases
            console_output: Whether to print to console
            log_level: Minimum log level

        Raises:
            DatabaseRequiredError: If SurrealDB is not configured
        """
        # Validate database is available (fail-fast)
        # require_db() - removed for repository pattern decoupling

        self.project_dir = Path(project_dir).resolve()
        self.max_retries = max_retries
        self.auto_commit = auto_commit

        # Initialize storage adapter (DB-only)
        self.storage = get_workflow_storage(self.project_dir)

        # Ensure workflow directory exists (still needed for logs)
        self.workflow_dir = self.project_dir / ".workflow"
        self.workflow_dir.mkdir(exist_ok=True)

        # Initialize logger
        self.logger = OrchestrationLogger(
            workflow_dir=self.workflow_dir,
            console_output=console_output,
            min_level=log_level,
        )

        # Initialize git operations manager for efficient batched git operations
        self.git = GitOperationsManager(self.project_dir)

        # Initialize worktree manager and clean up any orphaned worktrees from previous runs
        # This is optional - worktrees require git, so we gracefully handle non-git directories
        from .utils.worktree import WorktreeError, WorktreeManager

        self.worktree_manager: Optional[WorktreeManager] = None
        try:
            self.worktree_manager = WorktreeManager(self.project_dir)
            self.worktree_manager.cleanup_orphaned_worktrees()
        except WorktreeError as e:
            self.logger.debug(f"Worktree manager disabled: {e} (git repository required)")
        except Exception as e:
            self.logger.warning(f"Failed to initialize worktree manager: {e}")

    def check_prerequisites(self) -> tuple[bool, list[str]]:
        """Check that all prerequisites are met.

        Returns:
            Tuple of (success, list of errors)
        """
        errors = []

        # Check PRODUCT.md exists
        # Check for documentation in docs/ folder (case-insensitive)
        doc_files = ["PRODUCT.md", "README.md", "product.md", "readme.md"]
        doc_dirs = ["docs", "Docs", "DOCS"]  # Only docs folder, case variations

        has_doc_file = any((self.project_dir / f).exists() for f in doc_files)

        has_doc_dir_content = False
        found_dirs = []

        for d in doc_dirs:
            d_path = self.project_dir / d
            if d_path.exists() and d_path.is_dir():
                found_dirs.append(d)
                # Check if there are any files (recursive)
                if any(f.is_file() for f in d_path.glob("**/*")):
                    has_doc_dir_content = True
                    break

        if not has_doc_file and not has_doc_dir_content:
            msg = "No documentation found. "
            if found_dirs:
                msg += f"Found empty directories: {', '.join(found_dirs)}. Please add files to them or create a PRODUCT.md."
            else:
                msg += "Create 'PRODUCT.md', 'README.md', or add content to a 'docs/' folder."
            errors.append(msg)

        # Check CLI tools
        from .agents import ClaudeAgent, CursorAgent, GeminiAgent

        claude = ClaudeAgent(self.project_dir)
        cursor = CursorAgent(self.project_dir)
        gemini = GeminiAgent(self.project_dir)

        if not claude.check_available():
            errors.append(
                "Claude CLI not found. Install with: npm install -g @anthropic/claude-cli"
            )

        if not cursor.check_available():
            errors.append(
                "Cursor CLI not found. Install with: curl https://cursor.com/install -fsSL | bash"
            )

        if not gemini.check_available():
            errors.append("Gemini CLI not found. Install with: npm install -g @google/gemini-cli")

        return len(errors) == 0, errors

    async def run_async(
        self,
        start_phase: int = 1,
        end_phase: int = 5,
        skip_validation: bool = False,
        autonomous: bool = False,
    ) -> dict:
        """Run the orchestration workflow asynchronously using LangGraph.

        Args:
            start_phase: Phase to start from (1-5)
            end_phase: Phase to end at (1-5)
            skip_validation: Skip the validation phase (phase 2)
            autonomous: Run fully autonomously without human consultation

        Returns:
            Dictionary with workflow results
        """
        return await self.run_langgraph(
            start_phase=start_phase,
            end_phase=end_phase,
            skip_validation=skip_validation,
            autonomous=autonomous,
        )

    def run(
        self,
        start_phase: int = 1,
        end_phase: int = 5,
        skip_validation: bool = False,
        autonomous: bool = False,
    ) -> dict:
        """Run the orchestration workflow using LangGraph (synchronous wrapper).

        Args:
            start_phase: Phase to start from (1-5)
            end_phase: Phase to end at (1-5)
            skip_validation: Skip the validation phase (phase 2)
            autonomous: Run fully autonomously without human consultation

        Returns:
            Dictionary with workflow results
        """
        return asyncio.run(
            self.run_async(start_phase, end_phase, skip_validation, autonomous)
        )

    def _auto_commit(self, phase_num: int, phase_name: str) -> None:
        """Auto-commit changes after a phase.

        Uses GitOperationsManager for efficient batched git operations.

        Args:
            phase_num: Phase number
            phase_name: Phase name for commit message
        """
        try:
            if not self.git.is_git_repo():
                self.logger.debug("Not a git repository, skipping auto-commit")
                return

            commit_message = f"[orchestrator] Phase {phase_num}: {phase_name} complete"

            commit_hash = self.git.auto_commit(commit_message)

            if commit_hash:
                self.storage.record_git_commit(phase_num, commit_hash, commit_message)
                self.logger.commit(phase_num, commit_hash, commit_message)
            else:
                self.logger.debug("No changes to commit")

        except Exception as e:
            self.logger.warning(f"Auto-commit failed: {e}", phase=phase_num)

    def resume(self) -> dict:
        """Resume workflow from last checkpoint using LangGraph.

        Returns:
            Dictionary with workflow results
        """
        return asyncio.run(self.resume_langgraph())

    def status(self) -> dict:
        """Get current workflow status.

        Returns:
            Dictionary with status information
        """
        return self.storage.get_summary()

    def reset(self, phase: Optional[int] = None) -> None:
        """Reset workflow or a specific phase.

        Args:
            phase: Phase number to reset, or None to reset all
        """
        if phase:
            self.storage.reset_to_phase(phase)
            self.logger.info(f"Reset phase {phase}")
        else:
            self.storage.reset_state()
            self.logger.info("Reset all phases")

    def rollback_to_phase(self, phase_num: int) -> dict:
        """Rollback to state before specified phase.

        Uses git commits recorded during workflow execution to restore
        the codebase to a previous state.

        Args:
            phase_num: Phase number to rollback to (will undo this phase and later)

        Returns:
            Dictionary with rollback results
        """
        commits = self.storage.get_git_commits()

        target_commit = None
        for commit in commits:
            if commit.get("phase", 0) < phase_num:
                target_commit = commit.get("commit_hash")
                break

        if not target_commit:
            return {"success": False, "error": f"No commit found before phase {phase_num}"}

        try:
            if self.git.reset_hard(target_commit):
                self.storage.reset_to_phase(phase_num)

                self.logger.info(
                    f"Rolled back to commit {target_commit[:8]} (before phase {phase_num})"
                )

                return {
                    "success": True,
                    "rolled_back_to": target_commit,
                    "current_phase": phase_num - 1 if phase_num > 1 else 1,
                    "message": f"Successfully rolled back to state before phase {phase_num}",
                }
            else:
                return {"success": False, "error": "Git reset failed"}
        except Exception as e:
            return {"success": False, "error": f"Rollback failed: {str(e)}"}

    def health_check(self) -> dict:
        """Return current health status.

        Returns:
            Dictionary with health status information
        """
        state = self.storage.get_state()
        summary = self.storage.get_summary()

        from .agents import ClaudeAgent, CursorAgent, GeminiAgent

        claude = ClaudeAgent(self.project_dir)
        cursor = CursorAgent(self.project_dir)
        gemini = GeminiAgent(self.project_dir)

        agents_status = {
            "claude": claude.check_available(),
            "cursor": cursor.check_available(),
            "gemini": gemini.check_available(),
        }

        all_agents_available = all(agents_status.values())
        current_phase_status = None
        if state and state.phase_status:
            phase_key = str(state.current_phase)
            phase_info = state.phase_status.get(phase_key, {})
            current_phase_status = phase_info.get("status")

        health_status = "healthy"
        if not all_agents_available:
            health_status = "degraded"
        if current_phase_status == "failed":
            health_status = "unhealthy"

        return {
            "status": health_status,
            "project": summary.get("project_name", self.project_dir.name),
            "current_phase": state.current_phase if state else None,
            "phase_status": current_phase_status,
            "iteration_count": state.iteration_count if state else 0,
            "last_updated": state.updated_at.isoformat() if state and state.updated_at else None,
            "agents": agents_status,
            "langgraph_enabled": is_langgraph_enabled(),
            "has_context": summary.get("discussion_complete", False),
            "total_commits": summary.get("total_commits", 0),
            "total_commits": summary.get("total_commits", 0),
        }

    async def health_check_async(self) -> dict:
        """Return current health status asynchronously.

        Returns:
            Dictionary with health status information
        """
        # Use async methods if available in storage, else fallback (carefully)
        if hasattr(self.storage, "get_state_async"):
            state = await self.storage.get_state_async()
            summary = await self.storage.get_summary_async()
        else:
            # If storage doesn't support async, we might risk loop issues if it uses run_async
            # But normally we should be using SurrealWorkflowRepository which now does.
            state = self.storage.get_state()
            summary = self.storage.get_summary()

        from .agents import ClaudeAgent, CursorAgent, GeminiAgent

        claude = ClaudeAgent(self.project_dir)
        cursor = CursorAgent(self.project_dir)
        gemini = GeminiAgent(self.project_dir)

        agents_status = {
            "claude": claude.check_available(),
            "cursor": cursor.check_available(),
            "gemini": gemini.check_available(),
        }

        all_agents_available = all(agents_status.values())
        current_phase_status = None
        if state and state.phase_status:
            phase_key = str(state.current_phase)
            phase_info = state.phase_status.get(phase_key, {})
            current_phase_status = phase_info.get("status")

        health_status = "healthy"
        if not all_agents_available:
            health_status = "degraded"
        if current_phase_status == "failed":
            health_status = "unhealthy"

        return {
            "status": health_status,
            "project": summary.get("project_name", self.project_dir.name),
            "current_phase": state.current_phase if state else None,
            "phase_status": current_phase_status,
            "iteration_count": state.iteration_count if state else 0,
            "last_updated": state.updated_at.isoformat() if state and state.updated_at else None,
            "agents": agents_status,
            "langgraph_enabled": is_langgraph_enabled(),
            "has_context": summary.get("discussion_complete", False),
            "total_commits": summary.get("total_commits", 0),
        }

    async def status_async(self) -> dict:
        """Get current workflow status asynchronously.

        Returns:
            Dictionary with status information
        """
        if hasattr(self.storage, "get_summary_async"):
            return await self.storage.get_summary_async()
        return self.storage.get_summary()

    async def run_langgraph(
        self,
        use_rich_display: bool = True,
        start_phase: int = 1,
        end_phase: int = 5,
        skip_validation: bool = False,
        autonomous: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> dict:
        """Run the workflow using LangGraph.

        Args:
            use_rich_display: Whether to use Rich live display (default True)
            start_phase: Phase to start from (1-5)
            end_phase: Phase to end at (1-5)
            skip_validation: Skip the validation phase (phase 2)
            autonomous: Run fully autonomously without human consultation (default False)
            progress_callback: Optional callback for progress events

        Returns:
            Dictionary with workflow results
        """
        from .langgraph import WorkflowRunner
        from .ui import UICallbackHandler, create_display

        self.logger.banner("Multi-Agent Orchestration System (LangGraph Mode)")

        # Validate DB connection before starting (fail-fast)
        try:
            await validate_db_connection(self.project_dir.name)
            self.logger.info("Database connection validated")
        except DatabaseRequiredError as e:
            self.logger.error(str(e))
            return {
                "success": False,
                "error": "Database connection required",
                "details": str(e),
            }

        prereq_ok, prereq_errors = self.check_prerequisites()
        if not prereq_ok:
            for error in prereq_errors:
                self.logger.error(error)
            return {
                "success": False,
                "error": "Prerequisites not met",
                "details": prereq_errors,
            }

        self.logger.info(f"Project: {self.project_dir.name}")

        display = create_display(self.project_dir.name) if use_rich_display else None

        # Combine callbacks if both display and external callback are provided
        callback = None
        if display:
            callback = UICallbackHandler(display)
            # If we also have a progress_callback, we might need a CompositeCallback
            # For now, if progress_callback is provided, we prioritize it for the runner
            # or we could make a composite.
            # To keep it simple: if progress_callback is passed, use it.
            # Ideally we want both.

        # Use provided callback or fall back to UI callback
        active_callback = progress_callback if progress_callback else callback

        # Determine execution mode
        execution_mode = "afk" if autonomous else "hitl"
        if autonomous:
            self.logger.info("Running in autonomous mode (no human consultation)")
        else:
            self.logger.info("Running in interactive mode (will pause for human input)")

        # Pass configuration to runner
        run_config = {
            "start_phase": start_phase,
            "end_phase": end_phase,
            "skip_validation": skip_validation,
            "execution_mode": execution_mode,
        }

        try:
            async with WorkflowRunner(self.project_dir) as runner:
                self.logger.separator()

                if display:
                    with display.start():
                        display.log_event("Starting LangGraph workflow", "info")
                        # Pass active_callback (which might be the websocket one)
                        # NOTE: If we use websocket callback, the local rich display might miss events
                        # if we don't composite them.
                        # For this specific requirement (visualization), the websocket is priority.
                        result = await runner.run(
                            progress_callback=active_callback, config=run_config
                        )

                        success = self._check_workflow_success(result)
                        if success:
                            display.show_completion(True, "Workflow completed successfully!")
                        elif result.get("next_decision") == "escalate":
                            display.show_completion(False, "Workflow paused for human intervention")
                        else:
                            display.show_completion(False, "Workflow did not complete successfully")
                else:
                    # No local display, just use the provided callback
                    result = await runner.run(progress_callback=active_callback, config=run_config)

                if self._check_workflow_success(result):
                    self.logger.banner("Workflow Complete!")
                    return {
                        "success": True,
                        "mode": "langgraph",
                        "results": result,
                    }
                else:
                    if result.get("next_decision") == "escalate":
                        self.logger.warning("Workflow paused for human intervention")
                        return {
                            "success": False,
                            "mode": "langgraph",
                            "paused": True,
                            "message": "Workflow requires human intervention",
                            "results": result,
                        }
                    else:
                        return {
                            "success": False,
                            "mode": "langgraph",
                            "results": result,
                        }

        except Exception as e:
            self.logger.error(f"LangGraph workflow failed: {e}")
            if display:
                display.show_completion(False, f"Workflow failed: {e}")
            return {
                "success": False,
                "mode": "langgraph",
                "error": str(e),
            }

    def _check_workflow_success(self, result: dict) -> bool:
        """Check if workflow completed successfully.

        Checks the target phase (end_phase) instead of hardcoded phase 5.
        For early stops (end_phase < 5), considers the workflow successful
        if the completion node ran (phase 5 marked completed) OR if the
        last executed phase completed successfully.

        Args:
            result: Workflow result dictionary

        Returns:
            True if target phase is completed
        """
        end_phase = result.get("end_phase", 5)
        phase_status = result.get("phase_status", {})

        # Primary check: completion node sets current_phase=5 and next_decision="continue"
        if result.get("current_phase") == 5 and result.get("next_decision") == "continue":
            return True

        # Secondary check: phase_status shows completion node ran (marks phase 5)
        phase_5 = phase_status.get("5")
        if phase_5 and hasattr(phase_5, "status"):
            status_val = (
                phase_5.status.value if hasattr(phase_5.status, "value") else phase_5.status
            )
            if status_val == "completed":
                return True

        # For early stops, check if the target phase completed
        if end_phase < 5:
            target = phase_status.get(str(end_phase))
            if target and hasattr(target, "status"):
                status_val = (
                    target.status.value if hasattr(target.status, "value") else target.status
                )
                if status_val == "completed":
                    return True

        return False

    def _extract_interrupt_data(self, pending: dict) -> Optional[dict]:
        """Extract interrupt data from pending interrupt for UI display.

        Args:
            pending: Pending interrupt data from LangGraph

        Returns:
            Formatted interrupt data for UserInputManager, or None if not extractable
        """
        if not pending:
            return None

        # Get the interrupt value (the data passed to interrupt())
        interrupt_value = pending.get("value")
        if not interrupt_value:
            # Try to infer from pending structure
            interrupt_value = pending

        # Determine interrupt type
        interrupt_type = interrupt_value.get("type")
        if not interrupt_type:
            # Try to infer type from content
            if "issue" in interrupt_value or "error" in interrupt_value:
                interrupt_type = "escalation"
            elif "approval" in str(interrupt_value).lower():
                interrupt_type = "approval_required"
            else:
                interrupt_type = "escalation"  # Default to escalation

        # Build normalized interrupt data
        data = {
            "type": interrupt_type,
            "phase": interrupt_value.get("phase") or pending.get("paused_at", "unknown"),
        }

        if interrupt_type == "escalation":
            data.update(
                {
                    "issue": interrupt_value.get("issue")
                    or interrupt_value.get("error")
                    or "An issue occurred",
                    "error_type": interrupt_value.get("error_type", "workflow_error"),
                    "suggested_actions": interrupt_value.get("suggested_actions", []),
                    "clarifications": interrupt_value.get("clarifications", []),
                    "context": interrupt_value.get("context", {}),
                    "retry_count": interrupt_value.get("retry_count", 0),
                    "max_retries": interrupt_value.get("max_retries", 3),
                }
            )
        elif interrupt_type == "approval_required":
            data.update(
                {
                    "approval_type": interrupt_value.get("approval_type", "general"),
                    "summary": interrupt_value.get("summary")
                    or interrupt_value.get("message", "Approval required"),
                    "details": interrupt_value.get("details", {}),
                    "scores": interrupt_value.get("scores", {}),
                    "files_changed": interrupt_value.get("files_changed", []),
                }
            )

        return data

    async def resume_langgraph(
        self,
        human_response: Optional[dict] = None,
        use_rich_display: bool = True,
        autonomous: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> dict:
        """Resume the LangGraph workflow from checkpoint.

        Args:
            human_response: Optional response for human escalation
            use_rich_display: Whether to use Rich live display (default True)
            autonomous: Run fully autonomously without human consultation (default False)
            progress_callback: Optional callback for progress events

        Returns:
            Dictionary with workflow results
        """
        from .langgraph import WorkflowRunner
        from .ui import UICallbackHandler, UserInputManager, create_display

        self.logger.banner("Resuming LangGraph Workflow")

        # Validate DB connection before resuming (fail-fast)
        try:
            await validate_db_connection(self.project_dir.name)
        except DatabaseRequiredError as e:
            self.logger.error(str(e))
            return {
                "success": False,
                "error": "Database connection required",
                "details": str(e),
            }

        # Determine execution mode
        execution_mode = "afk" if autonomous else "hitl"
        if autonomous:
            self.logger.info("Resuming in autonomous mode (no human consultation)")

        display = create_display(self.project_dir.name) if use_rich_display else None

        callback = None
        if display:
            callback = UICallbackHandler(display)

        active_callback = progress_callback if progress_callback else callback

        # Pass execution mode through config
        resume_config = {
            "execution_mode": execution_mode,
        }

        try:
            async with WorkflowRunner(self.project_dir) as runner:
                pending = await runner.get_pending_interrupt_async()

                # Handle HITL input if there's a pending interrupt and no response provided
                if pending and human_response is None and not autonomous:
                    self.logger.info(f"Workflow paused at: {pending['paused_at']}")

                    # Extract interrupt data and prompt for user input
                    interrupt_data = self._extract_interrupt_data(pending)
                    if interrupt_data:
                        input_manager = UserInputManager()
                        human_response = input_manager.handle_interrupt(interrupt_data)
                        self.logger.info(
                            f"User response: {human_response.get('action', 'unknown')}"
                        )

                elif pending:
                    self.logger.info(f"Workflow paused at: {pending['paused_at']}")

                if display:
                    with display.start():
                        display.log_event("Resuming LangGraph workflow", "info")
                        result = await runner.resume(
                            human_response=human_response,
                            progress_callback=active_callback,
                            config=resume_config,
                        )

                        success = self._check_workflow_success(result)
                        if success:
                            display.show_completion(True, "Workflow completed successfully!")
                        else:
                            display.show_completion(False, "Workflow did not complete successfully")
                else:
                    # No local display, use provided callback
                    result = await runner.resume(
                        human_response=human_response,
                        progress_callback=active_callback,
                        config=resume_config,
                    )

                if self._check_workflow_success(result):
                    self.logger.banner("Workflow Complete!")
                    return {
                        "success": True,
                        "mode": "langgraph",
                        "results": result,
                    }
                else:
                    return {
                        "success": False,
                        "mode": "langgraph",
                        "results": result,
                    }

        except Exception as e:
            self.logger.error(f"LangGraph resume failed: {e}")
            if display:
                display.show_completion(False, f"Resume failed: {e}")
            return {
                "success": False,
                "mode": "langgraph",
                "error": str(e),
            }

    async def status_langgraph(self) -> dict:
        """Get LangGraph workflow status.

        Returns:
            Dictionary with status information
        """
        from .langgraph import WorkflowRunner

        async with WorkflowRunner(self.project_dir) as runner:
            state = await runner.get_state()
            if not state:
                return {
                    "mode": "langgraph",
                    "status": "not_started",
                    "message": "No checkpoint found",
                }

            pending = await runner.get_pending_interrupt_async()

            return {
                "mode": "langgraph",
                "status": "paused" if pending else "in_progress",
                "project": state.get("project_name"),
                "current_phase": state.get("current_phase"),
                "phase_status": {
                    k: v.status.value if hasattr(v, "status") else str(v)
                    for k, v in state.get("phase_status", {}).items()
                },
                "pending_interrupt": pending,
            }

    async def get_workflow_definition(self, status_dict: Optional[dict] = None) -> dict:
        """Get the workflow graph definition for visualization.

        Args:
            status_dict: Optional dictionary with current phase statuses

        Returns:
            Dictionary with nodes and edges including rich metadata:
            - nodes: List of {id, type, phase, subgraph, agent, description, data}
            - edges: List of {source, target, type, data} with labels
        """
        from .langgraph import create_workflow_graph

        # Create the graph (without checkpointer as we just want structure)
        graph = create_workflow_graph()

        # Get the underlying graph definition
        drawable = graph.get_graph()

        nodes = []
        edges = []

        # Node metadata mappings
        # Phase assignments: which workflow phase does this node belong to?
        phase_map = {
            # Phase 1: Planning
            "prerequisites": 1,
            "product_validation": 1,
            "research_phase": 1,
            "discuss_phase": 1,
            "planning": 1,
            "task_breakdown": 1,
            # Phase 2: Validation
            "cursor_validate": 2,
            "gemini_validate": 2,
            "validation_fan_in": 2,
            "approval_gate": 2,
            # Phase 3: Implementation
            "pre_implementation": 3,
            "implementation": 3,
            "implement_task": 3,
            "select_task": 3,
            "write_tests": 3,
            "quality_gate": 3,
            "coverage_check": 3,
            "build_verification": 3,
            "security_scan": 3,
            # Phase 4: Verification
            "cursor_verify": 4,
            "gemini_verify": 4,
            "verification_fan_in": 4,
            "verify_task": 4,
            "review_gate": 4,
            "evaluate_agent": 4,
            # Phase 5: Completion
            "completion": 5,
            "generate_handoff": 5,
            # Error handling (cross-phase)
            "escalation": 0,
            "error_dispatch": 0,
            "fixer_triage": 0,
            "fixer_diagnose": 0,
            "fixer_research": 0,
            "fixer_apply": 0,
            "fixer_validate": 0,
            "fixer_verify": 0,
            "fix_bug": 0,
        }

        # Subgraph groupings: which logical group does this node belong to?
        subgraph_map = {
            "cursor_validate": "validation",
            "gemini_validate": "validation",
            "validation_fan_in": "validation",
            "cursor_verify": "verification",
            "gemini_verify": "verification",
            "verification_fan_in": "verification",
            "fixer_triage": "fixer",
            "fixer_diagnose": "fixer",
            "fixer_research": "fixer",
            "fixer_apply": "fixer",
            "fixer_validate": "fixer",
            "fixer_verify": "fixer",
            "quality_gate": "quality",
            "coverage_check": "quality",
            "build_verification": "quality",
            "security_scan": "quality",
            "research_phase": "research",
            "discuss_phase": "research",
        }

        # Agent assignments
        agent_map = {
            "cursor_validate": "cursor",
            "cursor_verify": "cursor",
            "gemini_validate": "gemini",
            "gemini_verify": "gemini",
            "planning": "claude",
            "implementation": "claude",
            "task_breakdown": "claude",
            "research_phase": "claude",
            "discuss_phase": "claude",
            "review_gate": "claude",
            "fixer_diagnose": "claude",
            "fixer_apply": "claude",
            "pre_implementation": "claude",
            "quality_gate": "claude",
        }

        # Human-readable descriptions (storytelling)
        description_map = {
            "prerequisites": "Checking if your project is ready to start.",
            "product_validation": "Validating your PRODUCT.md requirements.",
            "research_phase": "Researching best practices for your project.",
            "discuss_phase": "Analyzing the implementation approach.",
            "planning": "Creating a blueprint for what to build.",
            "task_breakdown": "Breaking features into implementation tasks.",
            "cursor_validate": "Cursor reviews for patterns and practices.",
            "gemini_validate": "Gemini reviews for architecture.",
            "validation_fan_in": "Combining validation feedback.",
            "approval_gate": "Checking plan approval status.",
            "pre_implementation": "Preparing the workspace.",
            "implementation": "Writing the code to build it.",
            "implement_task": "Implementing a specific task.",
            "select_task": "Picking the next task to work on.",
            "write_tests": "Writing tests for the code.",
            "quality_gate": "Running code quality checks.",
            "coverage_check": "Verifying test coverage.",
            "build_verification": "Verifying the build.",
            "security_scan": "Scanning for vulnerabilities.",
            "cursor_verify": "Cursor verifies implementation.",
            "gemini_verify": "Gemini verifies architecture.",
            "verification_fan_in": "Combining verification feedback.",
            "verify_task": "Verifying task implementation.",
            "review_gate": "Checking code review status.",
            "evaluate_agent": "Evaluating agent performance.",
            "completion": "Finishing up and showing results.",
            "generate_handoff": "Creating build summary.",
            "escalation": "Needs human input.",
            "error_dispatch": "Routing error to handler.",
            "fixer_triage": "Categorizing the error.",
            "fixer_diagnose": "Diagnosing root cause.",
            "fixer_research": "Researching solutions.",
            "fixer_apply": "Applying the fix.",
            "fixer_validate": "Validating the fix.",
            "fixer_verify": "Verifying no regressions.",
        }

        # Track conditional edge sources (routers)
        router_sources = set()
        for edge in drawable.edges:
            if hasattr(edge, "conditional") and edge.conditional:
                router_sources.add(edge.source)

        def get_node_status(node_id: str) -> str:
            if not status_dict or not status_dict.get("phase_status"):
                return "idle"
            node_key = node_id.lower().replace("_node", "").replace("node_", "")
            for key, phase in phase_map.items():
                if key in node_key and phase != 0:
                    ps = status_dict["phase_status"].get(str(phase))
                    if hasattr(ps, "value"):
                        return ps.value
                    return str(ps) if ps else "idle"
            return "idle"

        def get_node_metadata(node_id: str) -> dict:
            nk = node_id.lower().replace("_node", "").replace("node_", "")
            phase = next((p for k, p in phase_map.items() if k in nk), 0)
            subgraph = next((s for k, s in subgraph_map.items() if k in nk), None)
            agent = next((a for k, a in agent_map.items() if k in nk), None)
            desc = next((d for k, d in description_map.items() if k in nk), "Working...")
            return {"phase": phase, "subgraph": subgraph, "agent": agent, "description": desc}

        # Add standard nodes
        for node_id, node in drawable.nodes.items():
            if node_id in ["__start__", "__end__"]:
                continue
            status = get_node_status(node_id)
            meta = get_node_metadata(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "type": "default",
                    "phase": meta["phase"],
                    "subgraph": meta["subgraph"],
                    "agent": meta["agent"],
                    "data": {
                        "label": node_id,
                        "status": status,
                        "description": meta["description"],
                    },
                }
            )

        # Add synthetic router nodes
        for source in router_sources:
            router_id = f"{source}_router"
            smeta = get_node_metadata(source)
            nodes.append(
                {
                    "id": router_id,
                    "type": "router",
                    "phase": smeta["phase"],
                    "subgraph": smeta["subgraph"],
                    "agent": None,
                    "data": {
                        "label": "",
                        "status": "idle",
                        "description": f"Decision after {source}",
                    },
                }
            )
            edges.append(
                {
                    "source": source,
                    "target": router_id,
                    "type": "default",
                    "data": {"is_connector": True},
                }
            )

        # Add edges
        for edge in drawable.edges:
            src, tgt = edge.source, edge.target
            if src == "__start__":
                edges.append({"source": src, "target": tgt, "type": "default", "data": None})
                continue
            if tgt == "__end__":
                if src in router_sources:
                    lbl = str(edge.data) if hasattr(edge, "data") and edge.data else "end"
                    edges.append(
                        {
                            "source": f"{src}_router",
                            "target": "end_node",
                            "type": "default",
                            "data": {"label": lbl, "condition": lbl},
                        }
                    )
                continue
            is_cond = hasattr(edge, "conditional") and edge.conditional
            if is_cond:
                lbl = str(edge.data) if hasattr(edge, "data") and edge.data else tgt
                edges.append(
                    {
                        "source": f"{src}_router",
                        "target": tgt,
                        "type": "default",
                        "data": {"label": lbl, "condition": lbl},
                    }
                )
            else:
                edges.append({"source": src, "target": tgt, "type": "default", "data": None})

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_nodes": len(nodes),
                "phases": {
                    1: "Planning",
                    2: "Validation",
                    3: "Implementation",
                    4: "Verification",
                    5: "Completion",
                    0: "Error Handling",
                },
                "subgroups": list(set(subgraph_map.values())),
            },
        }

    def _print_progress(self, phase_num: int, phase_name: str, status: str) -> None:
        """Print progress indicator.

        Args:
            phase_num: Current phase number
            phase_name: Name of the current phase
            status: Status message
        """
        phases = ["Planning", "Validation", "Implementation", "Verification", "Completion"]

        progress_parts = []
        for i, name in enumerate(phases, 1):
            if i < phase_num:
                progress_parts.append(f"[{i}]")
            elif i == phase_num:
                progress_parts.append(f"[{i}*]")
            else:
                progress_parts.append("[ ]")

        progress_bar = " ".join(progress_parts)

        if self.logger.console_output:
            print()
            print("=" * 60)
            print(f"Phase {phase_num}/5: {phase_name} - {status}")
            print(f"Progress: {progress_bar}")
            print("=" * 60)
            print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Orchestration System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Project workflow (nested projects in projects/)
  python -m orchestrator --project my-app --start
  python -m orchestrator --project my-app --resume
  python -m orchestrator --project my-app --status

  # External project (any directory)
  python -m orchestrator --project-path ~/repos/my-project --start
  python -m orchestrator --project-path /path/to/project --status

  # Project management
  python -m orchestrator --list-projects
  python -m orchestrator --init-project my-new-app

  # Workflow operations
  python -m orchestrator --project my-app --health
  python -m orchestrator --project my-app --reset
  python -m orchestrator --project my-app --rollback 3
        """,
    )

    # Project management
    parser.add_argument(
        "--project",
        "-p",
        type=str,
        help="Project name (in projects/ directory)",
    )
    parser.add_argument(
        "--project-path",
        type=str,
        metavar="PATH",
        help="Path to external project (instead of projects/<name>)",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List all projects",
    )
    parser.add_argument(
        "--init-project",
        type=str,
        metavar="NAME",
        help="Initialize a new project directory",
    )

    # Workflow commands
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the workflow",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last incomplete phase",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show workflow status",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Show health check status",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset workflow",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Launch interactive Time Travel Debugger",
    )

    parser.add_argument(
        "--rollback",
        type=int,
        help="Rollback to state before specified phase",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Start from specific phase",
    )
    parser.add_argument(
        "--end-phase",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=5,
        help="End at specific phase",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation phase",
    )
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Run fully autonomously without human consultation (default: interactive mode)",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Disable auto-commit",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per phase (default: 3)",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=".",
        help="Project directory (default: current)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )

    # LangGraph mode options
    parser.add_argument(
        "--use-langgraph",
        action="store_true",
        help="Use LangGraph workflow (graph-based with parallelism)",
    )

    # Observability options
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Show enhanced status dashboard with recent actions and errors",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Show compact single-line status (use with --status or --dashboard)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output status as JSON (use with --status or --dashboard)",
    )
    parser.add_argument(
        "--cleanup-logs",
        action="store_true",
        help="Clean up and rotate log files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without doing it",
    )
    parser.add_argument(
        "--handoff",
        action="store_true",
        help="Generate handoff brief for session resumption",
    )
    parser.add_argument(
        "--log-stats",
        action="store_true",
        help="Show log file statistics",
    )

    args = parser.parse_args()

    if args.debug:
        from .cli.debug import TimeTravelDebugger

        debugger = TimeTravelDebugger(project_dir)
        debugger.cmdloop()
        return

    # Check for LangGraph mode env var
    # This overrides the flag if set in env
    if os.environ.get("ORCHESTRATOR_USE_LANGGRAPH", "").lower() in ("true", "1"):
        args.use_langgraph = True

    # Determine log level
    log_level = LogLevel.INFO
    if args.quiet:
        log_level = LogLevel.WARNING
    elif args.debug:
        log_level = LogLevel.DEBUG

    # Handle project management commands first
    root_dir = Path(args.project_dir).resolve()
    if args.project_dir == ".":
        # Try to find Conductor root
        candidate = Path.cwd()
        while candidate != candidate.parent:
            if (candidate / "projects").exists() and (candidate / "orchestrator").exists():
                root_dir = candidate
                break
            candidate = candidate.parent

    project_manager = ProjectManager(root_dir)

    # Project management commands
    if args.list_projects:
        projects = project_manager.list_projects()
        if not projects:
            print("No projects found. Initialize one with: --init-project <name>")
            return

        print("\nProjects:")
        print("-" * 60)
        for p in projects:
            phase_str = f"Phase {p['current_phase']}" if p["current_phase"] else "Not started"
            docs_str = "Has docs" if p.get("has_docs") or p.get("has_product_spec") else "No docs"
            context_str = []
            if p["has_claude_md"]:
                context_str.append("CLAUDE")
            if p["has_gemini_md"]:
                context_str.append("GEMINI")
            if p["has_cursor_rules"]:
                context_str.append("Cursor")
            context_display = ", ".join(context_str) if context_str else "No context files"

            print(f"  {p['name']}")
            print(f"    Status: {phase_str}, {docs_str}")
            print(f"    Context: {context_display}")
        return

    if args.init_project:
        result = project_manager.init_project(args.init_project)
        if result["success"]:
            print(f"\nProject initialized: {result['project_dir']}")
            print(result["message"])
            print("\nNext steps:")
            print("  1. Add Documents/ folder with product vision and architecture docs")
            print("  2. Add context files (CLAUDE.md, GEMINI.md, .cursor/rules)")
            print("  3. Create PRODUCT.md with feature specification")
            print(f"  4. Run: python -m orchestrator --project {args.init_project} --start")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)
        return

    # Determine project directory
    if args.project_path:
        # External project mode - use absolute path
        external_path = Path(args.project_path).resolve()
        if not external_path.exists():
            print(f"Error: Project path '{args.project_path}' does not exist")
            sys.exit(1)
        if not external_path.is_dir():
            print(f"Error: Project path '{args.project_path}' is not a directory")
            sys.exit(1)
        project_dir = external_path
        print(f"Using external project: {project_dir}")
    elif args.project:
        project_dir = project_manager.get_project(args.project)
        if not project_dir:
            print(f"Error: Project '{args.project}' not found")
            print("Available projects:")
            for p in project_manager.list_projects():
                print(f"  - {p['name']}")
            sys.exit(1)
    else:
        project_dir = Path(args.project_dir).resolve()

    # Handle observability commands before creating full orchestrator
    workflow_dir = project_dir / ".workflow"

    # Dashboard command
    if args.dashboard:
        from .status import show_status

        show_status(
            project_dir,
            compact=args.compact,
            json_output=args.json,
            use_colors=not args.quiet,
        )
        return

    # Log cleanup command
    if args.cleanup_logs:
        config = load_log_config(workflow_dir)
        log_manager = LogManager(workflow_dir, config)
        result = log_manager.cleanup(dry_run=args.dry_run)

        if args.dry_run:
            print("\nDry run - would perform the following actions:")
        else:
            print("\nLog cleanup complete:")

        if result.rotated_files:
            print(f"\nRotated files ({len(result.rotated_files)}):")
            for f in result.rotated_files:
                print(f"  - {f}")

        if result.archived_files:
            print(f"\nArchived files ({len(result.archived_files)}):")
            for f in result.archived_files:
                print(f"  - {f}")

        if result.deleted_files:
            print(f"\nDeleted files ({len(result.deleted_files)}):")
            for f in result.deleted_files:
                print(f"  - {f}")

        if result.freed_bytes > 0:
            print(f"\nFreed space: {result.freed_bytes / (1024 * 1024):.2f} MB")

        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  - {e}")
            sys.exit(1)

        return

    # Log stats command
    if args.log_stats:
        config = load_log_config(workflow_dir)
        log_manager = LogManager(workflow_dir, config)
        stats = log_manager.get_log_stats()

        print("\nLog Statistics:")
        print(f"  Total size: {stats['total_size_mb']} MB")
        print(f"  Archive count: {stats['archive_count']}")

        if stats["needs_rotation"]:
            print("\n  Files needing rotation:")
            for f in stats["needs_rotation"]:
                print(f"    - {f}")

        print("\n  File details:")
        for name, info in stats["files"].items():
            if info.get("exists"):
                size = info.get("size_mb", 0)
                age = info.get("age_days", 0)
                count = info.get("file_count")
                if count is not None:
                    print(f"    {name}: {size} MB ({count} files)")
                else:
                    print(f"    {name}: {size} MB ({age:.1f} days old)")

        return

    # Handoff command
    if args.handoff:
        brief = generate_handoff(project_dir, save=True)

        if args.json:
            print(json.dumps(brief.to_dict(), indent=2))
        else:
            print(brief.to_markdown())
            print("\nHandoff files saved to:")
            print(f"  - {workflow_dir / 'handoff_brief.json'}")
            print(f"  - {workflow_dir / 'handoff_brief.md'}")

        return

    # Create orchestrator
    orchestrator = Orchestrator(
        project_dir=project_dir,
        max_retries=args.max_retries,
        auto_commit=not args.no_commit,
        log_level=log_level,
    )

    # Auto-cleanup logs on start if enabled
    if should_auto_cleanup(workflow_dir):
        config = load_log_config(workflow_dir)
        log_manager = LogManager(workflow_dir, config)
        rotation_needed = log_manager.check_rotation_needed()
        if any(rotation_needed.values()):
            result = log_manager.rotate_if_needed()
            if result.rotated_files and not args.quiet:
                print(f"Auto-rotated {len(result.rotated_files)} log file(s)")

    # Check if using LangGraph mode (CLI flag or env var)
    use_langgraph = args.use_langgraph or is_langgraph_enabled()

    # Execute command
    if args.status:
        if use_langgraph:
            status = asyncio.run(orchestrator.status_langgraph())
            print("\nWorkflow Status (LangGraph Mode):")
            print(f"  Status: {status.get('status', 'unknown')}")
            print(f"  Project: {status.get('project', 'N/A')}")
            print(f"  Current Phase: {status.get('current_phase', 'N/A')}")
            if status.get("pending_interrupt"):
                paused_at = status.get("pending_interrupt", {}).get("paused_at", "Unknown")
                print(f"  Warning: Paused for human intervention at: {paused_at}")
            if "phase_status" in status:
                print("\nPhase Statuses:")
                for phase, state in status["phase_status"].items():
                    emoji = "+" if state == "completed" else "x" if state == "failed" else "."
                    print(f"  [{emoji}] Phase {phase}: {state}")
        else:
            status = orchestrator.status()
            print("\nWorkflow Status:")
            print(f"  Project: {status.get('project_name', status.get('project', 'Unknown'))}")
            print(f"  Current Phase: {status.get('current_phase', 'N/A')}")
            print(f"  Total Commits: {status.get('total_commits', 0)}")
            print("\nPhase Statuses:")
            for phase, state in status.get("phase_statuses", {}).items():
                emoji = "+" if state == "completed" else "x" if state == "failed" else "."
                print(f"  [{emoji}] {phase}: {state}")
        return

    if args.health:
        health = orchestrator.health_check()
        health_status = health.get("status", "unknown")
        status_emoji = (
            "+" if health_status == "healthy" else "?" if health_status == "degraded" else "x"
        )
        print(f"\nHealth Check: [{status_emoji}] {health_status.upper()}")
        print(f"\n  Project: {health.get('project', 'Unknown')}")
        print(f"  Current Phase: {health.get('current_phase', 'N/A')}")
        print(f"  Phase Status: {health.get('phase_status') or 'N/A'}")
        print(f"  Iteration Count: {health.get('iteration_count', 0)}")
        print(f"  Last Updated: {health.get('last_updated', 'N/A')}")
        print("\nAgent Availability (CLI):")
        for agent, available in health.get("agents", {}).items():
            emoji = "+" if available else "x"
            print(f"  [{emoji}] {agent}: {'Available' if available else 'Unavailable'}")
        print(f"\nLangGraph Mode: {'Enabled' if health.get('langgraph_enabled') else 'Disabled'}")
        return

    if args.rollback:
        result = orchestrator.rollback_to_phase(args.rollback)
        if result.get("success"):
            print("\nRollback successful!")
            rolled_back = result.get("rolled_back_to", "")
            print(f"  Rolled back to commit: {rolled_back[:8] if rolled_back else 'N/A'}")
            print(f"  Current phase: {result.get('current_phase', 'N/A')}")
        else:
            print(f"\nRollback failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
        return

    if args.reset:
        orchestrator.reset()
        print("Workflow reset.")
        return

    if args.resume:
        if use_langgraph:
            result = asyncio.run(orchestrator.resume_langgraph(autonomous=args.autonomous))
        else:
            result = orchestrator.resume()
    elif args.start or args.phase:
        if use_langgraph:
            result = asyncio.run(
                orchestrator.run_langgraph(
                    autonomous=args.autonomous,
                    start_phase=args.phase or 1,
                    end_phase=args.end_phase,
                    skip_validation=args.skip_validation,
                )
            )
        else:
            start = args.phase or 1
            result = orchestrator.run(
                start_phase=start,
                end_phase=args.end_phase,
                skip_validation=args.skip_validation,
                autonomous=args.autonomous,
            )
    else:
        parser.print_help()
        return

    # Print mode information
    if result.get("mode") == "langgraph":
        print("\n[LangGraph Mode]")

    # Exit with appropriate code
    sys.exit(0 if result.get("success", False) else 1)


def setup_global_exception_handler():
    """Setup global exception handler to log unhandled exceptions."""

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        import json
        import traceback
        from datetime import datetime
        from pathlib import Path

        # Print to stderr as usual
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

        try:
            # Try to write to errors directory
            project_dir = Path.cwd()
            workflow_dir = project_dir / ".workflow"
            errors_dir = workflow_dir / "errors"

            # If we are in the root orchestrator dir, we might need to find the project
            # But usually we run from root. Let's try to be safe.
            if not errors_dir.exists():
                # Try to create it if we can determine a valid project path
                # But if we crashed this early, maybe we can't.
                return

            errors_dir.mkdir(parents=True, exist_ok=True)
            log_file = errors_dir / "crash_report.jsonl"

            error_data = {
                "level": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "error_type": exc_type.__name__,
                "message": str(exc_value),
                "stack_trace": "".join(traceback.format_tb(exc_traceback)),
                "source": "global_exception_handler",
            }

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(error_data) + "\n")

        except Exception:
            # Last resort - don't crash the crash handler
            pass

    sys.excepthook = handle_exception


if __name__ == "__main__":
    setup_global_exception_handler()
    main()
