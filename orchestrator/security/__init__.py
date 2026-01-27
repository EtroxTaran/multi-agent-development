"""Security validation module for the orchestrator.

This module provides centralized security validation functions used across
the orchestrator to prevent:
- SQL injection in SurrealDB queries
- Command injection in subprocess calls
- Prompt injection in LLM inputs
- Path traversal attacks

Usage:
    from orchestrator.security import (
        validate_sql_table,
        validate_sql_field,
        validate_package_name,
        validate_file_path,
        validate_coverage_command,
        detect_prompt_injection,
        sanitize_prompt_content,
    )
"""

from .validators import (
    ALLOWED_FIELDS,
    ALLOWED_TABLES,
    SecurityValidationError,
    detect_prompt_injection,
    sanitize_prompt_content,
    validate_coverage_command,
    validate_file_path,
    validate_package_name,
    validate_sql_field,
    validate_sql_table,
)

__all__ = [
    "SecurityValidationError",
    "validate_sql_table",
    "validate_sql_field",
    "validate_package_name",
    "validate_file_path",
    "validate_coverage_command",
    "detect_prompt_injection",
    "sanitize_prompt_content",
    "ALLOWED_TABLES",
    "ALLOWED_FIELDS",
]
