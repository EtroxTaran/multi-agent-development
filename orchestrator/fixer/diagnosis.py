"""Diagnosis engine for root cause analysis.

The diagnosis engine analyzes errors to determine their root cause,
considering context like file content, logs, and error history.
This enables more targeted and effective fixes.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from .triage import ErrorCategory, FixerError

logger = logging.getLogger(__name__)


class DiagnosisConfidence(str, Enum):
    """Confidence level in diagnosis."""

    HIGH = "high"  # > 80% confidence
    MEDIUM = "medium"  # 50-80% confidence
    LOW = "low"  # < 50% confidence


class RootCause(str, Enum):
    """Root causes for errors."""

    # Import/dependency issues
    MISSING_IMPORT = "missing_import"
    CIRCULAR_IMPORT = "circular_import"
    WRONG_IMPORT_PATH = "wrong_import_path"
    MISSING_DEPENDENCY = "missing_dependency"
    VERSION_MISMATCH = "version_mismatch"

    # Syntax issues
    SYNTAX_ERROR = "syntax_error"
    INDENTATION_ERROR = "indentation_error"
    UNCLOSED_BRACKET = "unclosed_bracket"
    MISSING_COLON = "missing_colon"

    # Type/name issues
    UNDEFINED_VARIABLE = "undefined_variable"
    WRONG_TYPE = "wrong_type"
    MISSING_ATTRIBUTE = "missing_attribute"
    TYPO = "typo"

    # Test issues
    ASSERTION_MISMATCH = "assertion_mismatch"
    MISSING_TEST_DATA = "missing_test_data"
    SETUP_FAILURE = "setup_failure"
    FLAKY_TEST = "flaky_test"

    # Configuration issues
    MISSING_CONFIG = "missing_config"
    INVALID_CONFIG = "invalid_config"
    MISSING_ENV_VAR = "missing_env_var"

    # Build issues
    BUILD_SCRIPT_ERROR = "build_script_error"
    COMPILATION_ERROR = "compilation_error"
    LINT_VIOLATION = "lint_violation"

    # Runtime issues
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    PERMISSION_DENIED = "permission_denied"

    # Security issues
    VULNERABILITY = "vulnerability"
    EXPOSED_SECRET = "exposed_secret"

    # Knowledge issues (triggers research)
    API_MISUSE = "api_misuse"
    MISSING_DOCUMENTATION = "missing_documentation"
    DEPRECATED_FEATURE = "deprecated_feature"

    # Unknown
    UNKNOWN = "unknown"


@dataclass
class AffectedFile:
    """A file affected by the error."""

    path: str
    line_number: Optional[int] = None
    column: Optional[int] = None
    snippet: Optional[str] = None
    suggested_fix: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "line_number": self.line_number,
            "column": self.column,
            "snippet": self.snippet,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class DiagnosisResult:
    """Result of error diagnosis.

    Attributes:
        error: The original error
        root_cause: Identified root cause
        confidence: Confidence in the diagnosis
        category: Error category from triage
        affected_files: Files affected by the error
        explanation: Human-readable explanation
        suggested_fixes: Ordered list of suggested fixes
        related_errors: IDs of errors that might have the same root cause
        context: Additional diagnostic context
        timestamp: When diagnosis was performed
    """

    error: FixerError
    root_cause: RootCause
    confidence: DiagnosisConfidence
    category: ErrorCategory
    affected_files: list[AffectedFile] = field(default_factory=list)
    explanation: str = ""
    suggested_fixes: list[str] = field(default_factory=list)
    related_errors: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "error": self.error.to_dict(),
            "root_cause": self.root_cause.value,
            "confidence": self.confidence.value,
            "category": self.category.value,
            "affected_files": [f.to_dict() for f in self.affected_files],
            "explanation": self.explanation,
            "suggested_fixes": self.suggested_fixes,
            "related_errors": self.related_errors,
            "context": self.context,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiagnosisResult":
        return cls(
            error=FixerError.from_dict(data["error"]),
            root_cause=RootCause(data["root_cause"]),
            confidence=DiagnosisConfidence(data["confidence"]),
            category=ErrorCategory(data["category"]),
            affected_files=[AffectedFile(**f) for f in data.get("affected_files", [])],
            explanation=data.get("explanation", ""),
            suggested_fixes=data.get("suggested_fixes", []),
            related_errors=data.get("related_errors", []),
            context=data.get("context", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


# Patterns for extracting file locations from error messages
FILE_LOCATION_PATTERNS = [
    # Python: File "path", line 123
    r'File ["\']([^"\']+)["\'], line (\d+)',
    # Python: path:line:col
    r"([^\s:]+\.py):(\d+):(\d+)",
    # JavaScript/TypeScript: at path:line:col
    r"at ([^\s:]+\.[jt]sx?):(\d+):(\d+)",
    # Generic: path:line
    r"([^\s:]+):(\d+)",
    # Go: path:line:col
    r"([^\s:]+\.go):(\d+):(\d+)",
    # Rust: --> path:line:col
    r"--> ([^\s:]+\.rs):(\d+):(\d+)",
]

# Patterns for identifying root causes
ROOT_CAUSE_PATTERNS = {
    RootCause.MISSING_IMPORT: [
        r"ImportError: No module named ['\"]([^'\"]+)['\"]",
        r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        r"Cannot find module ['\"]([^'\"]+)['\"]",
    ],
    RootCause.CIRCULAR_IMPORT: [
        r"circular import",
        r"ImportError: cannot import name .* from partially initialized module",
    ],
    RootCause.WRONG_IMPORT_PATH: [
        r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]",
        r"Module .* has no attribute",
    ],
    RootCause.MISSING_DEPENDENCY: [
        r"Package ['\"]([^'\"]+)['\"] not found",
        r"pip install ([^\s]+)",
        r"npm install ([^\s]+)",
    ],
    RootCause.SYNTAX_ERROR: [
        r"SyntaxError: (.*)",
        r"invalid syntax",
    ],
    RootCause.INDENTATION_ERROR: [
        r"IndentationError: (.*)",
        r"unexpected indent",
        r"expected an indented block",
    ],
    RootCause.UNCLOSED_BRACKET: [
        r"unexpected EOF",
        r"unclosed [\(\[\{]",
        r"Unexpected end of input",
    ],
    RootCause.UNDEFINED_VARIABLE: [
        r"NameError: name ['\"]([^'\"]+)['\"] is not defined",
        r"ReferenceError: ([^\s]+) is not defined",
        r"undefined variable ['\"]([^'\"]+)['\"]",
    ],
    RootCause.WRONG_TYPE: [
        r"TypeError: (.*)",
        r"expected .*, got .*",
        r"Argument of type .* is not assignable",
    ],
    RootCause.MISSING_ATTRIBUTE: [
        r"AttributeError: ['\"]([^'\"]+)['\"] object has no attribute ['\"]([^'\"]+)['\"]",
        r"has no property ['\"]([^'\"]+)['\"]",
    ],
    RootCause.TYPO: [
        r"Did you mean ['\"]([^'\"]+)['\"]",
        r"perhaps you meant ['\"]([^'\"]+)['\"]",
    ],
    RootCause.ASSERTION_MISMATCH: [
        r"AssertionError: (.*)",
        r"expected .* to (equal|be|match)",
        r"assert .* == .*",
    ],
    RootCause.MISSING_ENV_VAR: [
        r"KeyError: ['\"]([A-Z_]+)['\"]",
        r"Environment variable ['\"]([^'\"]+)['\"] not set",
    ],
    RootCause.TIMEOUT: [
        r"TimeoutError",
        r"timed out after \d+ seconds",
        r"operation timed out",
    ],
    RootCause.PERMISSION_DENIED: [
        r"PermissionError",
        r"EACCES",
        r"permission denied",
    ],
    RootCause.VULNERABILITY: [
        r"CVE-\d+-\d+",
        r"security vulnerability",
        r"vulnerable to",
    ],
    RootCause.EXPOSED_SECRET: [
        r"(api[_-]?key|secret|password|token).*exposed",
        r"credential.*found",
    ],
}


class DiagnosisEngine:
    """Engine for diagnosing error root causes.

    Analyzes error messages, stack traces, and context to determine
    the most likely root cause of an error.
    """

    def __init__(self, project_dir: str | Path):
        """Initialize the diagnosis engine.

        Args:
            project_dir: Project directory for reading files
        """
        self.project_dir = Path(project_dir)

        # Initialize LLM diagnoser for complex errors
        from .llm_diagnoser import LLMDiagnosisEngine

        self.llm_engine = LLMDiagnosisEngine(self.project_dir)

    async def diagnose(
        self,
        error: FixerError,
        category: ErrorCategory,
        workflow_state: Optional[dict] = None,
    ) -> DiagnosisResult:
        """Diagnose an error to determine its root cause.

        Args:
            error: The error to diagnose
            category: Error category from triage
            workflow_state: Optional workflow state for additional context

        Returns:
            DiagnosisResult with root cause and suggested fixes
        """
        # Extract text to analyze
        message = error.message
        stack_trace = error.stack_trace or ""
        combined_text = f"{message}\n{stack_trace}"

        # Determine root cause via regex (fast path)
        root_cause, confidence = self._identify_root_cause(combined_text, category)

        # Extract affected files
        affected_files = self._extract_affected_files(combined_text)

        # Build context
        context = self._build_context(error, workflow_state)

        # If regex confidence is low or unknown, try LLM (slow path)
        if confidence == DiagnosisConfidence.LOW or root_cause == RootCause.UNKNOWN:
            logger.info("Regex diagnosis low confidence/unknown. Attempting LLM diagnosis...")
            llm_result = await self.llm_engine.diagnose(
                error=error, category=category, affected_files=affected_files, context=context
            )
            if llm_result:
                logger.info(f"LLM diagnosis successful: {llm_result.root_cause}")
                return llm_result
            logger.warning("LLM diagnosis failed, falling back to regex result")

        # Generate explanation
        explanation = self._generate_explanation(root_cause, error, affected_files)

        # Generate suggested fixes
        suggested_fixes = self._generate_suggested_fixes(root_cause, affected_files, error)

        return DiagnosisResult(
            error=error,
            root_cause=root_cause,
            confidence=confidence,
            category=category,
            affected_files=affected_files,
            explanation=explanation,
            suggested_fixes=suggested_fixes,
            context=context,
        )

    def _identify_root_cause(
        self,
        text: str,
        category: ErrorCategory,
    ) -> tuple[RootCause, DiagnosisConfidence]:
        """Identify the root cause from error text.

        Args:
            text: Combined error message and stack trace
            category: Error category

        Returns:
            Tuple of (root_cause, confidence)
        """
        text_lower = text.lower()

        # Check patterns for each root cause
        for root_cause, patterns in ROOT_CAUSE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    # Higher confidence for more specific patterns
                    confidence = (
                        DiagnosisConfidence.HIGH
                        if len(pattern) > 30
                        else DiagnosisConfidence.MEDIUM
                    )
                    return root_cause, confidence

        # Fall back to category-based mapping
        category_to_cause = {
            ErrorCategory.IMPORT_ERROR: RootCause.MISSING_IMPORT,
            ErrorCategory.SYNTAX_ERROR: RootCause.SYNTAX_ERROR,
            ErrorCategory.TYPE_ERROR: RootCause.WRONG_TYPE,
            ErrorCategory.NAME_ERROR: RootCause.UNDEFINED_VARIABLE,
            ErrorCategory.ATTRIBUTE_ERROR: RootCause.MISSING_ATTRIBUTE,
            ErrorCategory.TEST_FAILURE: RootCause.ASSERTION_MISMATCH,
            ErrorCategory.DEPENDENCY_ERROR: RootCause.MISSING_DEPENDENCY,
            ErrorCategory.CONFIG_ERROR: RootCause.MISSING_CONFIG,
            ErrorCategory.TIMEOUT_ERROR: RootCause.TIMEOUT,
            ErrorCategory.PERMISSION_ERROR: RootCause.PERMISSION_DENIED,
            ErrorCategory.SECURITY_VULNERABILITY: RootCause.VULNERABILITY,
            ErrorCategory.SECRET_EXPOSURE: RootCause.EXPOSED_SECRET,
        }

        if category in category_to_cause:
            return category_to_cause[category], DiagnosisConfidence.LOW

        return RootCause.UNKNOWN, DiagnosisConfidence.LOW

    def _extract_affected_files(self, text: str) -> list[AffectedFile]:
        """Extract file locations from error text.

        Args:
            text: Combined error message and stack trace

        Returns:
            List of affected files
        """
        affected = []
        seen_paths = set()

        for pattern in FILE_LOCATION_PATTERNS:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                path = groups[0]

                # Skip if we've seen this path
                if path in seen_paths:
                    continue
                seen_paths.add(path)

                # Skip system/library paths
                if any(
                    x in path
                    for x in [
                        "site-packages",
                        "node_modules",
                        "/usr/",
                        "python3.",
                        "venv/",
                        ".venv/",
                    ]
                ):
                    continue

                line_num = int(groups[1]) if len(groups) > 1 else None
                column = int(groups[2]) if len(groups) > 2 else None

                # Try to read snippet from file
                snippet = self._read_snippet(path, line_num) if line_num else None

                affected.append(
                    AffectedFile(
                        path=path,
                        line_number=line_num,
                        column=column,
                        snippet=snippet,
                    )
                )

        return affected

    def _read_snippet(
        self,
        path: str,
        line_number: int,
        context_lines: int = 3,
    ) -> Optional[str]:
        """Read a code snippet from a file.

        Args:
            path: File path
            line_number: Center line number
            context_lines: Lines of context before and after

        Returns:
            Code snippet or None
        """
        try:
            file_path = self.project_dir / path
            if not file_path.exists():
                # Try without project_dir prefix
                file_path = Path(path)
                if not file_path.exists():
                    return None

            lines = file_path.read_text().splitlines()
            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)

            snippet_lines = []
            for i in range(start, end):
                marker = ">>> " if i == line_number - 1 else "    "
                snippet_lines.append(f"{marker}{i + 1}: {lines[i]}")

            return "\n".join(snippet_lines)

        except (OSError, UnicodeDecodeError):
            return None

    def _generate_explanation(
        self,
        root_cause: RootCause,
        error: FixerError,
        affected_files: list[AffectedFile],
    ) -> str:
        """Generate a human-readable explanation.

        Args:
            root_cause: Identified root cause
            error: Original error
            affected_files: Affected files

        Returns:
            Explanation string
        """
        explanations = {
            RootCause.MISSING_IMPORT: "A required module is not installed or cannot be found.",
            RootCause.CIRCULAR_IMPORT: "Two or more modules are importing each other, creating a dependency cycle.",
            RootCause.WRONG_IMPORT_PATH: "The import path is incorrect or the name doesn't exist in the module.",
            RootCause.MISSING_DEPENDENCY: "A required package is not installed in the environment.",
            RootCause.VERSION_MISMATCH: "Package versions are incompatible with each other.",
            RootCause.SYNTAX_ERROR: "The code contains a syntax error that prevents parsing.",
            RootCause.INDENTATION_ERROR: "Incorrect indentation in the code (Python requires consistent indentation).",
            RootCause.UNCLOSED_BRACKET: "A bracket, parenthesis, or brace is not properly closed.",
            RootCause.MISSING_COLON: "A required colon is missing after a statement.",
            RootCause.UNDEFINED_VARIABLE: "A variable is used before it is defined or is misspelled.",
            RootCause.WRONG_TYPE: "A value of the wrong type is being used in an operation.",
            RootCause.MISSING_ATTRIBUTE: "The object doesn't have the attribute being accessed.",
            RootCause.TYPO: "A name appears to be misspelled.",
            RootCause.ASSERTION_MISMATCH: "A test assertion failed because the actual value doesn't match expected.",
            RootCause.MISSING_TEST_DATA: "Test data or fixtures are missing.",
            RootCause.SETUP_FAILURE: "Test setup or initialization failed.",
            RootCause.FLAKY_TEST: "The test is non-deterministic and occasionally fails.",
            RootCause.MISSING_CONFIG: "A required configuration file is missing.",
            RootCause.INVALID_CONFIG: "The configuration file contains invalid values.",
            RootCause.MISSING_ENV_VAR: "A required environment variable is not set.",
            RootCause.BUILD_SCRIPT_ERROR: "The build script contains an error.",
            RootCause.COMPILATION_ERROR: "The code failed to compile.",
            RootCause.LINT_VIOLATION: "The code violates linting rules.",
            RootCause.TIMEOUT: "An operation took too long and was terminated.",
            RootCause.RESOURCE_EXHAUSTION: "System resources (memory, disk) are exhausted.",
            RootCause.PERMISSION_DENIED: "Insufficient permissions to perform the operation.",
            RootCause.VULNERABILITY: "A security vulnerability has been detected.",
            RootCause.EXPOSED_SECRET: "A secret or credential has been exposed in the code.",
            RootCause.UNKNOWN: "The root cause could not be determined.",
        }

        base = explanations.get(root_cause, "An error occurred.")

        # Add file context
        if affected_files:
            file_info = affected_files[0]
            if file_info.line_number:
                base += (
                    f" The error appears to be in {file_info.path} at line {file_info.line_number}."
                )
            else:
                base += f" The error appears to be related to {file_info.path}."

        return base

    def _generate_suggested_fixes(
        self,
        root_cause: RootCause,
        affected_files: list[AffectedFile],
        error: FixerError,
    ) -> list[str]:
        """Generate suggested fixes for the root cause.

        Args:
            root_cause: Identified root cause
            affected_files: Affected files
            error: Original error

        Returns:
            List of suggested fixes
        """
        fixes = {
            RootCause.MISSING_IMPORT: [
                "Install the missing package",
                "Add the import statement to the file",
                "Check if the module name is spelled correctly",
            ],
            RootCause.CIRCULAR_IMPORT: [
                "Move shared code to a separate module",
                "Use lazy imports inside functions",
                "Restructure module dependencies",
            ],
            RootCause.WRONG_IMPORT_PATH: [
                "Fix the import path to the correct location",
                "Check if the name exists in the source module",
                "Use absolute imports instead of relative",
            ],
            RootCause.MISSING_DEPENDENCY: [
                "Install the missing package with pip or npm",
                "Add the package to requirements.txt or package.json",
                "Check if the package name is correct",
            ],
            RootCause.SYNTAX_ERROR: [
                "Fix the syntax error at the indicated line",
                "Check for missing or extra characters",
                "Ensure proper indentation and brackets",
            ],
            RootCause.INDENTATION_ERROR: [
                "Fix the indentation at the indicated line",
                "Use consistent tabs or spaces (not mixed)",
                "Check for proper nesting level",
            ],
            RootCause.UNDEFINED_VARIABLE: [
                "Define the variable before using it",
                "Check for typos in the variable name",
                "Import the variable if it's from another module",
            ],
            RootCause.WRONG_TYPE: [
                "Convert the value to the expected type",
                "Add type checking before the operation",
                "Fix the function call to pass correct types",
            ],
            RootCause.MISSING_ATTRIBUTE: [
                "Add the missing attribute to the class",
                "Check if the attribute name is spelled correctly",
                "Verify the object type before accessing",
            ],
            RootCause.ASSERTION_MISMATCH: [
                "Update the implementation to produce expected output",
                "Update the test if the expected value is wrong",
                "Check for edge cases in the test data",
            ],
            RootCause.MISSING_ENV_VAR: [
                "Set the required environment variable",
                "Add the variable to .env file",
                "Provide a default value in the code",
            ],
            RootCause.TIMEOUT: [
                "Increase the timeout value",
                "Optimize the operation to be faster",
                "Add progress tracking and early termination",
            ],
            RootCause.VULNERABILITY: [
                "Upgrade the affected package to a patched version",
                "Apply the recommended security fix",
                "Implement input validation or sanitization",
            ],
            RootCause.EXPOSED_SECRET: [
                "Remove the exposed secret from the code",
                "Rotate the compromised credential",
                "Use environment variables for secrets",
            ],
        }

        return fixes.get(root_cause, ["Manual investigation required"])

    def _build_context(
        self,
        error: FixerError,
        workflow_state: Optional[dict],
    ) -> dict:
        """Build additional context for the diagnosis.

        Args:
            error: Original error
            workflow_state: Workflow state if available

        Returns:
            Context dictionary
        """
        context = {}

        # Add error context
        if error.context:
            context["error_context"] = error.context

        # Add workflow context
        if workflow_state:
            context["current_phase"] = workflow_state.get("current_phase")
            context["current_task_id"] = workflow_state.get("current_task_id")
            context["iteration_count"] = workflow_state.get("iteration_count")

        return context
