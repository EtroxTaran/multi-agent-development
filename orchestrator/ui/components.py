"""UI rendering components for workflow display."""

from typing import Any

from orchestrator.ui.state_adapter import UIStateSnapshot


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_tokens(tokens: int) -> str:
    """Format token count."""
    if tokens < 1000:
        return str(tokens)
    elif tokens < 1000000:
        return f"{tokens / 1000:.1f}K"
    else:
        return f"{tokens / 1000000:.2f}M"


def render_header(snapshot: UIStateSnapshot) -> Any:
    """
    Render header component.

    Args:
        snapshot: UI state snapshot

    Returns:
        Renderable object (Rich Panel or string)
    """
    try:
        from rich.panel import Panel
        from rich.text import Text

        header_text = Text()
        header_text.append(f"Project: {snapshot.project_name}", style="bold cyan")
        header_text.append(
            f"  |  Phase {snapshot.current_phase}/{snapshot.total_phases}: {snapshot.phase_name}"
        )
        header_text.append(f"  |  Elapsed: {format_duration(snapshot.elapsed_seconds)}")
        header_text.append(f"  |  Status: {snapshot.status.upper()}")

        return Panel(header_text, title="Workflow Monitor", border_style="blue")
    except ImportError:
        # Fallback to plain string
        return (
            f"=== Workflow Monitor ===\n"
            f"Project: {snapshot.project_name}\n"
            f"Phase {snapshot.current_phase}/{snapshot.total_phases}: {snapshot.phase_name}\n"
            f"Elapsed: {format_duration(snapshot.elapsed_seconds)}\n"
            f"Status: {snapshot.status.upper()}"
        )


def render_phase_bar(snapshot: UIStateSnapshot) -> Any:
    """
    Render phase progress bar.

    Args:
        snapshot: UI state snapshot

    Returns:
        Renderable object
    """
    try:
        from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        )
        task = progress.add_task(
            f"Phase {snapshot.current_phase}: {snapshot.phase_name}",
            total=100,
            completed=int(snapshot.phase_progress * 100),
        )
        return progress
    except ImportError:
        # Fallback to ASCII bar
        filled = int(snapshot.phase_progress * 20)
        bar = "█" * filled + "░" * (20 - filled)
        return f"[{bar}] {int(snapshot.phase_progress * 100)}%"


def render_task_tree(snapshot: UIStateSnapshot) -> Any:
    """
    Render task tree.

    Args:
        snapshot: UI state snapshot

    Returns:
        Renderable object
    """
    try:
        from rich.text import Text
        from rich.tree import Tree

        tree = Tree(f"[bold]Tasks ({snapshot.tasks_completed}/{snapshot.tasks_total})[/bold]")

        for task in snapshot.tasks:
            # Status icons
            status_icons = {
                "pending": "○",
                "in_progress": "●",
                "completed": "✓",
                "failed": "✗",
            }
            status_colors = {
                "pending": "dim",
                "in_progress": "yellow",
                "completed": "green",
                "failed": "red",
            }

            icon = status_icons.get(task.status, "?")
            color = status_colors.get(task.status, "white")

            task_text = Text()
            task_text.append(f"{icon} ", style=color)
            task_text.append(
                f"{task.id}: {task.title}",
                style=color if task.status != "in_progress" else "bold yellow",
            )

            # Add iteration info if in progress
            if task.status == "in_progress" and task.max_iterations > 0:
                task_text.append(f" (iter {task.iteration}/{task.max_iterations})")
                if task.tests_total > 0:
                    task_text.append(f" [{task.tests_passed}/{task.tests_total} tests]")

            tree.add(task_text)

        return tree
    except ImportError:
        # Fallback to plain text
        lines = [f"Tasks ({snapshot.tasks_completed}/{snapshot.tasks_total}):"]
        for task in snapshot.tasks:
            status_chars = {"pending": "○", "in_progress": "●", "completed": "✓", "failed": "✗"}
            char = status_chars.get(task.status, "?")
            line = f"  {char} {task.id}: {task.title}"
            if task.status == "in_progress" and task.max_iterations > 0:
                line += f" (iter {task.iteration}/{task.max_iterations})"
            lines.append(line)
        return "\n".join(lines)


def render_metrics_panel(snapshot: UIStateSnapshot) -> Any:
    """
    Render metrics panel.

    Args:
        snapshot: UI state snapshot

    Returns:
        Renderable object
    """
    try:
        from rich.table import Table

        table = Table(title="Metrics", show_header=False, box=None)
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")

        table.add_row("Tokens", format_tokens(snapshot.tokens))
        table.add_row("Cost", f"${snapshot.cost:.2f}")
        table.add_row("Files Created", str(snapshot.files_created))
        table.add_row("Files Modified", str(snapshot.files_modified))

        return table
    except ImportError:
        return (
            f"Metrics:\n"
            f"  Tokens: {format_tokens(snapshot.tokens)}\n"
            f"  Cost: ${snapshot.cost:.2f}\n"
            f"  Files Created: {snapshot.files_created}\n"
            f"  Files Modified: {snapshot.files_modified}"
        )


def render_event_log(snapshot: UIStateSnapshot, max_events: int = 10) -> Any:
    """
    Render event log.

    Args:
        snapshot: UI state snapshot
        max_events: Maximum events to display

    Returns:
        Renderable object
    """
    try:
        from rich.panel import Panel
        from rich.text import Text

        log_text = Text()
        events = snapshot.recent_events[-max_events:] if snapshot.recent_events else []

        level_styles = {
            "info": "white",
            "warning": "yellow",
            "error": "red",
            "success": "green",
        }

        for event in events:
            timestamp = event.timestamp.strftime("%H:%M:%S")
            style = level_styles.get(event.level, "white")
            log_text.append(f"[{timestamp}] ", style="dim")
            log_text.append(f"{event.message}\n", style=style)

        if not events:
            log_text.append("No events yet", style="dim")

        return Panel(log_text, title="Event Log", border_style="dim")
    except ImportError:
        lines = ["Event Log:"]
        events = snapshot.recent_events[-max_events:] if snapshot.recent_events else []
        if not events:
            lines.append("  No events yet")
        else:
            for event in events:
                timestamp = event.timestamp.strftime("%H:%M:%S")
                lines.append(f"  [{timestamp}] {event.message}")
        return "\n".join(lines)
