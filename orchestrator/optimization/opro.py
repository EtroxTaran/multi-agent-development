"""OPRO-style prompt optimization.

Uses LLM to generate improved prompts based on examples
of high and low scoring outputs.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Meta-prompt for OPRO optimization
OPRO_META_PROMPT = """You are an expert prompt engineer optimizing prompts for AI agents.

## Current Prompt
```
{current_prompt}
```

## Performance History

Below are examples of outputs from this prompt with their effectiveness scores (1-10):

### High-Scoring Examples (What Works)
{high_scoring_examples}

### Low-Scoring Examples (What Doesn't Work)
{low_scoring_examples}

## Common Issues Identified
{issues}

## Task
Generate an IMPROVED version of the prompt that:
1. Addresses the issues found in low-scoring outputs
2. Preserves the patterns that led to high-scoring outputs
3. Is clear and specific about expected behavior
4. Provides better structure for consistent outputs
5. Is concise without unnecessary verbosity

## Guidelines
- Keep the core functionality intact
- Make instructions more precise where outputs were unclear
- Add constraints or examples if outputs were inconsistent
- Remove or simplify instructions that led to verbose outputs
- Ensure the output format expectations are explicit

## Output
Provide ONLY the improved prompt, no explanations or commentary.
The prompt should be ready to use directly.

---
Improved Prompt:"""


@dataclass
class OPROResult:
    """Result from OPRO optimization."""

    success: bool
    new_prompt: Optional[str] = None
    error: Optional[str] = None
    examples_used: int = 0


class OPROOptimizer:
    """OPRO-style optimizer using LLM to generate better prompts.

    OPRO (Optimization by Prompting) uses a meta-prompt that includes
    examples of high and low scoring outputs to guide the LLM in
    generating an improved prompt.
    """

    def __init__(
        self,
        project_dir: Optional[str] = None,
        project_name: Optional[str] = None,
        optimizer_model: str = "sonnet",
        timeout: int = 120,
        top_k: int = 5,
        bottom_k: int = 3,
    ):
        """Initialize the OPRO optimizer.

        Args:
            project_dir: Project directory
            project_name: Project name for DB access
            optimizer_model: Model to use for optimization
            timeout: Timeout for LLM call
            top_k: Number of high-scoring examples to use
            bottom_k: Number of low-scoring examples to use
        """
        self.project_dir = project_dir or os.getcwd()
        self.project_name = project_name
        self.optimizer_model = optimizer_model
        self.timeout = timeout
        self.top_k = top_k
        self.bottom_k = bottom_k

    async def optimize(
        self,
        template_name: str,
        current_prompt: str,
        evaluation_history: list[dict],
    ) -> OPROResult:
        """Optimize a prompt using OPRO.

        Args:
            template_name: Name of the template
            current_prompt: Current prompt content
            evaluation_history: List of evaluations with scores

        Returns:
            OPROResult with new prompt if successful
        """
        if not evaluation_history:
            return OPROResult(
                success=False,
                error="No evaluation history provided",
            )

        # Sort by score
        sorted_evals = sorted(
            evaluation_history,
            key=lambda x: x.get("overall_score", 0),
        )

        # Get top and bottom examples
        top_examples = sorted_evals[-self.top_k :]
        bottom_examples = sorted_evals[: self.bottom_k]

        # Format examples
        high_scoring = self._format_examples(top_examples, "high")
        low_scoring = self._format_examples(bottom_examples, "low")

        # Extract common issues from low-scoring examples
        issues = self._extract_issues(bottom_examples)

        # Build meta-prompt
        meta_prompt = OPRO_META_PROMPT.format(
            current_prompt=self._truncate(current_prompt, 3000),
            high_scoring_examples=high_scoring,
            low_scoring_examples=low_scoring,
            issues=issues,
        )

        # Call optimizer LLM
        new_prompt = self._call_optimizer(meta_prompt)

        if new_prompt and len(new_prompt.strip()) > 100:
            return OPROResult(
                success=True,
                new_prompt=new_prompt.strip(),
                examples_used=len(top_examples) + len(bottom_examples),
            )
        else:
            return OPROResult(
                success=False,
                error="Optimizer returned empty or invalid prompt",
            )

    def _format_examples(self, examples: list[dict], category: str) -> str:
        """Format examples for the meta-prompt.

        Args:
            examples: List of evaluation records
            category: "high" or "low"

        Returns:
            Formatted string
        """
        if not examples:
            return "No examples available."

        lines = []
        for i, example in enumerate(examples, 1):
            score = example.get("overall_score", "N/A")
            feedback = example.get("feedback", "No feedback")
            suggestions = example.get("suggestions", [])

            lines.append(f"**Example {i}** (Score: {score}/10)")
            lines.append(f"Feedback: {self._truncate(feedback, 300)}")
            if suggestions:
                lines.append(f"Suggestions: {'; '.join(suggestions[:3])}")
            lines.append("")

        return "\n".join(lines)

    def _extract_issues(self, low_scoring: list[dict]) -> str:
        """Extract common issues from low-scoring examples.

        Args:
            low_scoring: List of low-scoring evaluations

        Returns:
            Formatted issues string
        """
        all_suggestions = []
        for example in low_scoring:
            suggestions = example.get("suggestions", [])
            all_suggestions.extend(suggestions)

        # Count frequency
        issue_counts: dict[str, int] = {}
        for suggestion in all_suggestions:
            # Normalize
            normalized = suggestion.lower().strip()[:100]
            issue_counts[normalized] = issue_counts.get(normalized, 0) + 1

        # Sort by frequency
        sorted_issues = sorted(
            issue_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        if not sorted_issues:
            return "No specific issues identified."

        lines = []
        for issue, count in sorted_issues[:5]:
            lines.append(f"- {issue} (occurred {count} times)")

        return "\n".join(lines)

    def _call_optimizer(self, prompt: str) -> Optional[str]:
        """Call the optimizer LLM.

        Args:
            prompt: Meta-prompt for optimization

        Returns:
            Generated prompt or None
        """
        try:
            cmd = [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "text",
                "--max-turns",
                "1",
            ]

            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "TERM": "dumb"},
            )

            if result.returncode != 0:
                logger.warning(f"Optimizer returned non-zero: {result.stderr}")
                return None

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.warning(f"Optimizer timed out after {self.timeout}s")
            return None
        except FileNotFoundError:
            logger.warning("Claude CLI not found")
            return None
        except Exception as e:
            logger.warning(f"Optimizer call failed: {e}")
            return None

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
