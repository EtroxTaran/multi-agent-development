"""User input manager for workflow interrupts.

Handles displaying workflow interrupts and gathering user responses
for the HITL (Human-in-the-Loop) workflow mode.
"""

import logging
import os
import sys
from typing import Optional

from rich.console import Console

from .interrupt_display import InterruptDisplay
from .prompt_helpers import (
    display_warning,
    prompt_confirm,
    prompt_menu,
    prompt_multiline,
    prompt_text_block,
)


def _is_interactive() -> bool:
    """Check if the current environment supports interactive display.

    Returns:
        True if interactive mode is supported, False otherwise
    """
    # Check CI environment variables
    ci_vars = [
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CIRCLECI",
        "JENKINS_URL",
        "BUILDKITE",
        "TRAVIS",
        "TF_BUILD",
    ]
    for var in ci_vars:
        if os.environ.get(var):
            return False

    # Check explicit flags
    if os.environ.get("ORCHESTRATOR_PLAIN_OUTPUT"):
        return False

    if os.environ.get("NO_COLOR"):
        return False

    # Check if stdout is a TTY
    if not sys.stdout.isatty():
        return False

    return True


logger = logging.getLogger(__name__)


class UserInputManager:
    """Handles interrupt display and user input gathering.

    This class is the main interface for the HITL workflow mode,
    responsible for displaying workflow interrupts and collecting
    user responses.
    """

    # Available actions for escalation interrupts
    ESCALATION_ACTIONS = {
        "retry": "Retry the current phase",
        "skip": "Skip to next phase",
        "continue": "Continue (I fixed it externally)",
        "answer_clarification": "Answer clarification questions",
        "abort": "Abort the workflow",
    }

    # Available actions for approval interrupts
    APPROVAL_ACTIONS = {
        "approve": "Approve and continue",
        "reject": "Reject and abort workflow",
        "request_changes": "Request changes and retry phase",
    }

    def __init__(
        self,
        console: Optional[Console] = None,
        interactive: Optional[bool] = None,
    ):
        """Initialize the user input manager.

        Args:
            console: Rich console instance for output
            interactive: Force interactive mode (auto-detect if None)
        """
        self.console = console or Console()
        self._display = InterruptDisplay(self.console)
        self._interactive = interactive if interactive is not None else _is_interactive()

    @property
    def is_interactive(self) -> bool:
        """Check if running in interactive mode."""
        return self._interactive

    def handle_interrupt(self, interrupt_data: dict) -> dict:
        """Handle a workflow interrupt and return user response.

        This is the main entry point for processing workflow interrupts.
        Routes to specific handlers based on interrupt type.

        Args:
            interrupt_data: Interrupt data containing:
                - type: "escalation" or "approval_required"
                - phase: Current workflow phase
                - ... other type-specific fields

        Returns:
            Dictionary with user response containing:
                - action: The action selected by the user
                - ... additional action-specific fields
        """
        if not self._interactive:
            logger.info("Non-interactive mode: using default response")
            return self._get_non_interactive_default(interrupt_data.get("type", ""))

        interrupt_type = interrupt_data.get("type")

        if interrupt_type == "escalation":
            return self._handle_escalation(interrupt_data)
        elif interrupt_type == "approval_required":
            return self._handle_approval(interrupt_data)
        else:
            logger.warning(f"Unknown interrupt type: {interrupt_type}")
            display_warning(self.console, f"Unknown interrupt type: {interrupt_type}")
            return {"action": "abort", "reason": f"unknown_interrupt_type: {interrupt_type}"}

    def _handle_escalation(self, data: dict) -> dict:
        """Handle an escalation interrupt.

        Displays the escalation context, shows available actions,
        and collects the user's response.

        Args:
            data: Escalation data from the workflow

        Returns:
            Dictionary with:
                - action: Selected action (retry, skip, continue, answer_clarification, abort)
                - answers: Clarification answers if action is answer_clarification
                - feedback: User feedback if provided
        """
        # Display the escalation information
        self._display.display_escalation(data)
        self._display.display_separator()

        # Check if clarifications are available
        clarifications = data.get("clarifications", [])
        has_clarifications = bool(clarifications)

        # Build action list
        actions = list(self.ESCALATION_ACTIONS.keys())
        if not has_clarifications:
            actions = [a for a in actions if a != "answer_clarification"]

        # Display action menu
        action_descriptions = [self.ESCALATION_ACTIONS[a] for a in actions]
        idx, _ = prompt_menu(
            self.console,
            action_descriptions,
            "Choose an action",
            default=1,  # Default to retry
        )
        action = actions[idx]

        response = {"action": action}

        # Handle action-specific follow-up
        if action == "answer_clarification":
            answers = self._collect_answers(clarifications)
            response["answers"] = answers
        elif action == "skip":
            # Confirm skip action
            if not prompt_confirm(self.console, "Are you sure you want to skip this phase?"):
                return self._handle_escalation(data)  # Re-prompt
        elif action == "abort":
            # Confirm abort
            if not prompt_confirm(self.console, "Are you sure you want to abort the workflow?"):
                return self._handle_escalation(data)  # Re-prompt
            # Optionally collect reason
            reason = prompt_multiline(
                self.console,
                "Reason for aborting (optional)",
                hint="Press Enter to skip",
            )
            if reason:
                response["reason"] = reason

        return response

    def _handle_approval(self, data: dict) -> dict:
        """Handle an approval interrupt.

        Displays the approval context and collects user's decision.

        Args:
            data: Approval data from the workflow

        Returns:
            Dictionary with:
                - action: Selected action (approve, reject, request_changes)
                - feedback: User feedback if action is reject or request_changes
        """
        # Display the approval information
        self._display.display_approval(data)
        self._display.display_separator()

        # Display action menu
        actions = list(self.APPROVAL_ACTIONS.keys())
        action_descriptions = [self.APPROVAL_ACTIONS[a] for a in actions]
        idx, _ = prompt_menu(
            self.console,
            action_descriptions,
            "Choose approval action",
            default=1,  # Default to approve
        )
        action = actions[idx]

        response = {"action": action}

        # Collect feedback for reject/request_changes
        if action in ("reject", "request_changes"):
            prompt_msg = "Provide feedback" if action == "reject" else "Describe the changes needed"
            feedback = prompt_text_block(
                self.console,
                prompt_msg,
                hint="Enter your feedback (empty line to finish)",
            )
            response["feedback"] = feedback

            # Confirm rejection
            if action == "reject":
                if not prompt_confirm(self.console, "Are you sure you want to reject and abort?"):
                    return self._handle_approval(data)  # Re-prompt

        return response

    def _collect_answers(self, questions: list[dict]) -> dict:
        """Collect answers for clarification questions.

        Args:
            questions: List of question dictionaries with:
                - id: Question identifier
                - question: Question text
                - options: Optional list of answer options

        Returns:
            Dictionary mapping question IDs to answers
        """
        answers = {}

        self.console.print()
        self.console.print("[bold]Please answer the following questions:[/bold]")
        self.console.print()

        for i, q in enumerate(questions):
            q_id = q.get("id", f"q{i}")
            text = q.get("question", f"Question {i + 1}")
            options = q.get("options", [])

            self.console.print(f"[bold cyan]Q{i + 1}:[/bold cyan] {text}")

            if options:
                # Multiple choice with custom option
                idx, answer = prompt_menu(
                    self.console,
                    options,
                    allow_custom=True,
                )
            else:
                # Free text input
                answer = prompt_multiline(self.console, "Your answer")

            answers[q_id] = answer
            self.console.print()

        return answers

    def _get_non_interactive_default(self, interrupt_type: str) -> dict:
        """Get safe default response for non-interactive mode.

        In CI or non-TTY environments, we need to provide a safe
        default response that won't cause data loss.

        Args:
            interrupt_type: Type of interrupt

        Returns:
            Safe default response dictionary
        """
        logger.info(f"Non-interactive default for {interrupt_type}")

        if interrupt_type == "escalation":
            return {
                "action": "abort",
                "reason": "Non-interactive mode - cannot collect human input",
            }
        elif interrupt_type == "approval_required":
            return {
                "action": "reject",
                "feedback": "Non-interactive mode - cannot approve without human review",
            }
        else:
            return {
                "action": "abort",
                "reason": f"Unknown interrupt type in non-interactive mode: {interrupt_type}",
            }

    def prompt_for_response(self, message: str, options: Optional[list[str]] = None) -> str:
        """Simple prompt for user response (for direct usage).

        Args:
            message: Message to display
            options: Optional list of valid options

        Returns:
            User's response string
        """
        if not self._interactive:
            return ""

        if options:
            idx, value = prompt_menu(self.console, options, message, allow_custom=True)
            return value
        else:
            return prompt_multiline(self.console, message)
