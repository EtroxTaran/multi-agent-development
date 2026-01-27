"""Security validators for preventing injection attacks.

This module provides validation functions for:
- SQL table/field names (allowlist-based)
- Package names for pip/npm (regex + blocklist)
- File paths (traversal and shell character prevention)
- Coverage commands (allowlist-based)
- Prompt content (injection pattern detection)
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityValidationError(Exception):
    """Raised when security validation fails."""

    pass


# ============================================
# SQL Identifier Allowlists
# ============================================

# All tables defined in orchestrator/db/schema.py
ALLOWED_TABLES: frozenset[str] = frozenset(
    [
        # Core workflow tables
        "schema_version",
        "workflow_state",
        "tasks",
        "milestones",
        # Audit and tracking
        "audit_entries",
        "error_patterns",
        "checkpoints",
        "git_commits",
        "sessions",
        "budget_records",
        "workflow_events",
        # Phase outputs and logs
        "phase_outputs",
        "logs",
        # Auto-improvement system
        "agent_evaluations",
        "prompt_versions",
        "golden_examples",
        "optimization_history",
        # LangGraph persistence
        "graph_checkpoints",
        "graph_writes",
    ]
)

# All fields across all tables in the schema
ALLOWED_FIELDS: frozenset[str] = frozenset(
    [
        # Common fields
        "id",
        "created_at",
        "updated_at",
        # schema_version
        "version",
        "applied_at",
        # workflow_state
        "project_dir",
        "current_phase",
        "phase_status",
        "iteration_count",
        "plan",
        "validation_feedback",
        "verification_feedback",
        "implementation_result",
        "next_decision",
        "execution_mode",
        "discussion_complete",
        "research_complete",
        "research_findings",
        "token_usage",
        # tasks
        "task_id",
        "title",
        "user_story",
        "acceptance_criteria",
        "dependencies",
        "status",
        "priority",
        "milestone_id",
        "estimated_complexity",
        "files_to_create",
        "files_to_modify",
        "test_files",
        "attempts",
        "max_attempts",
        "linear_issue_id",
        "implementation_notes",
        "error",
        # milestones
        "name",
        "description",
        "task_ids",
        # audit_entries
        "entry_id",
        "agent",
        "session_id",
        "prompt_hash",
        "prompt_length",
        "command_args",
        "exit_code",
        "duration_seconds",
        "output_length",
        "error_length",
        "parsed_output_type",
        "cost_usd",
        "model",
        "metadata",
        "timestamp",
        # error_patterns
        "error_type",
        "error_message",
        "error_context",
        "solution",
        "embedding",
        # checkpoints
        "checkpoint_id",
        "notes",
        "phase",
        "task_progress",
        "state_snapshot",
        "files_snapshot",
        # git_commits
        "commit_hash",
        "message",
        "files_changed",
        # sessions
        "invocation_count",
        "total_cost_usd",
        "closed_at",
        # budget_records
        "tokens_input",
        "tokens_output",
        # workflow_events
        "event_type",
        "event_data",
        # phase_outputs
        "output_type",
        "content",
        # logs
        "log_type",
        # agent_evaluations
        "evaluation_id",
        "node",
        "scores",
        "overall_score",
        "feedback",
        "suggestions",
        "prompt_version",
        "evaluator_model",
        # prompt_versions
        "version_id",
        "template_name",
        "metrics",
        "parent_version",
        "optimization_method",
        # golden_examples
        "example_id",
        "input_prompt",
        "output",
        "score",
        # optimization_history
        "optimization_id",
        "method",
        "source_version",
        "target_version",
        "success",
        "source_score",
        "target_score",
        "improvement",
        "samples_used",
        "validation_results",
        # graph_checkpoints
        "thread_id",
        "checkpoint_ns",
        "parent_checkpoint_id",
        "checkpoint",
        # graph_writes
        "idx",
        "channel",
        "type",
        "value",
    ]
)

# ============================================
# SQL Validation
# ============================================


def validate_sql_table(table: str) -> str:
    """Validate a SQL table name against the allowlist.

    Args:
        table: Table name to validate

    Returns:
        The validated table name (unchanged if valid)

    Raises:
        SecurityValidationError: If table name is not in allowlist
    """
    if not table or not isinstance(table, str):
        raise SecurityValidationError("Table name must be a non-empty string")

    # Normalize and check
    table_clean = table.strip().lower()

    if table_clean not in ALLOWED_TABLES:
        raise SecurityValidationError(
            f"Table '{table}' is not in the allowed tables list. "
            f"Allowed tables: {sorted(ALLOWED_TABLES)}"
        )

    return table_clean


def validate_sql_field(field: str) -> str:
    """Validate a SQL field name against the allowlist.

    Args:
        field: Field name to validate

    Returns:
        The validated field name (unchanged if valid)

    Raises:
        SecurityValidationError: If field name is not in allowlist
    """
    if not field or not isinstance(field, str):
        raise SecurityValidationError("Field name must be a non-empty string")

    # Normalize and check
    field_clean = field.strip().lower()

    if field_clean not in ALLOWED_FIELDS:
        raise SecurityValidationError(f"Field '{field}' is not in the allowed fields list")

    return field_clean


# ============================================
# Command Injection Prevention
# ============================================

# Package name validation (supports scoped npm packages like @types/node)
_PACKAGE_NAME_PATTERN = re.compile(
    r"^(@[a-zA-Z0-9][-a-zA-Z0-9._]*/)?[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$"
)

# Characters that could be used for shell injection (excluding <> which are used in version specifiers)
_SHELL_DANGEROUS_CHARS = frozenset([";", "&", "|", "`", "$", "(", ")", "{", "}", "\n", "\r", "\\"])

# Blocked package names (common attack patterns)
_BLOCKED_PACKAGES = frozenset(
    [
        "rm",
        "sudo",
        "wget",
        "curl",
        "bash",
        "sh",
        "zsh",
        "eval",
        "exec",
    ]
)


def validate_package_name(package: str) -> str:
    """Validate a package name for pip/npm installation.

    Args:
        package: Package name to validate

    Returns:
        The validated package name

    Raises:
        SecurityValidationError: If package name is invalid or dangerous
    """
    if not package or not isinstance(package, str):
        raise SecurityValidationError("Package name must be a non-empty string")

    package_clean = package.strip()

    # Check for shell dangerous characters
    for char in _SHELL_DANGEROUS_CHARS:
        if char in package_clean:
            raise SecurityValidationError(f"Package name contains dangerous character: '{char}'")

    # Check against blocklist
    package_lower = package_clean.lower()
    if package_lower in _BLOCKED_PACKAGES:
        raise SecurityValidationError(f"Package name '{package}' is blocked for security reasons")

    # Check pattern (allows package names with version specifiers like pkg==1.0.0)
    # Split on common version specifiers to validate the base name
    # Note: Don't split on @ as it's used for scoped npm packages like @types/node
    base_name = re.split(r"[=<>!\[]", package_clean)[0]

    if not _PACKAGE_NAME_PATTERN.match(base_name):
        raise SecurityValidationError(f"Package name '{base_name}' does not match allowed pattern")

    # Length check
    if len(package_clean) > 200:
        raise SecurityValidationError("Package name is too long (max 200 chars)")

    return package_clean


def validate_file_path(path: str, base_dir: str) -> str:
    """Validate a file path for security.

    Prevents:
    - Path traversal attacks (../)
    - Absolute paths outside base_dir
    - Shell metacharacters
    - Null bytes

    Args:
        path: File path to validate
        base_dir: Base directory that path must be within

    Returns:
        The validated, resolved absolute path

    Raises:
        SecurityValidationError: If path is invalid or attempts traversal
    """
    if not path or not isinstance(path, str):
        raise SecurityValidationError("Path must be a non-empty string")

    if not base_dir or not isinstance(base_dir, str):
        raise SecurityValidationError("Base directory must be a non-empty string")

    # Check for null bytes (can bypass checks in some systems)
    if "\x00" in path:
        raise SecurityValidationError("Path contains null byte")

    # Check for shell dangerous characters in path
    dangerous_in_path = {";", "&", "|", "`", "$", "(", ")", "{", "}", "<", ">"}
    for char in dangerous_in_path:
        if char in path:
            raise SecurityValidationError(f"Path contains dangerous shell character: '{char}'")

    # Resolve paths
    try:
        base_path = Path(base_dir).resolve()
        target_path = (base_path / path).resolve()
    except (ValueError, OSError) as e:
        raise SecurityValidationError(f"Invalid path: {e}") from e

    # Check that resolved path is within base directory
    try:
        target_path.relative_to(base_path)
    except ValueError:
        raise SecurityValidationError(
            f"Path '{path}' resolves outside base directory '{base_dir}'"
        ) from None

    return str(target_path)


# Allowed coverage commands (exact patterns)
ALLOWED_COVERAGE_COMMANDS: frozenset[str] = frozenset(
    [
        "npm run coverage",
        "npm run test:coverage",
        "npx vitest run --coverage",
        "npx jest --coverage",
        "pytest --cov",
        "python -m pytest --cov",
        "coverage run -m pytest",
        "go test -coverprofile",
    ]
)


def validate_coverage_command(cmd: str) -> str:
    """Validate a coverage command against the allowlist.

    Args:
        cmd: Coverage command to validate

    Returns:
        The validated command

    Raises:
        SecurityValidationError: If command is not in allowlist
    """
    if not cmd or not isinstance(cmd, str):
        raise SecurityValidationError("Command must be a non-empty string")

    cmd_clean = cmd.strip()

    # Check if command starts with any allowed pattern
    for allowed in ALLOWED_COVERAGE_COMMANDS:
        if cmd_clean.startswith(allowed):
            # Additional check: no shell metacharacters after the base command
            suffix = cmd_clean[len(allowed) :]
            dangerous = {";", "&", "|", "`", "$", "(", ")"}
            for char in dangerous:
                if char in suffix:
                    raise SecurityValidationError(
                        f"Coverage command contains dangerous character: '{char}'"
                    )
            return cmd_clean

    raise SecurityValidationError(
        f"Coverage command '{cmd}' is not in the allowed list. "
        f"Allowed patterns: {sorted(ALLOWED_COVERAGE_COMMANDS)}"
    )


# ============================================
# Prompt Injection Detection
# ============================================

# Patterns that indicate prompt injection attempts
_PROMPT_INJECTION_PATTERNS = [
    # Direct instruction override
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above|your)\s+instructions?", re.IGNORECASE),
    # Role manipulation
    re.compile(r"you\s+are\s+now\s+(a|an|the)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an|if)", re.IGNORECASE),
    re.compile(r"roleplay\s+as", re.IGNORECASE),
    # System prompt extraction
    re.compile(
        r"(show|reveal|display|print|output)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)",
        re.IGNORECASE,
    ),
    re.compile(r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)", re.IGNORECASE),
    re.compile(r"tell\s+me\s+your\s+(system\s+)?(prompt|instructions)", re.IGNORECASE),
    # Jailbreak patterns
    re.compile(r"(DAN|do\s+anything\s+now)\s+mode", re.IGNORECASE),
    re.compile(r"developer\s+mode\s+(enabled|on|activated)", re.IGNORECASE),
    # Delimiter/boundary attacks
    re.compile(r"```\s*(system|admin|root)\s*```", re.IGNORECASE),
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|endoftext\|>", re.IGNORECASE),
]


def detect_prompt_injection(content: str) -> list[str]:
    """Detect potential prompt injection patterns in content.

    Args:
        content: The content to check

    Returns:
        List of detected suspicious patterns (empty if none found)
    """
    if not content or not isinstance(content, str):
        return []

    detected = []

    for pattern in _PROMPT_INJECTION_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            # Get the matched text for logging
            match = pattern.search(content)
            if match:
                detected.append(match.group(0)[:100])  # Truncate long matches

    return detected


def sanitize_prompt_content(
    content: str,
    *,
    max_length: int = 50000,
    validate_injection: bool = True,
    boundary_markers: bool = True,
) -> str:
    """Sanitize content for safe inclusion in prompts.

    Args:
        content: The content to sanitize
        max_length: Maximum allowed length (truncate if exceeded)
        validate_injection: If True, check for injection patterns
        boundary_markers: If True, wrap content with boundary markers

    Returns:
        Sanitized content string

    Raises:
        SecurityValidationError: If injection is detected and validate_injection is True
    """
    if not content or not isinstance(content, str):
        return ""

    result = content

    # Truncate if too long
    if len(result) > max_length:
        result = result[:max_length] + "\n[CONTENT TRUNCATED]"
        logger.warning(f"Content truncated from {len(content)} to {max_length} chars")

    # Check for injection patterns
    if validate_injection:
        suspicious = detect_prompt_injection(result)
        if suspicious:
            logger.warning(f"Potential prompt injection detected: {suspicious[:3]}")
            # Wrap with strong boundary markers to isolate
            if boundary_markers:
                result = f"[USER_CONTENT_START]\n{result}\n[USER_CONTENT_END]"

    elif boundary_markers:
        result = f"[USER_CONTENT_START]\n{result}\n[USER_CONTENT_END]"

    return result
