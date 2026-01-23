"""Few-shot bootstrapping for prompt optimization.

Generates improved prompts by incorporating high-quality
examples directly into the prompt as few-shot demonstrations.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Template for bootstrap optimization
BOOTSTRAP_TEMPLATE = '''You are an expert prompt engineer adding few-shot examples to improve prompt effectiveness.

## Current Prompt
```
{current_prompt}
```

## Golden Examples
These are high-quality outputs that scored >= 9.0:

{golden_examples}

## Task
Generate an improved prompt that:
1. Incorporates 2-3 of the best examples as few-shot demonstrations
2. Maintains the original prompt's core instructions
3. Uses examples to clarify expected output format and quality
4. Keeps the prompt concise (examples should be brief but representative)

## Guidelines
- Place examples after the main instructions
- Format examples clearly with "Example Input:" and "Example Output:"
- Choose diverse examples that cover different aspects
- Truncate long outputs to key parts that demonstrate quality
- Don't just append examples - integrate them naturally

## Output
Provide ONLY the improved prompt with integrated examples.
No explanations or commentary.

---
Improved Prompt with Examples:'''


@dataclass
class BootstrapResult:
    """Result from bootstrap optimization."""

    success: bool
    new_prompt: Optional[str] = None
    error: Optional[str] = None
    examples_used: int = 0


class BootstrapOptimizer:
    """Bootstrap optimizer using few-shot examples.

    Takes golden examples (high-scoring outputs) and incorporates
    them into the prompt as few-shot demonstrations.
    """

    def __init__(
        self,
        project_dir: Optional[str] = None,
        project_name: Optional[str] = None,
        optimizer_model: str = "sonnet",
        timeout: int = 120,
        max_examples: int = 5,
    ):
        """Initialize the bootstrap optimizer.

        Args:
            project_dir: Project directory
            project_name: Project name for DB access
            optimizer_model: Model for prompt generation
            timeout: Timeout for LLM call
            max_examples: Maximum examples to use
        """
        self.project_dir = project_dir or os.getcwd()
        self.project_name = project_name
        self.optimizer_model = optimizer_model
        self.timeout = timeout
        self.max_examples = max_examples

        # Lazy-loaded repository
        self._golden_repo = None

    @property
    def golden_repo(self):
        if self._golden_repo is None:
            from ..db.repositories import get_golden_example_repository
            self._golden_repo = get_golden_example_repository(self.project_name)
        return self._golden_repo

    async def optimize(
        self,
        agent: str,
        template_name: str,
        current_prompt: str,
    ) -> BootstrapResult:
        """Optimize a prompt using bootstrap method.

        Args:
            agent: Agent name
            template_name: Template identifier
            current_prompt: Current prompt content

        Returns:
            BootstrapResult with new prompt if successful
        """
        # Get golden examples
        examples = await self.golden_repo.get_by_template(
            agent=agent,
            template_name=template_name,
            limit=self.max_examples,
            min_score=9.0,
        )

        if len(examples) < 2:
            return BootstrapResult(
                success=False,
                error=f"Insufficient golden examples: {len(examples)} < 2",
            )

        # Format examples
        formatted = self._format_golden_examples(examples)

        # Build bootstrap prompt
        bootstrap_prompt = BOOTSTRAP_TEMPLATE.format(
            current_prompt=self._truncate(current_prompt, 3000),
            golden_examples=formatted,
        )

        # Generate improved prompt
        new_prompt = self._call_optimizer(bootstrap_prompt)

        if new_prompt and len(new_prompt.strip()) > 100:
            return BootstrapResult(
                success=True,
                new_prompt=new_prompt.strip(),
                examples_used=len(examples),
            )
        else:
            return BootstrapResult(
                success=False,
                error="Optimizer returned empty or invalid prompt",
            )

    def _format_golden_examples(self, examples: list[dict]) -> str:
        """Format golden examples for the bootstrap prompt.

        Args:
            examples: List of golden example records

        Returns:
            Formatted string
        """
        lines = []
        for i, example in enumerate(examples, 1):
            score = example.get("score", "N/A")
            input_prompt = example.get("input_prompt", "")
            output = example.get("output", "")

            lines.append(f"### Example {i} (Score: {score}/10)")
            lines.append("")
            lines.append("**Input:**")
            lines.append(f"```\n{self._truncate(input_prompt, 500)}\n```")
            lines.append("")
            lines.append("**Output:**")
            lines.append(f"```\n{self._truncate(output, 1000)}\n```")
            lines.append("")

        return "\n".join(lines)

    def _call_optimizer(self, prompt: str) -> Optional[str]:
        """Call the optimizer LLM.

        Args:
            prompt: Bootstrap prompt

        Returns:
            Generated prompt or None
        """
        try:
            cmd = [
                "claude",
                "-p", prompt,
                "--output-format", "text",
                "--max-turns", "1",
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

    async def generate_few_shot_section(
        self,
        agent: str,
        template_name: str,
        num_examples: int = 2,
    ) -> Optional[str]:
        """Generate a few-shot examples section to append to a prompt.

        This is a lighter-weight option that just generates the examples
        section without rewriting the entire prompt.

        Args:
            agent: Agent name
            template_name: Template identifier
            num_examples: Number of examples to include

        Returns:
            Few-shot section or None
        """
        examples = await self.golden_repo.get_by_template(
            agent=agent,
            template_name=template_name,
            limit=num_examples,
            min_score=9.0,
        )

        if not examples:
            return None

        lines = ["\n## Examples\n"]
        for i, example in enumerate(examples, 1):
            input_prompt = example.get("input_prompt", "")
            output = example.get("output", "")

            lines.append(f"### Example {i}")
            lines.append("")
            lines.append("**Input:**")
            lines.append(f"{self._truncate(input_prompt, 300)}")
            lines.append("")
            lines.append("**Output:**")
            lines.append(f"{self._truncate(output, 500)}")
            lines.append("")

        return "\n".join(lines)
