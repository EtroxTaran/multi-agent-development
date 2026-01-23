"""Error context preservation for intelligent retries.

When tasks fail, preserves rich context about:
- What was attempted
- What went wrong
- What files were involved
- Previous attempts and their outcomes

This context is used to enhance retry prompts, allowing
the agent to learn from previous failures.

Usage:
    manager = ErrorContextManager(project_dir)

    # Record an error
    context = manager.record_error(
        task_id="T1",
        error_type="test_failure",
        error_message="AssertionError: expected 5, got 3",
        stdout="...",
        stderr="...",
        files_involved=["src/calc.py", "tests/test_calc.py"],
    )

    # Build enhanced retry prompt
    retry_prompt = manager.build_retry_prompt(
        task_id="T1",
        original_prompt="Implement calculator...",
    )

    # Get error history
    history = manager.get_error_history("T1")
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Storage location
DEFAULT_ERROR_DIR = ".workflow/error_contexts"

# Maximum errors to retain per task
MAX_ERRORS_PER_TASK = 5

# Maximum context size to include in retry prompts
MAX_RETRY_CONTEXT_CHARS = 2000


@dataclass
class ErrorContext:
    """Context about a task failure.

    Captures all relevant information for debugging and
    intelligent retry prompt generation.

    Attributes:
        id: Unique error identifier
        task_id: Task that failed
        timestamp: When the error occurred
        attempt: Which attempt this was
        error_type: Classification of error
        error_message: Primary error message
        stdout_excerpt: Relevant portion of stdout
        stderr_excerpt: Relevant portion of stderr
        files_involved: Files related to the error
        stack_trace: Stack trace if available
        suggestions: Suggested fixes
        metadata: Additional context
    """

    id: str
    task_id: str
    timestamp: str
    attempt: int
    error_type: str
    error_message: str
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    files_involved: list[str] = field(default_factory=list)
    stack_trace: Optional[str] = None
    suggestions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ErrorContext":
        """Deserialize from storage."""
        return cls(**data)

    def to_prompt_context(self, max_chars: int = MAX_RETRY_CONTEXT_CHARS) -> str:
        """Format error context for inclusion in retry prompt.

        Args:
            max_chars: Maximum characters to include

        Returns:
            Formatted context string
        """
        lines = [
            f"### Previous Attempt {self.attempt} Failed",
            f"Error Type: {self.error_type}",
            f"Error: {self.error_message}",
        ]

        if self.files_involved:
            lines.append(f"Files Involved: {', '.join(self.files_involved[:5])}")

        if self.stack_trace:
            # Include truncated stack trace
            trace = self.stack_trace[:500]
            if len(self.stack_trace) > 500:
                trace += "\n... (truncated)"
            lines.append(f"Stack Trace:\n```\n{trace}\n```")

        if self.stderr_excerpt:
            excerpt = self.stderr_excerpt[:300]
            if len(self.stderr_excerpt) > 300:
                excerpt += "..."
            lines.append(f"Error Output:\n```\n{excerpt}\n```")

        if self.suggestions:
            lines.append("Suggestions:")
            for s in self.suggestions[:3]:
                lines.append(f"- {s}")

        result = "\n".join(lines)

        # Truncate if too long
        if len(result) > max_chars:
            result = result[: max_chars - 3] + "..."

        return result


# Error type classifications
class ErrorType:
    """Standard error type classifications."""

    TEST_FAILURE = "test_failure"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    BUILD_FAILURE = "build_failure"
    LINT_ERROR = "lint_error"
    SECURITY_ISSUE = "security_issue"
    CLARIFICATION_NEEDED = "clarification_needed"
    UNKNOWN = "unknown"


def classify_error(
    error_message: str,
    stderr: str = "",
    exit_code: int = 0,
) -> str:
    """Classify an error based on message and output.

    Args:
        error_message: Primary error message
        stderr: Standard error output
        exit_code: Process exit code

    Returns:
        Error type classification
    """
    combined = f"{error_message} {stderr}".lower()

    if "timeout" in combined or exit_code == -1:
        return ErrorType.TIMEOUT

    if "syntaxerror" in combined or "syntax error" in combined:
        return ErrorType.SYNTAX_ERROR

    if "importerror" in combined or "modulenotfounderror" in combined:
        return ErrorType.IMPORT_ERROR

    if "typeerror" in combined or "type error" in combined:
        return ErrorType.TYPE_ERROR

    if "assertionerror" in combined or "test failed" in combined or "failed" in combined:
        if "test" in combined or "pytest" in combined or "jest" in combined:
            return ErrorType.TEST_FAILURE

    if "build failed" in combined or "compilation error" in combined:
        return ErrorType.BUILD_FAILURE

    if "lint" in combined or "eslint" in combined or "flake8" in combined:
        return ErrorType.LINT_ERROR

    if "security" in combined or "vulnerability" in combined:
        return ErrorType.SECURITY_ISSUE

    if "clarification" in combined or "unclear" in combined or "ambiguous" in combined:
        return ErrorType.CLARIFICATION_NEEDED

    if exit_code != 0:
        return ErrorType.RUNTIME_ERROR

    return ErrorType.UNKNOWN


def extract_suggestions(
    error_type: str,
    error_message: str,
    stderr: str = "",
) -> list[str]:
    """Generate suggestions based on error type.

    Args:
        error_type: Classified error type
        error_message: Error message
        stderr: Standard error output

    Returns:
        List of suggestions
    """
    suggestions = []

    if error_type == ErrorType.TEST_FAILURE:
        suggestions = [
            "Review the failing test assertions carefully",
            "Check if the implementation matches the expected behavior",
            "Run the specific failing test in isolation to understand the issue",
        ]
    elif error_type == ErrorType.SYNTAX_ERROR:
        suggestions = [
            "Check for missing brackets, parentheses, or quotes",
            "Verify proper indentation (especially in Python)",
            "Look for typos in keywords or variable names",
        ]
    elif error_type == ErrorType.IMPORT_ERROR:
        suggestions = [
            "Verify the module/package is installed",
            "Check the import path is correct",
            "Ensure __init__.py exists in package directories",
        ]
    elif error_type == ErrorType.TYPE_ERROR:
        suggestions = [
            "Check the types of arguments being passed",
            "Verify return types match expectations",
            "Look for None values being passed where objects expected",
        ]
    elif error_type == ErrorType.TIMEOUT:
        suggestions = [
            "Check for infinite loops or recursion",
            "Look for blocking operations",
            "Consider breaking the task into smaller pieces",
        ]
    elif error_type == ErrorType.BUILD_FAILURE:
        suggestions = [
            "Check for missing dependencies",
            "Verify build configuration is correct",
            "Look for incompatible version requirements",
        ]
    elif error_type == ErrorType.LINT_ERROR:
        suggestions = [
            "Fix formatting issues flagged by the linter",
            "Address any code style violations",
            "Check for unused imports or variables",
        ]

    return suggestions


def extract_files_from_error(
    error_message: str,
    stderr: str = "",
    project_dir: Optional[Path] = None,
) -> list[str]:
    """Extract file paths mentioned in error output.

    Args:
        error_message: Error message
        stderr: Standard error output
        project_dir: Project directory for relative paths

    Returns:
        List of file paths mentioned
    """
    import re

    combined = f"{error_message}\n{stderr}"
    files = set()

    # Common patterns for file paths in error messages
    patterns = [
        r'File "([^"]+\.py)"',  # Python tracebacks
        r"at ([^\s]+\.(js|ts|jsx|tsx)):\d+",  # JavaScript/TypeScript
        r"([a-zA-Z0-9_/.-]+\.(py|js|ts|jsx|tsx|go|rs|java)):\d+",  # Generic
        r"in ([^\s]+\.(py|js|ts|jsx|tsx))",  # "in file.py"
    ]

    for pattern in patterns:
        matches = re.findall(pattern, combined)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            # Clean up the path
            path = match.strip()
            if path and not path.startswith("<"):
                files.add(path)

    return list(files)


class ErrorContextManager:
    """Manages error contexts for tasks.

    Stores and retrieves error contexts, builds enhanced retry prompts.

    Thread-safe for concurrent access.
    """

    def __init__(
        self,
        project_dir: Path | str,
        error_dir: Optional[str] = None,
        max_errors_per_task: int = MAX_ERRORS_PER_TASK,
    ):
        """Initialize error context manager.

        Args:
            project_dir: Project directory
            error_dir: Directory for error storage (relative to project)
            max_errors_per_task: Maximum errors to retain per task
        """
        self.project_dir = Path(project_dir)
        self.error_dir = self.project_dir / (error_dir or DEFAULT_ERROR_DIR)
        self.max_errors_per_task = max_errors_per_task
        self._error_counter = 0

    def _get_task_file(self, task_id: str) -> Path:
        """Get the error file path for a task."""
        return self.error_dir / f"{task_id}_errors.json"

    def _generate_error_id(self, task_id: str) -> str:
        """Generate unique error ID."""
        self._error_counter += 1
        return f"err-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._error_counter}"

    def record_error(
        self,
        task_id: str,
        error_message: str,
        attempt: int = 1,
        error_type: Optional[str] = None,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        files_involved: Optional[list[str]] = None,
        stack_trace: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ErrorContext:
        """Record an error for a task.

        Args:
            task_id: Task identifier
            error_message: Primary error message
            attempt: Which attempt this was
            error_type: Error classification (auto-classified if None)
            stdout: Standard output
            stderr: Standard error
            exit_code: Process exit code
            files_involved: Files related to the error
            stack_trace: Stack trace if available
            metadata: Additional context

        Returns:
            Created ErrorContext
        """
        # Auto-classify if not provided
        if error_type is None:
            error_type = classify_error(error_message, stderr, exit_code)

        # Extract files if not provided
        if files_involved is None:
            files_involved = extract_files_from_error(error_message, stderr, self.project_dir)

        # Generate suggestions
        suggestions = extract_suggestions(error_type, error_message, stderr)

        # Truncate outputs for storage
        stdout_excerpt = stdout[-1000:] if len(stdout) > 1000 else stdout
        stderr_excerpt = stderr[-1000:] if len(stderr) > 1000 else stderr

        context = ErrorContext(
            id=self._generate_error_id(task_id),
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
            attempt=attempt,
            error_type=error_type,
            error_message=error_message[:500],  # Truncate long messages
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
            files_involved=files_involved,
            stack_trace=stack_trace[:2000] if stack_trace else None,
            suggestions=suggestions,
            metadata=metadata or {},
        )

        # Save to storage
        self._save_error(context)

        logger.info(f"Recorded error for task {task_id}: {error_type}")
        return context

    def _save_error(self, context: ErrorContext) -> None:
        """Save error context to storage."""
        self.error_dir.mkdir(parents=True, exist_ok=True)
        task_file = self._get_task_file(context.task_id)

        # Load existing errors
        errors = self._load_task_errors(context.task_id)

        # Add new error
        errors.append(context.to_dict())

        # Trim to max errors (keep most recent)
        if len(errors) > self.max_errors_per_task:
            errors = errors[-self.max_errors_per_task :]

        # Save
        task_file.write_text(json.dumps(errors, indent=2))

    def _load_task_errors(self, task_id: str) -> list[dict]:
        """Load errors for a task."""
        task_file = self._get_task_file(task_id)
        if not task_file.exists():
            return []

        try:
            return json.loads(task_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load errors for {task_id}: {e}")
            return []

    def get_error_history(self, task_id: str) -> list[ErrorContext]:
        """Get error history for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of ErrorContext objects, chronologically ordered
        """
        errors = self._load_task_errors(task_id)
        return [ErrorContext.from_dict(e) for e in errors]

    def get_latest_error(self, task_id: str) -> Optional[ErrorContext]:
        """Get the most recent error for a task.

        Args:
            task_id: Task identifier

        Returns:
            Most recent ErrorContext or None
        """
        errors = self.get_error_history(task_id)
        return errors[-1] if errors else None

    def build_retry_prompt(
        self,
        task_id: str,
        original_prompt: str,
        max_context_chars: int = MAX_RETRY_CONTEXT_CHARS,
    ) -> str:
        """Build an enhanced retry prompt with error context.

        Includes information about previous failures to help
        the agent avoid repeating the same mistakes.

        Args:
            task_id: Task identifier
            original_prompt: The original task prompt
            max_context_chars: Maximum chars for error context

        Returns:
            Enhanced prompt with error context
        """
        errors = self.get_error_history(task_id)
        if not errors:
            return original_prompt

        # Build context from recent errors
        context_parts = []
        remaining_chars = max_context_chars

        for error in reversed(errors):  # Most recent first
            error_context = error.to_prompt_context(remaining_chars)
            if len(error_context) > remaining_chars:
                break
            context_parts.insert(0, error_context)
            remaining_chars -= len(error_context) + 10  # Account for separators

            if remaining_chars < 200:  # Minimum useful context
                break

        if not context_parts:
            return original_prompt

        error_section = "\n\n---\n\n".join(context_parts)

        # Build enhanced prompt
        enhanced = f"""## IMPORTANT: Previous Attempts Failed

