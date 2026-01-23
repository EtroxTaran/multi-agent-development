"""Helper utilities for interactive CLI prompts.

Provides reusable prompt components for gathering user input
in the HITL (Human-in-the-Loop) workflow.
"""

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt


def prompt_menu(
    console: Console,
    options: list[str],
    title: str = "Select an option",
    allow_custom: bool = False,
    default: Optional[int] = None,
) -> tuple[int, str]:
    """Display a numbered menu and get user selection.

    Args:
        console: Rich console for output
        options: List of option labels to display
        title: Menu title to display
        allow_custom: Whether to add an "Other" option for custom input
        default: Default selection (1-indexed), None for no default

    Returns:
        Tuple of (selected_index, selected_value)
        - selected_index is 0-indexed
        - selected_value is either the option string or custom input

    Example:
        >>> idx, value = prompt_menu(console, ["Option A", "Option B"], "Choose:", allow_custom=True)
        >>> # User selects 2
        >>> # Returns (1, "Option B")
    """
    console.print(f"\n[bold cyan]{title}[/bold cyan]")
    console.print()

    for i, opt in enumerate(options, 1):
        marker = "[bold green]>[/bold green]" if default == i else " "
        console.print(f"  {marker} [{i}] {opt}")

    if allow_custom:
        other_idx = len(options) + 1
        marker = "[bold green]>[/bold green]" if default == other_idx else " "
        console.print(f"  {marker} [{other_idx}] Other (enter custom response)")

    max_choice = len(options) + (1 if allow_custom else 0)

    default_str = str(default) if default else None
    while True:
        try:
            choice = IntPrompt.ask(
                f"\n  Enter number (1-{max_choice})",
                default=default_str,
                console=console,
            )
            if 1 <= choice <= max_choice:
                break
            console.print(f"  [red]Please enter a number between 1 and {max_choice}[/red]")
        except (ValueError, TypeError):
            console.print("  [red]Please enter a valid number[/red]")

    # Handle custom input
    if allow_custom and choice == len(options) + 1:
        custom = Prompt.ask("  Enter your response", console=console)
        return (choice - 1, custom)

    return (choice - 1, options[choice - 1])


def prompt_multiline(
    console: Console,
    prompt: str,
    hint: Optional[str] = None,
) -> str:
    """Get single-line text input from user.

    Args:
        console: Rich console for output
        prompt: Prompt message to display
        hint: Optional hint text to display before prompt

    Returns:
        User's text input

    Example:
        >>> text = prompt_multiline(console, "Describe the issue")
    """
    if hint:
        console.print(f"  [dim]{hint}[/dim]")

    return Prompt.ask(f"  {prompt}", console=console)


def prompt_confirm(
    console: Console,
    message: str,
    default: bool = False,
) -> bool:
    """Get yes/no confirmation from user.

    Args:
        console: Rich console for output
        message: Confirmation message to display
        default: Default value if user presses Enter

    Returns:
        True for yes, False for no

    Example:
        >>> if prompt_confirm(console, "Continue with this action?", default=True):
        ...     # proceed
    """
    return Confirm.ask(f"  {message}", default=default, console=console)


def prompt_text_block(
    console: Console,
    prompt: str,
    hint: Optional[str] = None,
) -> str:
    """Get multi-line text input from user.

    Allows user to enter multiple lines of text. Uses a simple
    approach where empty line + Enter ends input.

    Args:
        console: Rich console for output
        prompt: Prompt message to display
        hint: Optional hint text

    Returns:
        Multi-line text input

    Example:
        >>> feedback = prompt_text_block(console, "Enter detailed feedback")
    """
    console.print(f"\n  [bold]{prompt}[/bold]")
    if hint:
        console.print(f"  [dim]{hint}[/dim]")
    console.print("  [dim](Enter empty line to finish)[/dim]")
    console.print()

    lines = []
    while True:
        line = Prompt.ask("  ", console=console, default="")
        if not line:
            break
        lines.append(line)

    return "\n".join(lines)


def display_info_box(
    console: Console,
    title: str,
    content: str,
    style: str = "cyan",
) -> None:
    """Display an information box with title and content.

    Args:
        console: Rich console for output
        title: Box title
        content: Box content (supports Rich markup)
        style: Border style color

    Example:
        >>> display_info_box(console, "Current Phase", "Phase 2: Validation")
    """
    console.print(Panel(content, title=title, border_style=style))


def display_warning(
    console: Console,
    message: str,
) -> None:
    """Display a warning message.

    Args:
        console: Rich console for output
        message: Warning message to display
    """
    console.print(f"\n  [bold yellow]Warning:[/bold yellow] {message}")


def display_error(
    console: Console,
    message: str,
) -> None:
    """Display an error message.

    Args:
        console: Rich console for output
        message: Error message to display
    """
    console.print(f"\n  [bold red]Error:[/bold red] {message}")


def display_success(
    console: Console,
    message: str,
) -> None:
    """Display a success message.

    Args:
        console: Rich console for output
        message: Success message to display
    """
    console.print(f"\n  [bold green]Success:[/bold green] {message}")
