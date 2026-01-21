"""Main orchestrator for the multi-agent workflow.

Supports nested architecture where projects live in projects/<name>/ and
the orchestrator coordinates without directly writing application code.

Supports two execution modes:
- Legacy mode: Sequential phase execution via subprocess calls
- LangGraph mode: Graph-based workflow with native parallelism
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .utils.state import StateManager, PhaseStatus
from .utils.logging import OrchestrationLogger, LogLevel
from .utils.git_operations import GitOperationsManager
from .utils.log_manager import LogManager, load_config as load_log_config, should_auto_cleanup
from .utils.handoff import HandoffGenerator, generate_handoff
from .project_manager import ProjectManager
from .ui import create_display, UICallbackHandler


def is_langgraph_enabled() -> bool:
    """Check if LangGraph mode is enabled via environment variable.

    Returns:
        True if ORCHESTRATOR_USE_LANGGRAPH is set to 'true' or '1'
    """
    return os.environ.get("ORCHESTRATOR_USE_LANGGRAPH", "").lower() in ("true", "1")


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

    # Legacy PHASES removed - now using LangGraph workflow exclusively
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
        """
        self.project_dir = Path(project_dir).resolve()
        self.max_retries = max_retries
        self.auto_commit = auto_commit

        # Initialize state manager
        self.state = StateManager(self.project_dir)
        self.state.ensure_workflow_dir()

        # Initialize logger
        self.logger = OrchestrationLogger(
            workflow_dir=self.state.workflow_dir,
            console_output=console_output,
            min_level=log_level,
        )

        # Initialize git operations manager for efficient batched git operations
        self.git = GitOperationsManager(self.project_dir)

    def check_prerequisites(self) -> tuple[bool, list[str]]:
        """Check that all prerequisites are met.

        Returns:
            Tuple of (success, list of errors)
        """
        errors = []

        # Check PRODUCT.md exists
        product_file = self.project_dir / "PRODUCT.md"
        if not product_file.exists():
            errors.append(
                "PRODUCT.md not found. Create it with your feature specification."
            )

        # Check CLI tools
        from .agents import ClaudeAgent, CursorAgent, GeminiAgent

        claude = ClaudeAgent(self.project_dir)
        cursor = CursorAgent(self.project_dir)
        gemini = GeminiAgent(self.project_dir)

        if not claude.check_available():
            errors.append("Claude CLI not found. Install with: npm install -g @anthropic/claude-cli")

        if not cursor.check_available():
            errors.append("Cursor CLI not found. Install with: curl https://cursor.com/install -fsSL | bash")

        if not gemini.check_available():
            errors.append("Gemini CLI not found. Install with: npm install -g @google/gemini-cli")

        return len(errors) == 0, errors

    def run(
        self,
        start_phase: int = 1,
        end_phase: int = 5,
        skip_validation: bool = False,
    ) -> dict:
        """Run the orchestration workflow using LangGraph.

        Note: Legacy phase execution has been removed. This method now
        delegates to run_langgraph() for all workflow execution.

        Args:
            start_phase: Phase to start from (1-5) - currently ignored, LangGraph starts fresh
            end_phase: Phase to end at (1-5) - currently ignored, LangGraph runs to completion
            skip_validation: Skip the validation phase (phase 2) - currently ignored

        Returns:
            Dictionary with workflow results
        """
        # Delegate to LangGraph workflow
        return asyncio.run(self.run_langgraph())

    def _auto_commit(self, phase_num: int, phase_name: str) -> None:
        """Auto-commit changes after a phase.

        Uses GitOperationsManager for efficient batched git operations,
        reducing subprocess overhead from 5 calls to 1.

        Args:
            phase_num: Phase number
            phase_name: Phase name for commit message
        """
        try:
            if not self.git.is_git_repo():
                self.logger.debug("Not a git repository, skipping auto-commit")
                return

            commit_message = f"[orchestrator] Phase {phase_num}: {phase_name} complete"

            # Single batched operation: status check + add + commit + hash
            commit_hash = self.git.auto_commit(commit_message)

            if commit_hash:
                self.state.record_commit(phase_num, commit_hash, commit_message)
                self.logger.commit(phase_num, commit_hash, commit_message)
            else:
                self.logger.debug("No changes to commit")

        except Exception as e:
            self.logger.warning(f"Auto-commit failed: {e}", phase=phase_num)

    def resume(self) -> dict:
        """Resume workflow from last checkpoint using LangGraph.

        Note: Legacy phase-based resume has been removed. This method now
        delegates to resume_langgraph() for checkpoint-based resume.

        Returns:
            Dictionary with workflow results
        """
        # Delegate to LangGraph resume
        return asyncio.run(self.resume_langgraph())

    def status(self) -> dict:
        """Get current workflow status.

        Returns:
            Dictionary with status information
        """
        self.state.load()
        return self.state.get_summary()

    def reset(self, phase: Optional[int] = None) -> None:
        """Reset workflow or a specific phase.

        Args:
            phase: Phase number to reset, or None to reset all
        """
        self.state.load()

        if phase:
            self.state.reset_phase(phase)
            self.logger.info(f"Reset phase {phase}")
        else:
            # Reset all phases
            for phase_num, _ in self.PHASE_NAMES:
                phase_state = self.state.get_phase(phase_num)
                phase_state.status = PhaseStatus.PENDING
                phase_state.attempts = 0
                phase_state.blockers = []
                phase_state.error = None
                phase_state.started_at = None
                phase_state.completed_at = None

            self.state.state.current_phase = 1
            self.state.state.git_commits = []
            self.state.save()
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
        self.state.load()
        commits = self.state.state.git_commits

        # Find commit before this phase
        target_commit = None
        for commit in reversed(commits):
            if commit.get("phase", 0) < phase_num:
                target_commit = commit.get("hash")
                break

        if not target_commit:
            return {
                "success": False,
                "error": f"No commit found before phase {phase_num}"
            }

        # Git reset to that commit using GitOperationsManager
        try:
            if self.git.reset_hard(target_commit):
                # Update state
                self.state.reset_to_phase(phase_num)

                self.logger.info(f"Rolled back to commit {target_commit[:8]} (before phase {phase_num})")

                return {
                    "success": True,
                    "rolled_back_to": target_commit,
                    "current_phase": phase_num - 1 if phase_num > 1 else 1,
                    "message": f"Successfully rolled back to state before phase {phase_num}"
                }
            else:
                return {
                    "success": False,
                    "error": "Git reset failed"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Rollback failed: {str(e)}"
            }

    def health_check(self) -> dict:
        """Return current health status.

        Checks the status of the workflow and availability of all agents.

        Returns:
            Dictionary with health status information
        """
        self.state.load()
        state = self.state.state

        # Check agent availability
        from .agents import ClaudeAgent, CursorAgent, GeminiAgent

        claude = ClaudeAgent(self.project_dir)
        cursor = CursorAgent(self.project_dir)
        gemini = GeminiAgent(self.project_dir)

        agents_status = {
            "claude": claude.check_available(),
            "cursor": cursor.check_available(),
            "gemini": gemini.check_available(),
        }

        # Check SDK availability
        sdk_status = {}
        try:
            from .sdk import AgentFactory
            factory = AgentFactory(self.project_dir)
            sdk_report = factory.get_availability_report()
            sdk_status = {
                "claude_sdk": sdk_report.get("claude_sdk", False),
                "gemini_sdk": sdk_report.get("gemini_sdk", False),
            }
        except ImportError:
            sdk_status = {"claude_sdk": False, "gemini_sdk": False}

        # Determine overall health
        all_agents_available = all(agents_status.values())
        current_phase_status = None
        if state.current_phase:
            phase_state = self.state.get_phase(state.current_phase)
            current_phase_status = phase_state.status.value

        health_status = "healthy"
        if not all_agents_available:
            health_status = "degraded"
        if current_phase_status == "failed":
            health_status = "unhealthy"

        return {
            "status": health_status,
            "project": state.project_name,
            "current_phase": state.current_phase,
            "phase_status": current_phase_status,
            "iteration_count": state.iteration_count,
            "last_updated": state.updated_at,
            "agents": agents_status,
            "sdk": sdk_status,
            "langgraph_enabled": is_langgraph_enabled(),
            "has_context": state.context is not None,
            "total_commits": len(state.git_commits),
        }

    async def run_langgraph(self, use_rich_display: bool = True) -> dict:
        """Run the workflow using LangGraph.

        Uses the LangGraph workflow graph for graph-based execution
        with native parallelism and checkpointing.

        Args:
            use_rich_display: Whether to use Rich live display (default True)

        Returns:
            Dictionary with workflow results
        """
        from .langgraph import WorkflowRunner, create_initial_state

        self.logger.banner("Multi-Agent Orchestration System (LangGraph Mode)")

        # Check prerequisites
        prereq_ok, prereq_errors = self.check_prerequisites()
        if not prereq_ok:
            for error in prereq_errors:
                self.logger.error(error)
            return {
                "success": False,
                "error": "Prerequisites not met",
                "details": prereq_errors,
            }

        # Create LangGraph runner
        runner = WorkflowRunner(self.project_dir)

        self.logger.info(f"Project: {self.project_dir.name}")
        self.logger.info(f"Checkpoint directory: {runner.checkpoint_dir}")
        self.logger.separator()

        # Create display and callback
        display = create_display(self.project_dir.name) if use_rich_display else None
        callback = UICallbackHandler(display) if display else None

        try:
            if display:
                # Run with Rich live display
                with display.start():
                    display.log_event("Starting LangGraph workflow", "info")
                    result = await runner.run(progress_callback=callback)

                    # Show completion status
                    success = self._check_workflow_success(result)
                    if success:
                        display.show_completion(True, "Workflow completed successfully!")
                    elif result.get("next_decision") == "escalate":
                        display.show_completion(False, "Workflow paused for human intervention")
                    else:
                        display.show_completion(False, "Workflow did not complete successfully")
            else:
                # Run without display
                result = await runner.run()

            # Check result
            if self._check_workflow_success(result):
                self.logger.banner("Workflow Complete!")
                return {
                    "success": True,
                    "mode": "langgraph",
                    "results": result,
                }
            else:
                # Check if escalated
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

        Args:
            result: Workflow result dictionary

        Returns:
            True if phase 5 is completed
        """
        phase_status = result.get("phase_status", {})
        phase_5 = phase_status.get("5")
        if phase_5 and hasattr(phase_5, "status"):
            return phase_5.status.value == "completed" if hasattr(phase_5.status, "value") else phase_5.status == "completed"
        return False

    async def resume_langgraph(
        self,
        human_response: Optional[dict] = None,
        use_rich_display: bool = True,
    ) -> dict:
        """Resume the LangGraph workflow from checkpoint.

        Args:
            human_response: Optional response for human escalation
            use_rich_display: Whether to use Rich live display (default True)

        Returns:
            Dictionary with workflow results
        """
        from .langgraph import WorkflowRunner

        self.logger.banner("Resuming LangGraph Workflow")

        runner = WorkflowRunner(self.project_dir)

        # Check for pending interrupt
        pending = runner.get_pending_interrupt()
        if pending:
            self.logger.info(f"Workflow paused at: {pending['paused_at']}")

        # Create display and callback
        display = create_display(self.project_dir.name) if use_rich_display else None
        callback = UICallbackHandler(display) if display else None

        try:
            if display:
                # Run with Rich live display
                with display.start():
                    display.log_event("Resuming LangGraph workflow", "info")
                    result = await runner.resume(
                        human_response=human_response,
                        progress_callback=callback,
                    )

                    # Show completion status
                    success = self._check_workflow_success(result)
                    if success:
                        display.show_completion(True, "Workflow completed successfully!")
                    else:
                        display.show_completion(False, "Workflow did not complete successfully")
            else:
                # Run without display
                result = await runner.resume(human_response=human_response)

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

        runner = WorkflowRunner(self.project_dir)

        state = await runner.get_state()
        if not state:
            return {
                "mode": "langgraph",
                "status": "not_started",
                "message": "No checkpoint found",
            }

        pending = runner.get_pending_interrupt()

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

    def _print_progress(self, phase_num: int, phase_name: str, status: str) -> None:
        """Print progress indicator.

        Args:
            phase_num: Current phase number
            phase_name: Name of the current phase
            status: Status message
        """
        phases = ["Planning", "Validation", "Implementation", "Verification", "Completion"]

        # Build progress bar
        progress_parts = []
        for i, name in enumerate(phases, 1):
            if i < phase_num:
                progress_parts.append(f"[{i}]")  # Completed
            elif i == phase_num:
                progress_parts.append(f"[{i}*]")  # Current
            else:
                progress_parts.append(f"[ ]")  # Pending

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
  # Nested architecture (recommended)
  python -m orchestrator --project my-app --start
  python -m orchestrator --project my-app --resume
  python -m orchestrator --project my-app --status

  # Project management
  python -m orchestrator --list-projects
  python -m orchestrator --create-project my-new-app
  python -m orchestrator --sync-projects

  # Legacy mode (works in current directory)
  python -m orchestrator --start
  python -m orchestrator --resume
  python -m orchestrator --status
  python -m orchestrator --health
  python -m orchestrator --reset
  python -m orchestrator --rollback 3
  python -m orchestrator --phase 3
        """,
    )

    # Project management (nested architecture)
    parser.add_argument(
        "--project", "-p",
        type=str,
        help="Project name (in projects/ directory)",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List all projects",
    )
    parser.add_argument(
        "--create-project",
        type=str,
        metavar="NAME",
        help="Create a new project from template",
    )
    parser.add_argument(
        "--sync-projects",
        action="store_true",
        help="Sync templates to all projects",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="base",
        help="Template for new project (default: base)",
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
        "--rollback",
        type=int,
        choices=[1, 2, 3, 4, 5],
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
        help="Project directory (default: current) - legacy mode",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )

    # LangGraph mode options
    parser.add_argument(
        "--use-langgraph",
        action="store_true",
        help="Use LangGraph workflow (graph-based with parallelism)",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Force legacy mode (sequential subprocess calls)",
    )

    # Update management options
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check for available updates to project",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Apply available updates to project",
    )
    parser.add_argument(
        "--check-all-updates",
        action="store_true",
        help="Check updates for all projects",
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="List available backups for project",
    )
    parser.add_argument(
        "--rollback-backup",
        type=str,
        metavar="BACKUP_ID",
        help="Rollback project to specified backup",
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
        help="Show what would be done without doing it (use with --cleanup-logs)",
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

    # Set LangGraph mode from flag
    if args.use_langgraph:
        os.environ["ORCHESTRATOR_USE_LANGGRAPH"] = "true"
    elif args.legacy:
        os.environ["ORCHESTRATOR_USE_LANGGRAPH"] = "false"

    # Determine log level
    log_level = LogLevel.INFO
    if args.quiet:
        log_level = LogLevel.WARNING
    elif args.debug:
        log_level = LogLevel.DEBUG

    # Handle project management commands first
    root_dir = Path(args.project_dir).resolve()
    if args.project_dir == ".":
        # Try to find meta-architect root
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
            print("No projects found. Create one with: --create-project <name>")
            return

        print("\nProjects:")
        print("-" * 60)
        for p in projects:
            phase_str = f"Phase {p['current_phase']}" if p['current_phase'] else "Not started"
            spec_str = "Has spec" if p['has_product_spec'] else "No spec"
            print(f"  {p['name']}")
            print(f"    Template: {p['template']}, Status: {phase_str}, {spec_str}")
        return

    if args.create_project:
        result = project_manager.create_project(args.create_project, args.template)
        if result['success']:
            print(result['output'])
        else:
            print(f"Error: {result['error']}")
            if result.get('output'):
                print(result['output'])
            sys.exit(1)
        return

    if args.sync_projects:
        result = project_manager.sync_all_projects()
        print(result['output'])
        if not result['success']:
            sys.exit(1)
        return

    # Handle update management commands
    if args.check_all_updates:
        from .update_manager import UpdateManager, format_update_check

        manager = UpdateManager(root_dir)
        projects_dir = manager.projects_dir

        if not projects_dir.exists():
            print("No projects directory found.")
            return

        projects = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

        if not projects:
            print("No projects found.")
            return

        updates_count = 0
        print("\n" + "=" * 60)
        print("Project Update Status")
        print("=" * 60)

        for project_dir in sorted(projects):
            update_info = manager.check_updates(project_dir.name)
            if update_info.updates_available:
                updates_count += 1
                print(f"\n  {project_dir.name}")
                print(f"    Current: {update_info.current_version} -> Latest: {update_info.latest_version}")
                if update_info.is_breaking_update:
                    print("    ⚠️  Breaking update!")
            else:
                print(f"\n  {project_dir.name}: Up to date ({update_info.current_version})")

        print("\n" + "-" * 60)
        print(f"Summary: {updates_count}/{len(projects)} projects need updates")
        return

    # Determine project directory
    if args.project:
        project_dir = project_manager.get_project(args.project)
        if not project_dir:
            print(f"Error: Project '{args.project}' not found")
            print("Available projects:")
            for p in project_manager.list_projects():
                print(f"  - {p['name']}")
            sys.exit(1)
    else:
        # Legacy mode: use current directory or --project-dir
        project_dir = Path(args.project_dir).resolve()

    # Handle observability commands before creating full orchestrator
    workflow_dir = project_dir / ".workflow"

    # Handle update management commands for specific project
    if args.check_updates:
        from .update_manager import UpdateManager, format_update_check

        manager = UpdateManager(root_dir)
        project_name = args.project or project_dir.name
        update_info = manager.check_updates(project_name)

        if args.json:
            print(json.dumps(update_info.to_dict(), indent=2))
        else:
            print(format_update_check(update_info))
        return

    if args.update:
        from .update_manager import UpdateManager

        manager = UpdateManager(root_dir)
        project_name = args.project or project_dir.name

        # Check if updates available first
        update_info = manager.check_updates(project_name)
        if not update_info.updates_available:
            print(f"Project '{project_name}' is already up to date.")
            return

        # Warn about breaking updates
        if update_info.is_breaking_update:
            print(f"⚠️  Warning: This is a breaking update ({update_info.current_version} -> {update_info.latest_version})")
            if not args.dry_run:
                response = input("Continue? [y/N]: ").strip().lower()
                if response != "y":
                    print("Update cancelled.")
                    return

        # Apply updates
        result = manager.apply_updates(project_name, dry_run=args.dry_run)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if args.dry_run:
                print("\nDry run - would make the following changes:")
            else:
                print("\nUpdate result:")

            if result.success:
                print(f"  Status: {'Would update' if args.dry_run else 'Updated'}")
                if result.backup_id:
                    print(f"  Backup created: {result.backup_id}")
                if result.files_updated:
                    print("  Files updated:")
                    for f in result.files_updated:
                        print(f"    - {f}")
            else:
                print("  Status: Failed")
                for error in result.errors:
                    print(f"  Error: {error}")
                sys.exit(1)
        return

    if args.list_backups:
        from .update_manager import UpdateManager

        manager = UpdateManager(root_dir)
        project_name = args.project or project_dir.name
        backups = manager.list_backups(project_name)

        if args.json:
            print(json.dumps(backups, indent=2))
        else:
            if not backups:
                print(f"No backups found for project '{project_name}'")
            else:
                print(f"\nBackups for '{project_name}':")
                print("-" * 50)
                for backup in backups:
                    print(f"\n  ID: {backup['backup_id']}")
                    print(f"  Created: {backup['created_at']}")
                    print(f"  Version: {backup.get('project_version', 'unknown')}")
        return

    if args.rollback_backup:
        from .update_manager import UpdateManager

        manager = UpdateManager(root_dir)
        project_name = args.project or project_dir.name

        result = manager.rollback(project_name, args.rollback_backup)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"\n✅ Rollback successful!")
                print(f"  Restored files:")
                for f in result.files_updated:
                    print(f"    - {f}")
            else:
                print(f"\n❌ Rollback failed")
                for error in result.errors:
                    print(f"  Error: {error}")
                sys.exit(1)
        return

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

        if stats['needs_rotation']:
            print(f"\n  Files needing rotation:")
            for f in stats['needs_rotation']:
                print(f"    - {f}")

        print("\n  File details:")
        for name, info in stats['files'].items():
            if info.get('exists'):
                size = info.get('size_mb', 0)
                age = info.get('age_days', 0)
                count = info.get('file_count')
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
            print(f"\nHandoff files saved to:")
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

    # Check if using LangGraph mode
    use_langgraph = is_langgraph_enabled()

    # Execute command
    if args.status:
        if use_langgraph:
            status = asyncio.run(orchestrator.status_langgraph())
            print(f"\nWorkflow Status (LangGraph Mode):")
            print(f"  Status: {status.get('status', 'unknown')}")
            print(f"  Project: {status.get('project', 'N/A')}")
            print(f"  Current Phase: {status.get('current_phase', 'N/A')}")
            if status.get('pending_interrupt'):
                print(f"  ⚠️ Paused for human intervention at: {status['pending_interrupt']['paused_at']}")
            if 'phase_status' in status:
                print("\nPhase Statuses:")
                for phase, state in status['phase_status'].items():
                    emoji = "✅" if state == "completed" else "❌" if state == "failed" else "⏳"
                    print(f"  {emoji} Phase {phase}: {state}")
        else:
            status = orchestrator.status()
            print("\nWorkflow Status:")
            print(f"  Project: {status['project']}")
            print(f"  Current Phase: {status['current_phase']}")
            print(f"  Total Commits: {status['total_commits']}")
            print("\nPhase Statuses:")
            for phase, state in status['phase_statuses'].items():
                emoji = "✅" if state == "completed" else "❌" if state == "failed" else "⏳"
                print(f"  {emoji} {phase}: {state}")
        return

    if args.health:
        health = orchestrator.health_check()
        status_emoji = "✅" if health['status'] == "healthy" else "⚠️" if health['status'] == "degraded" else "❌"
        print(f"\nHealth Check: {status_emoji} {health['status'].upper()}")
        print(f"\n  Project: {health['project']}")
        print(f"  Current Phase: {health['current_phase']}")
        print(f"  Phase Status: {health['phase_status'] or 'N/A'}")
        print(f"  Iteration Count: {health['iteration_count']}")
        print(f"  Last Updated: {health['last_updated']}")
        print("\nAgent Availability (CLI):")
        for agent, available in health['agents'].items():
            emoji = "✅" if available else "❌"
            print(f"  {emoji} {agent}: {'Available' if available else 'Unavailable'}")
        if 'sdk' in health:
            print("\nSDK Availability:")
            for sdk, available in health['sdk'].items():
                emoji = "✅" if available else "❌"
                print(f"  {emoji} {sdk}: {'Available' if available else 'Unavailable'}")
        print(f"\nLangGraph Mode: {'Enabled' if health.get('langgraph_enabled') else 'Disabled'}")
        return

    if args.rollback:
        result = orchestrator.rollback_to_phase(args.rollback)
        if result['success']:
            print(f"\n✅ Rollback successful!")
            print(f"  Rolled back to commit: {result['rolled_back_to'][:8]}")
            print(f"  Current phase: {result['current_phase']}")
        else:
            print(f"\n❌ Rollback failed: {result['error']}")
            sys.exit(1)
        return

    if args.reset:
        orchestrator.reset()
        print("Workflow reset.")
        return

    # Check if using LangGraph mode
    use_langgraph = is_langgraph_enabled()

    if args.resume:
        if use_langgraph:
            result = asyncio.run(orchestrator.resume_langgraph())
        else:
            result = orchestrator.resume()
    elif args.start or args.phase:
        if use_langgraph:
            result = asyncio.run(orchestrator.run_langgraph())
        else:
            start = args.phase or 1
            result = orchestrator.run(
                start_phase=start,
                end_phase=args.end_phase,
                skip_validation=args.skip_validation,
            )
    else:
        parser.print_help()
        return

    # Print mode information
    if result.get("mode") == "langgraph":
        print(f"\n[LangGraph Mode]")

    # Exit with appropriate code
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