{error_section}

---

## Your Task (Retry Attempt {len(errors) + 1})

{original_prompt}

---

## Retry Instructions

1. Carefully review the previous error(s) above
2. Do NOT repeat the same approach that failed
3. Address the specific issues mentioned
4. If the same test is failing, analyze why and fix the root cause
5. If stuck, consider a different implementation approach
"""

        return enhanced

    def clear_task_errors(self, task_id: str) -> bool:
        """Clear error history for a task.

        Call this when a task completes successfully.

        Args:
            task_id: Task identifier

        Returns:
            True if errors were cleared
        """
        task_file = self._get_task_file(task_id)
        if task_file.exists():
            task_file.unlink()
            logger.debug(f"Cleared error history for task {task_id}")
            return True
        return False

    def get_error_summary(self, task_id: str) -> dict[str, Any]:
        """Get a summary of errors for a task.

        Args:
            task_id: Task identifier

        Returns:
            Summary dictionary
        """
        errors = self.get_error_history(task_id)
        if not errors:
            return {
                "task_id": task_id,
                "total_errors": 0,
                "error_types": {},
                "files_involved": [],
            }

        error_types: dict[str, int] = {}
        all_files: set[str] = set()

        for error in errors:
            error_types[error.error_type] = error_types.get(error.error_type, 0) + 1
            all_files.update(error.files_involved)

        return {
            "task_id": task_id,
            "total_errors": len(errors),
            "error_types": error_types,
            "files_involved": list(all_files),
            "latest_error": errors[-1].error_type if errors else None,
            "latest_message": errors[-1].error_message if errors else None,
        }
