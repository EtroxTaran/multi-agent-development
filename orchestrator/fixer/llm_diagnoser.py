"""LLM-based diagnosis engine for complex error analysis.

This module provides deep semantic analysis of errors using LLMs when
simple pattern matching fails. It can understand logic errors,
API misuse, and complex system interactions.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Any

from orchestrator.agents.adapter import create_adapter, AgentType
from orchestrator.fixer.triage import FixerError, ErrorCategory
from orchestrator.fixer.diagnosis import (
    DiagnosisResult,
    RootCause,
    DiagnosisConfidence,
    AffectedFile,
)

logger = logging.getLogger(__name__)


class LLMDiagnosisEngine:
    """LLM-based diagnosis engine."""

    def __init__(self, project_dir: str | Path):
        """Initialize the LLM diagnosis engine.

        Args:
            project_dir: Project directory path
        """
        self.project_dir = Path(project_dir)
        # Use Claude for deep reasoning, fallback to others if needed
        try:
            self.agent = create_adapter(AgentType.CLAUDE, self.project_dir)
        except Exception as e:
            logger.warning(f"Failed to initialize Claude adapter for diagnosis: {e}")
            self.agent = None

    async def diagnose(
        self,
        error: FixerError,
        category: ErrorCategory,
        affected_files: list[AffectedFile],
        context: Optional[dict] = None,
    ) -> Optional[DiagnosisResult]:
        """Diagnose an error using LLM analysis.

        Args:
            error: The error to diagnose
            category: Error category from triage
            affected_files: List of files identified as affected
            context: Additional context dictionary

        Returns:
            DiagnosisResult or None if analysis failed
        """
        if not self.agent:
            return None

        # Build prompt context
        file_context = ""
        for file in affected_files:
            if file.snippet:
                file_context += f"\nFile: {file.path}\n```\n{file.snippet}\n```\n"

        prompt = f"""
You are an expert software debugger. Analyze the following error and provide a deep diagnosis.

ERROR DETAILS:
Type: {error.error_type}
Message: {error.message}
Location: {error.source or "Unknown"}

STACK TRACE:
{error.stack_trace or "None"}

CODE CONTEXT:
{file_context}

YOUR TASK:
1. Analyze the root cause of the error. Is it a logic error, API misuse, missing handling, etc.?
2. Determine the best fix strategy.
3. Provide specific code suggestions.

RESPONSE FORMAT:
You MUST respond with a valid JSON object matching this structure:
{{
    "root_cause": "One of: {', '.join([r.value for r in RootCause])}",
    "confidence": "high|medium|low",
    "explanation": "Clear explanation of why the error occurred",
    "suggested_fixes": ["Fix 1", "Fix 2"],
    "affected_files": [
        {{
            "path": "path/to/file",
            "line_number": 123,
            "snippet": "code snippet",
            "suggested_fix": "specific code change"
        }}
    ]
}}
"""
        
        try:
            # Run LLM analysis
            result = await self.agent.run_iteration(prompt, timeout=120)
            
            # Parse JSON output
            analysis = self._parse_llm_output(result.output)
            if not analysis:
                return None

            # Map generic root cause if needed
            root_cause_str = analysis.get("root_cause", "unknown")
            try:
                root_cause = RootCause(root_cause_str)
            except ValueError:
                # Map unknown strings to UNKNOWN or best guess
                root_cause = RootCause.UNKNOWN

            # Convert affected files
            llm_files = []
            for f in analysis.get("affected_files", []):
                llm_files.append(AffectedFile(
                    path=f.get("path", ""),
                    line_number=f.get("line_number"),
                    snippet=f.get("snippet"),
                    suggested_fix=f.get("suggested_fix")
                ))

            # Merge with regex-detected files if LLM missed them
            if not llm_files and affected_files:
                llm_files = affected_files

            return DiagnosisResult(
                error=error,
                root_cause=root_cause,
                confidence=DiagnosisConfidence(analysis.get("confidence", "medium")),
                category=category,
                affected_files=llm_files,
                explanation=analysis.get("explanation", "LLM diagnosis provided"),
                suggested_fixes=analysis.get("suggested_fixes", []),
                context=context or {},
            )

        except Exception as e:
            logger.error(f"LLM diagnosis failed: {e}")
            return None

    def _parse_llm_output(self, output: str) -> Optional[dict]:
        """Parse JSON from LLM output."""
        try:
            # cleaner look for JSON block
            match = re.search(r"```json\n(.*?)\n```", output, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # specific look for json block if the above failed
            match = re.search(r"({.*})", output, re.DOTALL)
            if match:
                return json.loads(match.group(1))
                
            return None
        except json.JSONDecodeError:
            return None
