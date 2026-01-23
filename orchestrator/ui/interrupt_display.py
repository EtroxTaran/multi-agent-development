"""Display components for workflow interrupts.

Provides Rich-based display components for showing escalation
and approval information during HITL workflow pauses.
"""

from typing import Optional

from rich.box import ROUNDED
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class InterruptDisplay:
    """Displays workflow interrupt information using Rich components."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the interrupt display.

        Args:
            console: Rich console instance (creates one if not provided)
        """
        self.console = console or Console()

    def display_escalation(self, data: dict) -> None:
        """Display an escalation interrupt with full context.

        Shows the issue, suggested actions, and any clarification questions
        that need human input.

        Args:
            data: Escalation data containing:
                - phase: Current workflow phase
                - issue: Description of what went wrong
                - error_type: Type of error (optional)
                - suggested_actions: List of possible actions
                - clarifications: List of questions needing answers (optional)
                - context: Additional context information (optional)
                - retry_count: Number of retries attempted (optional)
                - max_retries: Maximum retries allowed (optional)
        """
        phase = data.get("phase", "Unknown")
        issue = data.get("issue", "An issue occurred that requires attention")
        error_type = data.get("error_type", "workflow_error")
        retry_count = data.get("retry_count", 0)
        max_retries = data.get("max_retries", 3)

        # Create header
        header_text = Text()
        header_text.append("WORKFLOW PAUSED", style="bold red")
        header_text.append(" - ", style="dim")
        header_text.append(f"Phase {phase}", style="bold cyan")

        self.console.print()
        self.console.print(
            Panel(
                header_text,
                box=ROUNDED,
                border_style="red",
                padding=(0, 2),
            )
        )

        # Display issue summary
        issue_content = Text()
        issue_content.append("Issue: ", style="bold")
        issue_content.append(issue)
        issue_content.append("\n\n")
        issue_content.append("Error Type: ", style="bold dim")
        issue_content.append(error_type, style="dim")
        issue_content.append("\n")
        issue_content.append("Retry Attempts: ", style="bold dim")
        issue_content.append(f"{retry_count}/{max_retries}", style="dim")

        self.console.print(
            Panel(
                issue_content,
                title="[bold]Issue Summary[/bold]",
                border_style="yellow",
            )
        )

        # Display suggested actions if provided
        suggested_actions = data.get("suggested_actions", [])
        if suggested_actions:
            action_table = Table(show_header=True, header_style="bold")
            action_table.add_column("#", style="dim", width=3)
            action_table.add_column("Action", style="cyan")
            action_table.add_column("Description")

            for i, action in enumerate(suggested_actions, 1):
                if isinstance(action, dict):
                    action_table.add_row(
                        str(i),
                        action.get("name", f"Action {i}"),
                        action.get("description", ""),
                    )
                else:
                    action_table.add_row(str(i), str(action), "")

            self.console.print(
                Panel(
                    action_table,
                    title="[bold]Suggested Actions[/bold]",
                    border_style="blue",
                )
            )

        # Display clarification questions if present
        clarifications = data.get("clarifications", [])
        if clarifications:
            self.console.print()
            self.console.print("[bold yellow]Clarification Needed:[/bold yellow]")
            self.console.print()

            for i, question in enumerate(clarifications, 1):
                if isinstance(question, dict):
                    q_text = question.get("question", f"Question {i}")
                    options = question.get("options", [])

                    self.console.print(f"  [bold]Q{i}:[/bold] {q_text}")

                    if options:
                        for j, opt in enumerate(options, 1):
                            self.console.print(f"      [{j}] {opt}")
                else:
                    self.console.print(f"  [bold]Q{i}:[/bold] {question}")
                self.console.print()

        # Display additional context if provided
        context = data.get("context", {})
        if context:
            context_table = Table(show_header=False, box=None)
            context_table.add_column("Key", style="bold dim")
            context_table.add_column("Value")

            for key, value in context.items():
                if isinstance(value, (list, dict)):
                    import json

                    value = json.dumps(value, indent=2)[:100] + "..."
                context_table.add_row(key, str(value)[:100])

            self.console.print(
                Panel(
                    context_table,
                    title="[bold]Additional Context[/bold]",
                    border_style="dim",
                )
            )

    def display_approval(self, data: dict) -> None:
        """Display an approval gate with context summary.

        Shows what is being approved and relevant context information.

        Args:
            data: Approval data containing:
                - phase: Current workflow phase
                - approval_type: Type of approval needed
                - summary: Summary of what's being approved
                - details: Detailed information (optional)
                - scores: Validation/verification scores (optional)
                - files_changed: List of changed files (optional)
        """
        phase = data.get("phase", "Unknown")
        approval_type = data.get("approval_type", "general")
        summary = data.get("summary", "Approval required to proceed")

        # Create header
        header_text = Text()
        header_text.append("APPROVAL REQUIRED", style="bold yellow")
        header_text.append(" - ", style="dim")
        header_text.append(f"Phase {phase}", style="bold cyan")

        self.console.print()
        self.console.print(
            Panel(
                header_text,
                box=ROUNDED,
                border_style="yellow",
                padding=(0, 2),
            )
        )

        # Display approval summary
        summary_content = Text()
        summary_content.append("Type: ", style="bold")
        summary_content.append(approval_type.replace("_", " ").title())
        summary_content.append("\n\n")
        summary_content.append(summary)

        self.console.print(
            Panel(
                summary_content,
                title="[bold]Summary[/bold]",
                border_style="cyan",
            )
        )

        # Display scores if available
        scores = data.get("scores", {})
        if scores:
            score_table = Table(show_header=True, header_style="bold")
            score_table.add_column("Agent", style="cyan")
            score_table.add_column("Score", justify="right")
            score_table.add_column("Status")

            for agent, score in scores.items():
                if isinstance(score, dict):
                    score_val = score.get("score", "N/A")
                    status = score.get("status", "unknown")
                else:
                    score_val = score
                    status = "passed" if float(score) >= 6.0 else "failed"

                status_style = (
                    "green" if status == "passed" else "red" if status == "failed" else "yellow"
                )
                score_table.add_row(
                    agent.title(),
                    str(score_val),
                    f"[{status_style}]{status}[/{status_style}]",
                )

            self.console.print(
                Panel(
                    score_table,
                    title="[bold]Validation Scores[/bold]",
                    border_style="blue",
                )
            )

        # Display files changed if available
        files_changed = data.get("files_changed", [])
        if files_changed:
            files_list = "\n".join(f"  - {f}" for f in files_changed[:10])
            if len(files_changed) > 10:
                files_list += f"\n  ... and {len(files_changed) - 10} more"

            self.console.print(
                Panel(
                    files_list,
                    title=f"[bold]Files Changed ({len(files_changed)})[/bold]",
                    border_style="dim",
                )
            )

        # Display details if available
        details = data.get("details", {})
        if details:
            if isinstance(details, str):
                self.console.print(
                    Panel(
                        Markdown(details),
                        title="[bold]Details[/bold]",
                        border_style="dim",
                    )
                )
            elif isinstance(details, dict):
                detail_table = Table(show_header=False, box=None)
                detail_table.add_column("Key", style="bold dim")
                detail_table.add_column("Value")

                for key, value in details.items():
                    detail_table.add_row(key, str(value)[:100])

                self.console.print(
                    Panel(
                        detail_table,
                        title="[bold]Details[/bold]",
                        border_style="dim",
                    )
                )

    def display_separator(self) -> None:
        """Display a visual separator line."""
        self.console.print()
        self.console.rule(style="dim")
        self.console.print()

    def display_waiting(self, message: str = "Waiting for input...") -> None:
        """Display a waiting indicator.

        Args:
            message: Message to display while waiting
        """
        self.console.print()
        self.console.print(f"[bold blue]>>> {message}[/bold blue]")
        self.console.print()
