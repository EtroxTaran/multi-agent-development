"""Security Specialist Agent for security concern analysis.

This agent reviews security concerns flagged by Cursor/Gemini and:
1. Classifies concerns as implementation flaws vs specification gaps
2. Provides best practice recommendations
3. Only escalates to human when genuinely ambiguous

Uses Claude as the backend with specialized security prompts.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .base import AgentResult, BaseAgent
from .prompts import format_prompt, load_prompt

logger = logging.getLogger(__name__)


@dataclass
class SecurityAnalysisResult:
    """Result from security specialist analysis.

    Attributes:
        success: Whether analysis completed successfully
        concerns_reviewed: Number of concerns reviewed
        reclassifications: Concerns reclassified from HIGH to MEDIUM
        confirmed_vulnerabilities: Actual vulnerabilities confirmed as HIGH
        human_escalation_required: Whether human input is needed
        escalation_questions: Questions for human if escalation needed
        recommendation: Overall recommendation (approve_with_feedback|needs_changes|escalate)
        raw_output: Full raw output from the agent
    """

    success: bool
    concerns_reviewed: int = 0
    reclassifications: list[dict[str, Any]] = field(default_factory=list)
    confirmed_vulnerabilities: list[dict[str, Any]] = field(default_factory=list)
    human_escalation_required: bool = False
    escalation_questions: list[str] = field(default_factory=list)
    recommendation: str = "approve_with_feedback"
    raw_output: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "concerns_reviewed": self.concerns_reviewed,
            "reclassifications": self.reclassifications,
            "confirmed_vulnerabilities": self.confirmed_vulnerabilities,
            "human_escalation_required": self.human_escalation_required,
            "escalation_questions": self.escalation_questions,
            "recommendation": self.recommendation,
            "raw_output": self.raw_output,
        }


class SecuritySpecialistAgent(BaseAgent):
    """Security Specialist agent for analyzing security concerns.

    This agent reviews security concerns from Cursor/Gemini validation and:
    - Distinguishes implementation flaws (actual vulnerabilities) from spec gaps
    - Provides best practice recommendations for spec gaps
    - Only escalates to human when there's genuine ambiguity

    Uses Claude Code CLI as the backend with specialized security prompts.
    """

    name = "security_specialist"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 300,
        phase_timeouts: Optional[dict[int, int]] = None,
        enable_audit: bool = True,
    ):
        """Initialize Security Specialist agent.

        Args:
            project_dir: Root directory of the project
            timeout: Timeout in seconds (default 5 minutes)
            phase_timeouts: Optional per-phase timeout overrides
            enable_audit: Whether to enable audit trail logging
        """
        super().__init__(project_dir, timeout, phase_timeouts, enable_audit)

    def get_cli_command(self) -> str:
        """Get the CLI command."""
        return "claude"

    def get_context_file(self) -> Optional[Path]:
        """Get the context file path."""
        return Path(self.project_dir) / "CLAUDE.md"

    def build_command(self, prompt: str, **kwargs) -> list[str]:
        """Build the Claude CLI command.

        Args:
            prompt: The security analysis prompt
            **kwargs: Additional arguments

        Returns:
            Command as list of strings
        """
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            "3",  # Quick analysis, don't need many turns
        ]

        # Add budget control
        cmd.extend(["--max-budget-usd", "0.50"])

        return cmd

    def analyze_concerns(
        self,
        concerns: list[dict],
        project_context: Optional[str] = None,
        security_docs: Optional[str] = None,
    ) -> SecurityAnalysisResult:
        """Analyze security concerns and classify them.

        Args:
            concerns: List of security concerns from Cursor/Gemini
            project_context: Optional project context (plan summary, etc.)
            security_docs: Optional security documentation content

        Returns:
            SecurityAnalysisResult with classifications and recommendations
        """
        if not concerns:
            return SecurityAnalysisResult(
                success=True,
                concerns_reviewed=0,
                recommendation="approve_with_feedback",
            )

        # Load and format the prompt
        try:
            template = load_prompt("security_specialist", "analysis")
        except FileNotFoundError:
            template = load_prompt("security", "specialist")

        concerns_json = json.dumps(concerns, indent=2)
        project_ctx = project_context or "No additional context provided."
        sec_docs = security_docs or "No security documentation provided."

        prompt = format_prompt(
            template,
            concerns=concerns_json,
            project_context=project_ctx,
            security_docs=sec_docs,
        )

        # Execute the analysis
        result = self.run(prompt)

        if not result.success:
            logger.error(f"Security specialist analysis failed: {result.error}")
            return SecurityAnalysisResult(
                success=False,
                raw_output={"error": result.error},
            )

        # Parse the output
        return self._parse_analysis_result(result)

    def _parse_analysis_result(self, result: AgentResult) -> SecurityAnalysisResult:
        """Parse the agent result into SecurityAnalysisResult.

        Args:
            result: Raw agent result

        Returns:
            Parsed SecurityAnalysisResult
        """
        output = result.parsed_output or {}

        # Handle Claude CLI JSON envelope format
        if "result" in output:
            content = output.get("result", "")
            # Extract JSON from content
            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
            if json_match:
                try:
                    output = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            if not output.get("specialist"):
                # Try raw JSON extraction
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        output = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass

        summary = output.get("summary", {})

        return SecurityAnalysisResult(
            success=True,
            concerns_reviewed=summary.get(
                "total_concerns", len(output.get("reclassifications", []))
            ),
            reclassifications=output.get("reclassifications", []),
            confirmed_vulnerabilities=output.get("confirmed_vulnerabilities", []),
            human_escalation_required=output.get("human_escalation_required", False),
            escalation_questions=output.get("escalation_questions", []),
            recommendation=summary.get("recommendation", "approve_with_feedback"),
            raw_output=output,
        )

    def get_best_practice(self, concern_area: str) -> dict[str, Any]:
        """Get best practice recommendation for a security concern area.

        This provides quick inline recommendations without calling the agent.

        Args:
            concern_area: The security concern area (e.g., "rate_limiting", "csrf")

        Returns:
            Best practice recommendation dict
        """
        best_practices: dict[str, dict[str, Any]] = {
            "rate_limiting": {
                "area": "Rate Limiting",
                "recommendation": "Implement sliding window rate limiting",
                "default_limits": {
                    "login": "5 attempts per 15 minutes per IP",
                    "api_authenticated": "100 requests per minute",
                    "api_public": "30 requests per minute",
                    "password_reset": "3 requests per hour",
                },
                "implementation": "Use redis-based sliding window or in-memory for small scale",
                "reference": "OWASP Rate Limiting Cheatsheet",
            },
            "csrf": {
                "area": "CSRF Protection",
                "recommendation": "Use double submit cookie pattern",
                "cookie_settings": "SameSite=Strict, Secure, HTTP-only",
                "implementation": "Generate cryptographically random 32-byte tokens",
                "reference": "OWASP CSRF Prevention Cheatsheet",
            },
            "session_management": {
                "area": "Session Management",
                "recommendation": "JWT with short-lived access + long-lived refresh tokens",
                "access_token_expiry": "15 minutes",
                "refresh_token_expiry": "7 days",
                "storage": "HTTP-only, Secure, SameSite=Strict cookies",
                "rotation": "Rotate refresh tokens on each use",
                "reference": "OWASP Session Management Cheatsheet",
            },
            "password_storage": {
                "area": "Password Storage",
                "recommendation": "Argon2id with appropriate parameters",
                "parameters": "time=3, memory=64MB, parallelism=4",
                "alternative": "bcrypt with cost factor 12 if Argon2 unavailable",
                "reference": "OWASP Password Storage Cheatsheet",
            },
            "input_validation": {
                "area": "Input Validation",
                "recommendation": "Validate at system boundaries, escape for context",
                "strategies": {
                    "html": "HTML entity encoding",
                    "sql": "Parameterized queries",
                    "shell": "Avoid shell execution; if required, use allowlists",
                    "file_path": "Resolve and validate against allowed base paths",
                },
                "reference": "OWASP Input Validation Cheatsheet",
            },
            "authentication": {
                "area": "Authentication",
                "recommendation": "Multi-factor with secure password hashing",
                "password_requirements": "Minimum 8 chars, check against common passwords",
                "mfa": "TOTP-based with recovery codes",
                "lockout": "Temporary lockout after 5 failures",
                "reference": "OWASP Authentication Cheatsheet",
            },
        }

        # Normalize the concern area
        normalized = concern_area.lower().replace(" ", "_").replace("-", "_")

        # Find matching best practice
        for key, value in best_practices.items():
            if key in normalized or normalized in key:
                return value

        # Return generic recommendation if not found
        return {
            "area": concern_area,
            "recommendation": "Follow OWASP guidelines for this area",
            "reference": "OWASP Cheatsheet Series",
        }

    def reclassify_concern(
        self,
        concern: dict,
        security_docs_available: bool = False,
    ) -> dict:
        """Quick reclassification of a concern without calling the agent.

        This is a heuristic-based reclassification for common patterns.

        Args:
            concern: The security concern dict
            security_docs_available: Whether security-requirements.md exists

        Returns:
            Reclassified concern dict with added fields
        """
        description = concern.get("description", "").lower()
        severity = concern.get("severity", "medium")
        concern_type = concern.get("concern_type", "")

        # Already classified as specification_gap
        if concern_type == "specification_gap":
            return {
                **concern,
                "reclassified": False,
                "classification": "specification_gap",
            }

        # Patterns indicating specification gaps (not actual vulnerabilities)
        spec_gap_patterns = [
            r"no (?:mention|rate limiting|csrf|session|authentication|authorization)",
            r"(?:missing|lacks|not defined|not specified|unclear)",
            r"(?:should|recommend|consider) (?:add|include|implement)",
            r"no explicit (?:strategy|policy|mechanism|validation)",
            r"plan (?:lacks|doesn't|does not)",
        ]

        # Patterns indicating actual implementation flaws
        impl_flaw_patterns = [
            r"sql injection",
            r"xss vulnerability",
            r"command injection",
            r"path traversal",
            r"hardcoded (?:secret|credential|password|key)",
            r"insecure (?:deserialization|direct object)",
            r"string concatenation.+query",
            r"eval\(|exec\(",
        ]

        # Check for implementation flaws first (higher priority)
        for pattern in impl_flaw_patterns:
            if re.search(pattern, description):
                return {
                    **concern,
                    "reclassified": False,
                    "classification": "implementation_flaw",
                    "blocks_plan": True,
                }

        # Check for specification gaps
        for pattern in spec_gap_patterns:
            if re.search(pattern, description):
                # Get best practice for this type of concern
                area = concern.get("area", "security").lower()
                best_practice = self.get_best_practice(area)

                return {
                    **concern,
                    "reclassified": True,
                    "original_severity": severity,
                    "severity": "medium",
                    "classification": "specification_gap",
                    "blocks_plan": False,
                    "best_practice": best_practice,
                    "covered_by_docs": security_docs_available,
                }

        # If HIGH severity but doesn't match patterns, keep as-is but flag for review
        if severity == "high":
            return {
                **concern,
                "reclassified": False,
                "classification": "needs_review",
                "blocks_plan": True,
            }

        # Default: keep as-is
        return {
            **concern,
            "reclassified": False,
            "classification": concern_type or "unknown",
        }


def get_security_specialist(project_dir: str | Path) -> SecuritySpecialistAgent:
    """Factory function to get a Security Specialist agent.

    Args:
        project_dir: Project directory path

    Returns:
        Configured SecuritySpecialistAgent instance
    """
    return SecuritySpecialistAgent(project_dir=project_dir)
