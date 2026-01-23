"""Gemini CLI agent wrapper."""

import json
from pathlib import Path
from typing import Optional

from ..config.models import DEFAULT_ARCHITECT_MODEL, DEFAULT_GEMINI_MODEL, GEMINI_MODELS
from .base import BaseAgent
from .prompts import format_prompt, load_prompt

# Available Gemini models
# Managed in orchestrator.config.models


class GeminiAgent(BaseAgent):
    """Wrapper for Gemini CLI.

    Gemini is used for validation and architecture verification phases.
    It reads context from GEMINI.md.

    Supports model selection:
    - gemini-2.0-flash: Fast, cost-effective (default)
    - gemini-2.0-pro: Higher capability for complex tasks
    """

    name = "gemini"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 300,
        model: Optional[str] = None,
    ):
        """Initialize Gemini agent.

        Args:
            project_dir: Root directory of the project
            timeout: Timeout in seconds
            model: Optional model override (gemini-2.0-flash, gemini-2.0-pro)
        """
        super().__init__(project_dir, timeout)
        self.model = model if model in GEMINI_MODELS else DEFAULT_GEMINI_MODEL

    def get_cli_command(self) -> str:
        """Get the CLI command."""
        return "gemini"

    def get_context_file(self) -> Optional[Path]:
        """Get Gemini's context file."""
        return self.project_dir / "GEMINI.md"

    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs,
    ) -> list[str]:
        """Build the Gemini CLI command.

        Args:
            prompt: The prompt to send
            model: Model override (gemini-2.0-flash, gemini-2.0-pro)
            **kwargs: Additional arguments (ignored)

        Returns:
            Command as list of strings

        Note:
            gemini CLI usage:
            - --yolo: Auto-approve tool calls (non-interactive)
            - --model: Model selection
            - Prompt is a positional argument
            - Gemini CLI does NOT support --output-format flag
            - Output must be parsed/wrapped to JSON externally
        """
        command = ["gemini"]

        # Model selection
        selected_model = model or self.model
        if selected_model and selected_model in GEMINI_MODELS:
            command.extend(["--model", selected_model])

        # Auto-approve tool calls for non-interactive use
        command.append("--yolo")

        # Prompt as positional argument
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
    ) -> "AgentResult":
        """Execute the agent with auto-fallback to Claude on quota limits."""
        # Initial run
        result = super().run(prompt, output_file, phase, task_id, session_id, **kwargs)

        # Check for quota/rate limit errors
        error_indicators = [
            "quota",
            "rate limit",
            "429",
            "too many requests",
            "exhausted",
            "resource exhausted",
        ]
        output_check = (result.output or "") + (result.error or "")
        is_quota_error = any(
            indicator.lower() in output_check.lower() for indicator in error_indicators
        )

        if not result.success and is_quota_error:
            # Fallback to Claude
            try:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Gemini quota exhausted (model {kwargs.get('model', self.model)}). "
                    "Falling back to Claude."
                )

                # Import locally to avoid circular imports
                from .claude_agent import ClaudeAgent

                # Instantiate Claude agent
                # Note: valid defaults are handled in ClaudeAgent.__init__
                claude = ClaudeAgent(self.project_dir)

                # Prepare kwargs for Claude
                fallback_kwargs = kwargs.copy()

                # Remove Gemini-specific kwargs that might confuse Claude
                if "model" in fallback_kwargs:
                    del fallback_kwargs["model"]

                # Set specific fallback model for robustness (User mentioned Sonnet or Opus)
                # User preference: Opus for highest quality.
                # We use the configured latest Opus model (2026 standard).
                from ..config.models import CLAUDE_OPUS

                claude_model = CLAUDE_OPUS
                fallback_kwargs["fallback_model"] = claude_model

                logger.info(f"Retrying request with Claude Agent (model: {claude_model})...")

                return claude.run(
                    prompt, output_file, phase, task_id, session_id, **fallback_kwargs
                )
            except Exception as e:
                logger.error(f"Fallback to Claude failed: {e}")
                # Return original result if fallback fails to avoid masking the original error
                # unless we want to try another fallback, but let's stick to one level for now.
                return result

        return result

    def run_validation(
        self,
        plan: dict,
        output_file: Optional[Path] = None,
    ):
        """Run Gemini for plan validation (architecture focus).

        Args:
            plan: The plan to validate
            output_file: File to write feedback to

        Returns:
            AgentResult with validation feedback
        """
        try:
            template = load_prompt("gemini", "validation")
            plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)
            prompt = format_prompt(template, plan=plan_str)
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are a senior software architect validating an implementation plan.

