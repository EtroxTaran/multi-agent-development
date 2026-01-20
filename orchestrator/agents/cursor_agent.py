"""Cursor CLI agent wrapper."""

from pathlib import Path
from typing import Optional

from .base import BaseAgent


class CursorAgent(BaseAgent):
    """Wrapper for Cursor CLI (cursor-agent).

    Cursor is used for validation (code review) and verification phases.
    It auto-reads .cursor/rules and AGENTS.md for context.
    """

    name = "cursor"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 300,
    ):
        """Initialize Cursor agent.

        Args:
            project_dir: Root directory of the project
            timeout: Timeout in seconds
        """
        super().__init__(project_dir, timeout)

    def get_cli_command(self) -> str:
        """Get the CLI command."""
        return "cursor-agent"

    def get_context_file(self) -> Optional[Path]:
        """Get Cursor's context file."""
        # Cursor reads multiple files, return the primary one
        return self.project_dir / "AGENTS.md"

    def get_rules_file(self) -> Optional[Path]:
        """Get Cursor's rules file."""
        return self.project_dir / ".cursor" / "rules"

    def build_command(
        self,
        prompt: str,
        output_format: str = "json",
        force: bool = True,
        **kwargs,
    ) -> list[str]:
        """Build the Cursor CLI command.

        Args:
            prompt: The prompt to send
            output_format: Output format
            force: Force non-interactive mode
            **kwargs: Additional arguments (ignored)

        Returns:
            Command as list of strings

        Note:
            cursor-agent CLI usage:
            - --print or -p: Non-interactive mode (print output, don't open UI)
            - --output-format json: Output as JSON
            - --force: Force execution without confirmation
            - Prompt is a positional argument at the end
        """
        command = [
            "cursor-agent",
            "--print",  # Non-interactive mode
            "--output-format",
            output_format,
        ]

        if force:
            command.append("--force")

        # Prompt must be positional argument at the end
        command.append(prompt)

        return command

    def run_validation(
        self,
        plan: dict,
        output_file: Optional[Path] = None,
    ):
        """Run Cursor for plan validation.

        Args:
            plan: The plan to validate
            output_file: File to write feedback to

        Returns:
            AgentResult with validation feedback
        """
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

        return self.run(prompt, output_file=output_file)

    def run_code_review(
        self,
        files_changed: list[str],
        test_results: dict,
        output_file: Optional[Path] = None,
    ):
        """Run Cursor for code review (verification phase).

        Args:
            files_changed: List of files that were created/modified
            test_results: Results from test execution
            output_file: File to write review to

        Returns:
            AgentResult with code review
        """
        files_list = "\n".join(f"- {f}" for f in files_changed)

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

        return self.run(prompt, output_file=output_file)
