"""Cursor CLI agent wrapper."""

import json
import logging
from pathlib import Path
from typing import Literal, Optional

from ..config.models import CURSOR_MODELS, DEFAULT_CURSOR_MODEL
from .base import AgentResult, BaseAgent
from .prompts import format_prompt, load_prompt

logger = logging.getLogger(__name__)

# Available Cursor models
# Managed in orchestrator.config.models

# Available agent modes (Jan 2026 CLI update)
# NOTE: 'plan' mode is interactive-only and should NOT be used for headless automation.
# For headless analysis, use 'ask' mode instead.
CURSOR_MODES = {"agent", "plan", "ask"}
HEADLESS_SAFE_MODES = {"agent", "ask"}  # Modes safe for non-interactive use
DEFAULT_CURSOR_MODE = "agent"


class CursorAgent(BaseAgent):
    """Wrapper for Cursor CLI (cursor-agent).

    Cursor is used for validation (code review) and verification phases.
    It auto-reads .cursor/rules and AGENTS.md for context.

    Supports model selection:
    - codex-5.2: High capability model (default)
    - composer: Cheaper, faster model for simpler tasks

    Supports agent modes (Jan 2026 CLI update):
    - agent: Execute changes directly (default)
    - plan: Research, ask questions, create plan before coding (INTERACTIVE ONLY)
    - ask: Explore code without making changes (use for headless analysis)

    NOTE: Plan mode requires interactive input (clarifying questions, plan approval).
    For headless/automation use cases (orchestrator), use 'ask' mode or
    the run_analysis() method instead.
    """

    name = "cursor"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 300,
        model: Optional[str] = None,
        mode: Optional[Literal["agent", "plan", "ask"]] = None,
    ):
        """Initialize Cursor agent.

        Args:
            project_dir: Root directory of the project
            timeout: Timeout in seconds
            model: Optional model override (codex-5.2, composer)
            mode: Optional agent mode (agent, plan, ask). Default is agent.
        """
        super().__init__(project_dir, timeout)
        self.model = model if model in CURSOR_MODELS else DEFAULT_CURSOR_MODEL
        self.mode = mode if mode in CURSOR_MODES else DEFAULT_CURSOR_MODE

    def get_cli_command(self) -> str:
        """Get the CLI command."""
        return "cursor-agent"

    def get_context_file(self) -> Optional[Path]:
        """Get Cursor's context file."""
        # Cursor reads multiple files, return the primary one
        return Path(self.project_dir) / "AGENTS.md"

    def get_rules_file(self) -> Optional[Path]:
        """Get Cursor's rules file."""
        return Path(self.project_dir) / ".cursor" / "rules"

    def build_command(
        self,
        prompt: str,
        output_format: str = "json",
        force: bool = True,
        model: Optional[str] = None,
        mode: Optional[Literal["agent", "plan", "ask"]] = None,
        resume: Optional[str] = None,
        **kwargs,
    ) -> list[str]:
        """Build the Cursor CLI command.

        Args:
            prompt: The prompt to send
            output_format: Output format
            force: Force non-interactive mode
            model: Model override (codex-5.2, composer)
            mode: Agent mode (agent, plan, ask). Jan 2026 CLI feature.
            resume: Thread ID to resume previous session
            **kwargs: Additional arguments (ignored)

        Returns:
            Command as list of strings

        Note:
            cursor-agent CLI usage:
            - --print or -p: Non-interactive mode (print output, don't open UI)
            - --output-format json: Output as JSON
            - --force: Force execution without confirmation
            - --model: Model selection (codex-5.2, composer)
            - --mode: Agent mode (agent, plan, ask) - Jan 2026 CLI feature
            - --resume: Resume previous thread by ID
            - Prompt is a positional argument at the end
        """
        command = [
            "cursor-agent",
            "--print",  # Non-interactive mode
            "--output-format",
            output_format,
        ]

        # Model selection
        selected_model = model or self.model
        if selected_model and selected_model in CURSOR_MODELS:
            command.extend(["--model", selected_model])

        # Mode selection (Jan 2026 CLI feature)
        selected_mode = mode or self.mode
        if selected_mode and selected_mode in CURSOR_MODES:
            # Warn if plan mode is used - it requires interactive input
            if selected_mode == "plan":
                logger.warning(
                    "Plan mode requires interactive input (clarifying questions, plan approval). "
                    "For headless/automation, consider using 'ask' mode instead via run_analysis()."
                )
            command.extend(["--mode", selected_mode])

        # Resume previous session
        if resume:
            command.extend(["--resume", resume])

        if force:
            command.append("--force")

        # Prompt must be positional argument at the end
        command.append(prompt)

        return command

    def run(
        self,
        prompt: str,
        output_file: Optional[Path] = None,
        phase: Optional[int] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AgentResult:
        """Execute the agent with auto-fallback for quota limits."""
        # Initial run
        result = super().run(prompt, output_file, phase, task_id, session_id, **kwargs)

        # Check for quota/rate limit errors
        # cursor-agent might output to stdout or stderr depending on implementation
        error_indicators = ["quota", "rate limit", "429", "too many requests", "exhausted"]
        output_check = (result.output or "") + (result.error or "")

        is_quota_error = any(
            indicator.lower() in output_check.lower() for indicator in error_indicators
        )

        if not result.success and is_quota_error:
            # check if we are already in auto mode
            current_model = kwargs.get("model", self.model)

            if current_model != "auto":
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Cursor quota exhausted for model {current_model}. Switching to 'auto' model."
                )

                # Retry with auto model
                # We need to update kwargs to override any previous model setting
                kwargs["model"] = "auto"

                return super().run(prompt, output_file, phase, task_id, session_id, **kwargs)

        return result

    def run_analysis(
        self,
        prompt: str,
        output_file: Optional[Path] = None,
        **kwargs,
    ) -> AgentResult:
        """Run Cursor in ask mode for headless read-only analysis.

        Ask mode (Jan 2026 CLI feature) enables Cursor to explore code
        without making changes - ideal for headless automation like
        the orchestrator workflow.

        Use this for:
        - Code reviews in Phase 4 verification
        - Plan validation in Phase 2
        - Any automated analysis that shouldn't modify code

        Args:
            prompt: The prompt to send
            output_file: File to write output to
            **kwargs: Additional arguments passed to run()

        Returns:
            AgentResult with analysis output
        """
        return self.run(prompt, output_file=output_file, mode="ask", **kwargs)

    def run_with_plan_mode(
        self,
        prompt: str,
        output_file: Optional[Path] = None,
        **kwargs,
    ) -> AgentResult:
        """Run Cursor in plan mode for complex validations.

        WARNING: Plan mode requires interactive input (clarifying questions,
        plan approval). It should NOT be used for headless automation.
        For headless analysis, use run_analysis() instead.

        Plan mode (Jan 2026 CLI feature) enables Cursor to:
        1. Ask clarifying questions
        2. Research the codebase for context
        3. Create a comprehensive implementation plan
        4. Execute only after plan is approved

        Use this ONLY for interactive development scenarios.

        Args:
            prompt: The prompt to send
            output_file: File to write output to
            **kwargs: Additional arguments passed to run()

        Returns:
            AgentResult with plan mode output
        """
        logger.warning(
            "run_with_plan_mode() uses interactive plan mode. "
            "For headless automation, use run_analysis() instead."
        )
        return self.run(prompt, output_file=output_file, mode="plan", **kwargs)

    def run_validation(
        self,
        plan: dict,
        output_file: Optional[Path] = None,
        use_ask_mode: bool = False,
    ):
        """Run Cursor for plan validation.

        Args:
            plan: The plan to validate
            output_file: File to write feedback to
            use_ask_mode: If True, use ask mode for deep analysis without changes.
                         (Previously use_plan_mode, but plan mode is interactive-only)

        Returns:
            AgentResult with validation feedback
        """
        try:
            template = load_prompt("cursor", "validation")
            plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)
            prompt = format_prompt(template, plan=plan_str)
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are a senior code reviewer validating an implementation plan.