PLAN TO REVIEW:
{plan}

Analyze this plan from an architectural perspective and provide feedback as JSON:
{{
    "reviewer": "gemini",
    "overall_assessment": "approve|needs_changes|reject",
    "score": 1-10,
    "architecture_review": {{
        "patterns_identified": ["List of design patterns used"],
        "scalability_assessment": "good|adequate|poor",
        "maintainability_assessment": "good|adequate|poor",
        "concerns": [
            {{
                "area": "Area of concern",
                "description": "Detailed description",
                "recommendation": "Suggested improvement"
            }}
        ]
    }},
    "dependency_analysis": {{
        "external_dependencies": ["List of external deps"],
        "internal_dependencies": ["Internal module deps"],
        "potential_conflicts": []
    }},
    "integration_considerations": [
        "Things to consider for integration"
    ],
    "alternative_approaches": [
        {{
            "approach": "Alternative approach name",
            "pros": ["Advantages"],
            "cons": ["Disadvantages"],
            "recommendation": "When to consider this"
        }}
    ],
    "summary": "Brief summary of architectural review"
}}

Focus on:
1. Overall architecture and design patterns
2. Scalability and performance implications
3. Integration with existing systems
4. Long-term maintainability
5. Alternative approaches that might be better"""

        return self.run(prompt, output_file=output_file, model=DEFAULT_ARCHITECT_MODEL)

    def run_architecture_review(
        self,
        files_changed: list[str],
        plan: dict,
        output_file: Optional[Path] = None,
    ):
        """Run Gemini for architecture review (verification phase).

        Args:
            files_changed: List of files that were created/modified
            plan: The original implementation plan
            output_file: File to write review to

        Returns:
            AgentResult with architecture review
        """
        files_list = "\n".join(f"- {f}" for f in files_changed)
        plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)

        try:
            template = load_prompt("gemini", "architecture_review")
            prompt = format_prompt(
                template,
                plan=plan_str,
                files_list=files_list,
            )
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are a senior software architect reviewing an implementation.

ORIGINAL PLAN:
{plan}

FILES IMPLEMENTED:
{files_list}

Review the implementation from an architectural perspective and provide feedback as JSON:
{{
    "reviewer": "gemini",
    "approved": true|false,
    "review_type": "architecture_review",
    "plan_adherence": {{
        "followed_plan": true|false,
        "deviations": [
            {{
                "planned": "What was planned",
                "actual": "What was implemented",
                "acceptable": true|false,
                "reason": "Why deviation occurred"
            }}
        ]
    }},
    "architecture_assessment": {{
        "patterns_used": ["Design patterns identified in code"],
        "modularity_score": 1-10,
        "coupling_assessment": "loose|moderate|tight",
        "cohesion_assessment": "high|moderate|low",
        "concerns": []
    }},
    "scalability_assessment": {{
        "current_capacity": "Assessment of current design",
        "bottlenecks": ["Potential bottlenecks"],
        "recommendations": ["Scaling recommendations"]
    }},
    "technical_debt": {{
        "items": [
            {{
                "description": "Technical debt item",
                "severity": "high|medium|low",
                "recommendation": "How to address"
            }}
        ],
        "overall_health": "good|acceptable|concerning"
    }},
    "blocking_issues": [
        "Architectural issues that must be addressed"
    ],
    "summary": "Overall architecture review summary"
}}

Focus on:
1. Adherence to the original plan
2. Code organization and modularity
3. Design pattern usage
4. Scalability potential
5. Technical debt introduced"""

        return self.run(prompt, output_file=output_file, model=DEFAULT_ARCHITECT_MODEL)
