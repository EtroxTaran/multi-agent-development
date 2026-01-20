"""Main orchestrator for the multi-agent workflow.

Supports nested architecture where projects live in projects/<name>/ and
the orchestrator coordinates without directly writing application code.

Supports two execution modes:
- Legacy mode: Sequential phase execution via subprocess calls
- LangGraph mode: Graph-based workflow with native parallelism
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .utils.state import StateManager, PhaseStatus
from .utils.logging import OrchestrationLogger, LogLevel
from .utils.git_operations import GitOperationsManager
from .project_manager import ProjectManager
from .phases import (
    PlanningPhase,
    ValidationPhase,
    ImplementationPhase,
    VerificationPhase,
    CompletionPhase,
)


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

    PHASES = [
        (1, "planning", PlanningPhase),
        (2, "validation", ValidationPhase),
        (3, "implementation", ImplementationPhase),
        (4, "verification", VerificationPhase),
        (5, "completion", CompletionPhase),
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
        """Run the orchestration workflow.

        Args:
            start_phase: Phase to start from (1-5)
            end_phase: Phase to end at (1-5)
            skip_validation: Skip the validation phase (phase 2)

        Returns:
            Dictionary with workflow results
        """
        self.logger.banner("Multi-Agent Orchestration System")

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

        # Load state
        self.state.load()
        self.logger.info(f"Project: {self.state.state.project_name}")
        self.logger.info(f"Workflow directory: {self.state.workflow_dir}")
        self.logger.separator()

        # Run phases
        results = {}
        for phase_num, phase_name, phase_class in self.PHASES:
            if phase_num < start_phase:
                continue
            if phase_num > end_phase:
                break
            if skip_validation and phase_num == 2:
                self.logger.info("Skipping validation phase", phase=2)
                continue

            # Check if phase is already completed
            phase_state = self.state.get_phase(phase_num)
            if phase_state.status == PhaseStatus.COMPLETED:
                self.logger.info(f"Phase {phase_num} already completed, skipping", phase=phase_num)
                continue

            # Run phase with retry logic
            result = self._run_phase_with_retry(phase_num, phase_name, phase_class)
            results[phase_name] = result

            if not result.get("success", False):
                self.logger.error(f"Workflow stopped at phase {phase_num}")
                return {
                    "success": False,
                    "stopped_at_phase": phase_num,
                    "error": result.get("error", "Phase failed"),
                    "results": results,
                }

            # Auto-commit after successful phase
            if self.auto_commit and phase_num < 5:  # Don't commit after completion
                self._auto_commit(phase_num, phase_name)

        self.logger.banner("Workflow Complete!")
        self.logger.info(f"Summary: {self.state.workflow_dir / 'phases' / 'completion' / 'COMPLETION.md'}")

        return {
            "success": True,
            "results": results,
            "summary": self.state.get_summary(),
        }

    def _run_phase_with_retry(
        self,
        phase_num: int,
        phase_name: str,
        phase_class: type,
    ) -> dict:
        """Run a phase with retry logic.

        Args:
            phase_num: Phase number (1-5)
            phase_name: Phase name
            phase_class: Phase class to instantiate

        Returns:
            Dictionary with phase results
        """
        phase_state = self.state.get_phase(phase_num)

        while self.state.can_retry(phase_num):
            # Print progress indicator
            self._print_progress(phase_num, phase_name.title(), "Starting...")

            # Create phase instance
            phase = phase_class(
                project_dir=self.project_dir,
                state_manager=self.state,
                logger=self.logger,
            )

            # Update max attempts from orchestrator config
            phase_state.max_attempts = self.max_retries

            # Log retry if not first attempt
            if phase_state.attempts > 0:
                self.logger.retry(phase_num, phase_state.attempts + 1, self.max_retries)

            # Run phase
            result = phase.run()

            if result.get("success", False):
                return result

            # Check if we should retry
            if not self.state.can_retry(phase_num):
                break

            # Reset phase for retry
            self.state.reset_phase(phase_num)

        return {
            "success": False,
            "error": f"Phase {phase_num} failed after {phase_state.attempts} attempts",
            "last_error": phase_state.error,
        }

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
        """Resume workflow from last incomplete phase.

        Returns:
            Dictionary with workflow results
        """
        self.state.load()

        # Find first incomplete phase
        start_phase = 1
        for phase_num, phase_name, _ in self.PHASES:
            phase_state = self.state.get_phase(phase_num)
            if phase_state.status != PhaseStatus.COMPLETED:
                start_phase = phase_num
                break

        if start_phase > 5:
            self.logger.info("All phases already completed")
            return {"success": True, "message": "Workflow already complete"}

        self.logger.info(f"Resuming from phase {start_phase}")
        return self.run(start_phase=start_phase)

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
            for phase_num, _, _ in self.PHASES:
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

    async def run_langgraph(self) -> dict:
        """Run the workflow using LangGraph.

        Uses the LangGraph workflow graph for graph-based execution
        with native parallelism and checkpointing.

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

        try:
            # Run the workflow
            result = await runner.run()

            # Check result
            if result.get("phase_status", {}).get("5", {}).status == "completed":
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
            return {
                "success": False,
                "mode": "langgraph",
                "error": str(e),
            }

    async def resume_langgraph(self, human_response: Optional[dict] = None) -> dict:
        """Resume the LangGraph workflow from checkpoint.

        Args:
            human_response: Optional response for human escalation

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

        try:
            result = await runner.resume(human_response)

            if result.get("phase_status", {}).get("5", {}).status == "completed":
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

    # Create orchestrator
    orchestrator = Orchestrator(
        project_dir=project_dir,
        max_retries=args.max_retries,
        auto_commit=not args.no_commit,
        log_level=log_level,
    )

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
