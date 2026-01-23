"""Database of known error patterns and their fixes.

This module provides a database of known error patterns that can be
automatically fixed. It learns from successful fixes and applies
them to similar errors in the future.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .diagnosis import DiagnosisResult, RootCause
from .triage import ErrorCategory

logger = logging.getLogger(__name__)


@dataclass
class FixPattern:
    """A pattern for matching errors to known fixes.

    Attributes:
        pattern: Regex pattern to match error messages
        category: Error category this pattern matches
        root_cause: Root cause this pattern indicates
        example_error: Example error that matches this pattern
    """

    pattern: str
    category: ErrorCategory
    root_cause: RootCause
    example_error: Optional[str] = None

    def matches(self, text: str) -> bool:
        """Check if this pattern matches the given text."""
        return bool(re.search(self.pattern, text, re.IGNORECASE))


@dataclass
class KnownFix:
    """A known fix for a specific error pattern.

    Attributes:
        id: Unique identifier
        pattern: Pattern that triggers this fix
        fix_type: Type of fix (e.g., "install_package", "edit_file")
        fix_data: Data needed to apply the fix
        description: Human-readable description
        success_count: Number of successful applications
        failure_count: Number of failed applications
        last_used: When this fix was last used
        created_at: When this fix was created
    """

    id: str
    pattern: FixPattern
    fix_type: str
    fix_data: dict
    description: str
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern": {
                "pattern": self.pattern.pattern,
                "category": self.pattern.category.value,
                "root_cause": self.pattern.root_cause.value,
                "example_error": self.pattern.example_error,
            },
            "fix_type": self.fix_type,
            "fix_data": self.fix_data,
            "description": self.description,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_used": self.last_used,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnownFix":
        pattern_data = data.get("pattern", {})
        return cls(
            id=data["id"],
            pattern=FixPattern(
                pattern=pattern_data.get("pattern", ""),
                category=ErrorCategory(pattern_data.get("category", "unknown")),
                root_cause=RootCause(pattern_data.get("root_cause", "unknown")),
                example_error=pattern_data.get("example_error"),
            ),
            fix_type=data.get("fix_type", "unknown"),
            fix_data=data.get("fix_data", {}),
            description=data.get("description", ""),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            last_used=data.get("last_used"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# Built-in known fixes
BUILTIN_FIXES = [
    # Python import fixes
    KnownFix(
        id="python_missing_module",
        pattern=FixPattern(
            pattern=r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
            category=ErrorCategory.IMPORT_ERROR,
            root_cause=RootCause.MISSING_IMPORT,
            example_error="ModuleNotFoundError: No module named 'requests'",
        ),
        fix_type="install_package",
        fix_data={"command": "pip install {module}"},
        description="Install missing Python package",
    ),
    KnownFix(
        id="python_missing_import_statement",
        pattern=FixPattern(
            pattern=r"NameError: name ['\"]([^'\"]+)['\"] is not defined",
            category=ErrorCategory.NAME_ERROR,
            root_cause=RootCause.UNDEFINED_VARIABLE,
            example_error="NameError: name 'json' is not defined",
        ),
        fix_type="add_import",
        fix_data={"module": "{name}"},
        description="Add missing import statement",
    ),
    # JavaScript/Node fixes
    KnownFix(
        id="node_missing_module",
        pattern=FixPattern(
            pattern=r"Cannot find module ['\"]([^'\"]+)['\"]",
            category=ErrorCategory.IMPORT_ERROR,
            root_cause=RootCause.MISSING_IMPORT,
            example_error="Cannot find module 'express'",
        ),
        fix_type="install_package",
        fix_data={"command": "npm install {module}"},
        description="Install missing Node.js package",
    ),
    # Syntax fixes
    KnownFix(
        id="python_indentation",
        pattern=FixPattern(
            pattern=r"IndentationError: (unexpected indent|expected an indented block)",
            category=ErrorCategory.SYNTAX_ERROR,
            root_cause=RootCause.INDENTATION_ERROR,
            example_error="IndentationError: unexpected indent",
        ),
        fix_type="fix_indentation",
        fix_data={},
        description="Fix Python indentation",
    ),
    # Test fixes
    KnownFix(
        id="pytest_assertion_error",
        pattern=FixPattern(
            pattern=r"AssertionError: assert .* == .*",
            category=ErrorCategory.TEST_FAILURE,
            root_cause=RootCause.ASSERTION_MISMATCH,
            example_error="AssertionError: assert 1 == 2",
        ),
        fix_type="analyze_test_failure",
        fix_data={},
        description="Analyze test assertion failure",
    ),
    # Configuration fixes
    KnownFix(
        id="missing_env_var",
        pattern=FixPattern(
            pattern=r"KeyError: ['\"]([A-Z_]+)['\"]",
            category=ErrorCategory.CONFIG_ERROR,
            root_cause=RootCause.MISSING_ENV_VAR,
            example_error="KeyError: 'DATABASE_URL'",
        ),
        fix_type="add_env_var",
        fix_data={"default": ""},
        description="Add missing environment variable",
    ),
    # Timeout fixes
    KnownFix(
        id="operation_timeout",
        pattern=FixPattern(
            pattern=r"(TimeoutError|timed out after \d+ seconds)",
            category=ErrorCategory.TIMEOUT_ERROR,
            root_cause=RootCause.TIMEOUT,
            example_error="TimeoutError: Command timed out after 60 seconds",
        ),
        fix_type="increase_timeout",
        fix_data={"multiplier": 2},
        description="Increase operation timeout",
    ),
    # Security fixes
    KnownFix(
        id="sql_injection",
        pattern=FixPattern(
            pattern=r"(SQL injection|sql.*injection)",
            category=ErrorCategory.SECURITY_VULNERABILITY,
            root_cause=RootCause.VULNERABILITY,
            example_error="Potential SQL injection vulnerability detected",
        ),
        fix_type="use_parameterized_query",
        fix_data={},
        description="Convert to parameterized SQL query",
    ),
]


class KnownFixDatabase:
    """Database for storing and retrieving known fixes.

    Maintains a database of error patterns and their fixes,
    learning from successful and failed fix attempts.
    """

    # Minimum success rate to consider a fix reliable
    MIN_RELIABLE_SUCCESS_RATE = 0.6
    # Maximum fixes to keep in database
    MAX_FIXES = 500

    def __init__(self, workflow_dir: str | Path):
        """Initialize the known fix database.

        Args:
            workflow_dir: Directory for storing database
        """
        self.workflow_dir = Path(workflow_dir)
        self.db_file = self.workflow_dir / "fixer" / "known_fixes.json"
        self._fixes: dict[str, KnownFix] = {}
        self._load_database()

    def _ensure_dir(self) -> None:
        """Ensure fixer directory exists."""
        self.db_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_database(self) -> None:
        """Load database from disk."""
        # Start with built-in fixes
        for fix in BUILTIN_FIXES:
            self._fixes[fix.id] = fix

        # Load custom fixes
        if self.db_file.exists():
            try:
                with open(self.db_file) as f:
                    data = json.load(f)
                    for fix_data in data.get("fixes", []):
                        fix = KnownFix.from_dict(fix_data)
                        self._fixes[fix.id] = fix
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not load known fixes database: {e}")

    def _save_database(self) -> None:
        """Save database to disk."""
        self._ensure_dir()

        # Only save custom fixes (not built-ins)
        custom_fixes = [
            fix.to_dict()
            for fix in self._fixes.values()
            if fix.id not in {f.id for f in BUILTIN_FIXES}
        ]

        data = {
            "fixes": custom_fixes,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            with open(self.db_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not save known fixes database: {e}")

    def find_matching_fix(
        self,
        diagnosis: DiagnosisResult,
        min_success_rate: float = None,
    ) -> Optional[KnownFix]:
        """Find a known fix for the given diagnosis.

        Args:
            diagnosis: Diagnosis result
            min_success_rate: Minimum success rate (default 0.6)

        Returns:
            Matching fix or None
        """
        min_rate = min_success_rate or self.MIN_RELIABLE_SUCCESS_RATE
        error_text = f"{diagnosis.error.message}\n{diagnosis.error.stack_trace or ''}"

        best_fix = None
        best_score = 0.0

        for fix in self._fixes.values():
            # Check if pattern matches
            if not fix.pattern.matches(error_text):
                continue

            # Check category match
            if fix.pattern.category != diagnosis.category:
                continue

            # Check success rate
            if fix.success_rate < min_rate and (fix.success_count + fix.failure_count) > 2:
                continue

            # Calculate match score
            score = self._calculate_match_score(fix, diagnosis)
            if score > best_score:
                best_score = score
                best_fix = fix

        return best_fix

    def _calculate_match_score(
        self,
        fix: KnownFix,
        diagnosis: DiagnosisResult,
    ) -> float:
        """Calculate how well a fix matches the diagnosis.

        Args:
            fix: Known fix
            diagnosis: Diagnosis result

        Returns:
            Match score (0-1)
        """
        score = 0.0

        # Pattern match (base score)
        score += 0.5

        # Category match
        if fix.pattern.category == diagnosis.category:
            score += 0.2

        # Root cause match
        if fix.pattern.root_cause == diagnosis.root_cause:
            score += 0.2

        # Success rate bonus
        score += 0.1 * fix.success_rate

        return min(score, 1.0)

    def record_success(self, fix_id: str) -> None:
        """Record a successful fix application.

        Args:
            fix_id: ID of the fix that succeeded
        """
        if fix_id in self._fixes:
            self._fixes[fix_id].success_count += 1
            self._fixes[fix_id].last_used = datetime.now().isoformat()
            self._save_database()

    def record_failure(self, fix_id: str) -> None:
        """Record a failed fix application.

        Args:
            fix_id: ID of the fix that failed
        """
        if fix_id in self._fixes:
            self._fixes[fix_id].failure_count += 1
            self._fixes[fix_id].last_used = datetime.now().isoformat()
            self._save_database()

    def add_fix(
        self,
        pattern: str,
        category: ErrorCategory,
        root_cause: RootCause,
        fix_type: str,
        fix_data: dict,
        description: str,
        example_error: Optional[str] = None,
    ) -> KnownFix:
        """Add a new known fix to the database.

        Args:
            pattern: Regex pattern for matching errors
            category: Error category
            root_cause: Root cause
            fix_type: Type of fix
            fix_data: Data for applying fix
            description: Description of fix
            example_error: Example error message

        Returns:
            The created KnownFix
        """
        # Generate ID from pattern hash
        fix_id = f"custom_{hashlib.md5(pattern.encode()).hexdigest()[:8]}"

        fix = KnownFix(
            id=fix_id,
            pattern=FixPattern(
                pattern=pattern,
                category=category,
                root_cause=root_cause,
                example_error=example_error,
            ),
            fix_type=fix_type,
            fix_data=fix_data,
            description=description,
        )

        self._fixes[fix_id] = fix
        self._save_database()

        return fix

    def get_fix(self, fix_id: str) -> Optional[KnownFix]:
        """Get a fix by ID.

        Args:
            fix_id: Fix ID

        Returns:
            KnownFix or None
        """
        return self._fixes.get(fix_id)

    def get_all_fixes(self) -> list[KnownFix]:
        """Get all fixes in the database.

        Returns:
            List of all fixes
        """
        return list(self._fixes.values())

    def get_statistics(self) -> dict:
        """Get database statistics.

        Returns:
            Statistics dictionary
        """
        fixes = list(self._fixes.values())
        total_successes = sum(f.success_count for f in fixes)
        total_failures = sum(f.failure_count for f in fixes)

        return {
            "total_fixes": len(fixes),
            "builtin_fixes": len(BUILTIN_FIXES),
            "custom_fixes": len(fixes) - len(BUILTIN_FIXES),
            "total_applications": total_successes + total_failures,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "overall_success_rate": total_successes / (total_successes + total_failures)
            if (total_successes + total_failures) > 0
            else 0.0,
        }