PLAN TO REVIEW:
{plan}

Analyze this plan and provide feedback as JSON:
{{
    "reviewer": "cursor",
    "overall_assessment": "approve|needs_changes|reject",
    "score": 1-10,
    "strengths": [
        "List of plan strengths"
    ],
    "concerns": [
        {{
            "severity": "high|medium|low",
            "area": "Area of concern",
            "description": "Detailed description",
            "suggestion": "How to address it"
        }}
    ],
    "missing_elements": [
        "Any missing elements in the plan"
    ],
    "security_review": {{
        "issues": [],
        "recommendations": []
    }},
    "maintainability_review": {{
        "concerns": [],
        "suggestions": []
    }},
    "summary": "Brief summary of your review"
}}

Focus on:
1. Code quality and best practices
2. Security vulnerabilities
3. Maintainability and readability
4. Test coverage adequacy
5. Error handling completeness"""

        mode = "ask" if use_ask_mode else None
        return self.run(prompt, output_file=output_file, mode=mode)

    def run_code_review(
        self,
        files_changed: list[str],
        test_results: dict,
        output_file: Optional[Path] = None,
        use_ask_mode: bool = False,
    ):
        """Run Cursor for code review (verification phase).

        Args:
            files_changed: List of files that were created/modified
            test_results: Results from test execution
            output_file: File to write review to
            use_ask_mode: If True, use ask mode for deep analysis without changes.
                         (Previously use_plan_mode, but plan mode is interactive-only)

        Returns:
            AgentResult with code review
        """
        files_list = "\n".join(f"- {f}" for f in files_changed)
        test_results_str = (
            json.dumps(test_results, indent=2)
            if isinstance(test_results, dict)
            else str(test_results)
        )

        try:
            template = load_prompt("cursor", "code_review")
            prompt = format_prompt(
                template,
                files_list=files_list,
                test_results=test_results_str,
            )
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are a senior code reviewer performing a detailed code review.

FILES TO REVIEW:
{files_list}

TEST RESULTS:
{test_results}

Review each file and provide feedback as JSON:
{{
    "reviewer": "cursor",
    "approved": true|false,
    "review_type": "code_review",
    "files_reviewed": [
        {{
            "file": "path/to/file",
            "status": "approved|needs_changes",
            "issues": [
                {{
                    "line": 42,
                    "severity": "error|warning|info",
                    "type": "bug|security|style|performance",
                    "description": "Issue description",
                    "suggestion": "How to fix"
                }}
            ],
            "positive_feedback": ["Good practices observed"]
        }}
    ],
    "overall_code_quality": 1-10,
    "test_coverage_assessment": "adequate|insufficient|excellent",
    "security_assessment": "pass|fail|needs_review",
    "blocking_issues": [
        "List of issues that must be fixed before merge"
    ],
    "summary": "Overall review summary"
}}

Focus on:
1. Code correctness and bug detection
2. Security vulnerabilities (OWASP Top 10)
3. Performance issues
4. Code style and consistency
5. Test quality and coverage"""

        mode = "ask" if use_ask_mode else None
        return self.run(prompt, output_file=output_file, mode=mode)
