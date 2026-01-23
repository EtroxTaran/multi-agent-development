"""Enhanced status dashboard for workflow observability.

Provides a comprehensive visual overview of workflow state,
including phase progress, task status, recent actions, and errors.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .utils.action_log import get_action_log
from .utils.error_aggregator import ErrorSeverity, get_error_aggregator
from .utils.handoff import HandoffGenerator


# ANSI escape codes for formatting
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Box drawing
    BOX_TOP_LEFT = "╔"
    BOX_TOP_RIGHT = "╗"
    BOX_BOTTOM_LEFT = "╚"
    BOX_BOTTOM_RIGHT = "╝"
    BOX_HORIZONTAL = "═"
    BOX_VERTICAL = "║"
    BOX_T_LEFT = "╠"
    BOX_T_RIGHT = "╣"


class StatusDashboard:
    """Visual status dashboard for workflow observability."""

    def __init__(
        self,
        project_dir: str | Path,
        width: int = 64,
        use_colors: bool = True,
    ):
        """Initialize the status dashboard.

        Args:
            project_dir: Project directory
            width: Dashboard width in characters
            use_colors: Whether to use ANSI colors
        """
        self.project_dir = Path(project_dir)
        self.workflow_dir = self.project_dir / ".workflow"
        self.width = width
        self.use_colors = use_colors

        # Initialize components
        self.action_log = get_action_log(self.workflow_dir)
        self.error_aggregator = get_error_aggregator(self.workflow_dir)

    def _color(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    def _box_line(self, left: str, fill: str, right: str, content: str = "") -> str:
        """Create a box line with optional content."""
        if content:
            padding = self.width - len(content) - 4
            return f"{left} {content}{' ' * padding} {right}"
        return f"{left}{fill * (self.width - 2)}{right}"

    def _load_state(self) -> Optional[dict]:
        """Load workflow state from database.

        Uses WorkflowStorageAdapter to get state from SurrealDB.
        """
        try:
            from .storage.workflow_adapter import get_workflow_storage

            storage = get_workflow_storage(self.project_dir)
            state_data = storage.get_state()
            if state_data is not None:
                return {
                    "project_name": self.project_dir.name,
                    "current_phase": state_data.current_phase,
                    "phase_status": state_data.phase_status,
                    "iteration_count": state_data.iteration_count,
                    "execution_mode": state_data.execution_mode,
                    "created_at": state_data.created_at.isoformat()
                    if state_data.created_at
                    else None,
                    "updated_at": state_data.updated_at.isoformat()
                    if state_data.updated_at
                    else None,
                }
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(f"Storage adapter failed: {e}")

        return None

    def _load_tasks(self) -> list[dict]:
        """Load task information from database."""
        try:
            from .db.repositories.tasks import get_task_repository

            repo = get_task_repository(self.project_dir.name)
            from .storage.async_utils import run_async

            tasks = run_async(repo.list_tasks())
            return [t.to_dict() if hasattr(t, "to_dict") else t for t in tasks] if tasks else []
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(f"Failed to load tasks: {e}")
            return []

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def _render_header(self, state: dict) -> list[str]:
        """Render dashboard header."""
        lines = []

        project = state.get("project_name", self.project_dir.name)
        phase = state.get("current_phase", 1)

        # Get current task info
        tasks = self._load_tasks()
        current_task = None
        completed_tasks = 0
        for task in tasks:
            if task.get("status") == "in_progress":
                current_task = task
            if task.get("status") == "completed":
                completed_tasks += 1

        # Status line
        if current_task:
            status = f"Phase {phase} - Implementation (Task {completed_tasks + 1}/{len(tasks)})"
        else:
            phase_names = ["Planning", "Validation", "Implementation", "Verification", "Completion"]
            phase_name = phase_names[phase - 1] if 1 <= phase <= 5 else "Unknown"
            status = f"Phase {phase} - {phase_name}"

        # Build header
        lines.append(
            self._box_line(Colors.BOX_TOP_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_TOP_RIGHT)
        )
        lines.append(
            self._box_line(
                Colors.BOX_VERTICAL,
                " ",
                Colors.BOX_VERTICAL,
                self._color(f"PROJECT: {project}", Colors.BOLD + Colors.CYAN),
            )
        )
        lines.append(
            self._box_line(
                Colors.BOX_VERTICAL,
                " ",
                Colors.BOX_VERTICAL,
                self._color(f"STATUS: {status}", Colors.BOLD + Colors.WHITE),
            )
        )

        return lines

    def _render_phases(self, state: dict) -> list[str]:
        """Render phase status section."""
        lines = []

        lines.append(self._box_line(Colors.BOX_T_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_T_RIGHT))
        lines.append(
            self._box_line(
                Colors.BOX_VERTICAL, " ", Colors.BOX_VERTICAL, self._color("PHASES:", Colors.BOLD)
            )
        )

        phases = state.get("phases", {})
        phase_info = [
            ("1", "Planning", "planning"),
            ("2", "Validation", "validation"),
            ("3", "Implementation", "implementation"),
            ("4", "Verification", "verification"),
            ("5", "Completion", "completion"),
        ]

        current_phase = state.get("current_phase", 1)

        for num, display_name, key in phase_info:
            phase_data = phases.get(key, {})
            status = phase_data.get("status", "pending")
            attempts = phase_data.get("attempts", 0)
            max_attempts = phase_data.get("max_attempts", 3)

            # Status indicator
            if status == "completed":
                indicator = self._color("[✓]", Colors.GREEN)
                status_text = "completed"
            elif status == "in_progress":
                indicator = self._color("[→]", Colors.YELLOW)
                # Add task info for implementation phase
                if key == "implementation":
                    tasks = self._load_tasks()
                    current_task = None
                    for task in tasks:
                        if task.get("status") == "in_progress":
                            current_task = task
                            break
                    if current_task:
                        status_text = f"in_progress ({current_task.get('id')}: {current_task.get('title', '')[:20]})"
                    else:
                        status_text = "in_progress"
                else:
                    status_text = "in_progress"
            elif status == "failed":
                indicator = self._color("[✗]", Colors.RED)
                status_text = "failed"
            elif status == "blocked":
                indicator = self._color("[!]", Colors.MAGENTA)
                status_text = "blocked"
            else:
                indicator = "[ ]"
                status_text = "pending"

            # Add attempt info if retrying
            if attempts > 1 and status in ["in_progress", "failed"]:
                status_text += f" (attempt {attempts}/{max_attempts})"

            # Duration if completed
            started = phase_data.get("started_at")
            completed = phase_data.get("completed_at")
            if started and completed:
                try:
                    start_dt = datetime.fromisoformat(started)
                    end_dt = datetime.fromisoformat(completed)
                    duration = (end_dt - start_dt).total_seconds()
                    status_text += f" ({self._format_duration(duration)})"
                except ValueError:
                    pass

            line = f"{indicator} {num}. {display_name:<14} - {status_text}"
            lines.append(self._box_line(Colors.BOX_VERTICAL, " ", Colors.BOX_VERTICAL, line))

        return lines

    def _render_recent_actions(self, limit: int = 5) -> list[str]:
        """Render recent actions section."""
        lines = []

        actions = self.action_log.get_recent(limit)

        lines.append(self._box_line(Colors.BOX_T_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_T_RIGHT))
        lines.append(
            self._box_line(
                Colors.BOX_VERTICAL,
                " ",
                Colors.BOX_VERTICAL,
                self._color(f"RECENT ACTIONS (last {limit}):", Colors.BOLD),
            )
        )

        if not actions:
            lines.append(
                self._box_line(
                    Colors.BOX_VERTICAL,
                    " ",
                    Colors.BOX_VERTICAL,
                    self._color("No actions recorded yet", Colors.DIM),
                )
            )
        else:
            for action in actions:
                timestamp = datetime.fromisoformat(action.timestamp).strftime("%H:%M:%S")

                parts = [timestamp]

                if action.phase is not None:
                    parts.append(f"[P{action.phase}]")

                if action.agent:
                    parts.append(self._color(f"[{action.agent}]", Colors.MAGENTA))

                # Status symbol
                if action.status.value == "completed":
                    parts.append(self._color("✓", Colors.GREEN))
                elif action.status.value == "failed":
                    parts.append(self._color("✗", Colors.RED))
                elif action.status.value == "started":
                    parts.append(self._color("▶", Colors.BLUE))
                else:
                    parts.append("•")

                # Truncate message to fit
                max_msg_len = self.width - 30
                message = action.message[:max_msg_len]
                if len(action.message) > max_msg_len:
                    message += "..."

                parts.append(message)

                line = " ".join(parts)
                lines.append(self._box_line(Colors.BOX_VERTICAL, " ", Colors.BOX_VERTICAL, line))

        return lines

    def _render_errors(self) -> list[str]:
        """Render errors section."""
        lines = []

        errors = self.error_aggregator.get_unresolved()
        error_count = len(errors)

        lines.append(self._box_line(Colors.BOX_T_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_T_RIGHT))

        if error_count == 0:
            lines.append(
                self._box_line(
                    Colors.BOX_VERTICAL,
                    " ",
                    Colors.BOX_VERTICAL,
                    self._color("ERRORS: None ✓", Colors.GREEN + Colors.BOLD),
                )
            )
        else:
            header = f"ERRORS ({error_count} unresolved):"
            lines.append(
                self._box_line(
                    Colors.BOX_VERTICAL,
                    " ",
                    Colors.BOX_VERTICAL,
                    self._color(header, Colors.RED + Colors.BOLD),
                )
            )

            for error in errors[:3]:  # Show max 3 errors
                # Severity icon
                if error.severity == ErrorSeverity.CRITICAL:
                    icon = self._color("●", Colors.RED)
                elif error.severity == ErrorSeverity.ERROR:
                    icon = self._color("●", Colors.YELLOW)
                else:
                    icon = self._color("●", Colors.GRAY)

                # Location
                location_parts = []
                if error.phase is not None:
                    location_parts.append(f"P{error.phase}")
                if error.task_id:
                    location_parts.append(error.task_id)
                location = "/".join(location_parts) if location_parts else ""

                # Truncate message
                max_msg_len = self.width - 20
                message = error.message[:max_msg_len]
                if len(error.message) > max_msg_len:
                    message += "..."

                if location:
                    line = f"{icon} [{location}] {message}"
                else:
                    line = f"{icon} {message}"

                lines.append(self._box_line(Colors.BOX_VERTICAL, " ", Colors.BOX_VERTICAL, line))

        return lines

    def _render_next_action(self, state: dict) -> list[str]:
        """Render next action recommendation."""
        lines = []

        # Generate handoff to get next action recommendation
        handoff_gen = HandoffGenerator(self.project_dir)
        brief = handoff_gen.generate()

        lines.append(self._box_line(Colors.BOX_T_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_T_RIGHT))
        lines.append(
            self._box_line(
                Colors.BOX_VERTICAL,
                " ",
                Colors.BOX_VERTICAL,
                self._color("NEXT:", Colors.BOLD) + f" {brief.next_action[:self.width - 12]}",
            )
        )

        return lines

    def _render_footer(self) -> list[str]:
        """Render dashboard footer."""
        return [
            self._box_line(Colors.BOX_BOTTOM_LEFT, Colors.BOX_HORIZONTAL, Colors.BOX_BOTTOM_RIGHT)
        ]

    def render(self, output: bool = True) -> str:
        """Render the full dashboard.

        Args:
            output: Whether to print to stdout

        Returns:
            Dashboard as string
        """
        state = self._load_state()

        if not state:
            message = "No workflow state found. Run --start to begin."
            if output:
                print(message)
            return message

        # Build dashboard
        lines = []
        lines.extend(self._render_header(state))
        lines.extend(self._render_phases(state))
        lines.extend(self._render_recent_actions())
        lines.extend(self._render_errors())
        lines.extend(self._render_next_action(state))
        lines.extend(self._render_footer())

        dashboard = "\n".join(lines)

        if output:
            print(dashboard)

        return dashboard

    def render_compact(self, output: bool = True) -> str:
        """Render a compact single-line status.

        Args:
            output: Whether to print to stdout

        Returns:
            Compact status string
        """
        state = self._load_state()

        if not state:
            status = "No workflow"
            if output:
                print(status)
            return status

        project = state.get("project_name", self.project_dir.name)
        phase = state.get("current_phase", 1)
        phases = state.get("phases", {})

        # Count completed phases
        completed = sum(1 for p in phases.values() if p.get("status") == "completed")

        # Check for errors
        errors = self.error_aggregator.get_unresolved()
        error_count = len(errors)

        # Build compact status
        parts = [
            f"{project}",
            f"P{phase}/5",
            f"{completed}/5 done",
        ]

        if error_count > 0:
            parts.append(self._color(f"{error_count} errors", Colors.RED))

        status = " | ".join(parts)

        if output:
            print(status)

        return status

    def get_json(self) -> dict:
        """Get dashboard data as JSON.

        Returns:
            Dictionary with all dashboard data
        """
        state = self._load_state() or {}
        tasks = self._load_tasks()
        actions = self.action_log.get_recent(20)
        errors = self.error_aggregator.get_unresolved()

        # Calculate task progress
        completed_tasks = sum(1 for t in tasks if t.get("status") == "completed")
        total_tasks = len(tasks)

        # Get current task
        current_task = None
        for task in tasks:
            if task.get("status") == "in_progress":
                current_task = task.get("id")
                break

        return {
            "project": state.get("project_name", self.project_dir.name),
            "current_phase": state.get("current_phase", 1),
            "phase_status": {
                name: data.get("status", "pending")
                for name, data in state.get("phases", {}).items()
            },
            "task_progress": {
                "current": current_task,
                "completed": completed_tasks,
                "total": total_tasks,
            },
            "recent_actions": [a.to_dict() for a in actions],
            "errors": {
                "count": len(errors),
                "items": [e.to_dict() for e in errors[:10]],
            },
            "summary": self.action_log.get_summary(),
        }


def show_status(
    project_dir: str | Path,
    compact: bool = False,
    json_output: bool = False,
    use_colors: bool = True,
) -> None:
    """Display workflow status.

    Args:
        project_dir: Project directory
        compact: Show compact single-line status
        json_output: Output as JSON
        use_colors: Use ANSI colors
    """
    dashboard = StatusDashboard(project_dir, use_colors=use_colors)

    if json_output:
        data = dashboard.get_json()
        print(json.dumps(data, indent=2))
    elif compact:
        dashboard.render_compact()
    else:
        dashboard.render()
