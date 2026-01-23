"""Output parsing and validation for task implementation.

Handles parsing worker output and validating task results.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_task_output(stdout: str, task_id: str) -> dict:
    """Parse worker output, extracting task result JSON.

    Args:
        stdout: Raw output from worker
        task_id: Task ID for reference

    Returns:
        Parsed output dict
    """
    if not stdout:
        return {"task_id": task_id, "status": "unknown", "raw_output": ""}

    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            parsed["task_id"] = task_id
            # Validate the parsed output
            validation_result = validate_implementer_output(parsed)
            parsed["_validation"] = validation_result
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in output
    json_pattern = rf'\{{\s*"task_id"\s*:\s*"{task_id}"[^}}]*\}}'
    match = re.search(json_pattern, stdout, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            validation_result = validate_implementer_output(parsed)
            parsed["_validation"] = validation_result
            return parsed
        except json.JSONDecodeError:
            pass

    # Generic JSON extraction
    json_match = re.search(r"\{[\s\S]*\}", stdout)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                parsed["task_id"] = task_id
                validation_result = validate_implementer_output(parsed)
                parsed["_validation"] = validation_result
                return parsed
        except json.JSONDecodeError:
            pass

    return {"task_id": task_id, "status": "unknown", "raw_output": stdout}


def validate_implementer_output(output: dict) -> dict:
    """Validate implementer output against expected schema.

    Performs basic structural validation of task implementation output.
    Returns validation result with is_valid flag and any warnings/errors.

    Args:
        output: Parsed JSON output from implementer

    Returns:
        Validation result dict with keys: is_valid, warnings, errors
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Required fields for a valid task completion
    required_fields = ["task_id", "status"]
    for field in required_fields:
        if field not in output:
            errors.append(f"Missing required field: {field}")

    # Status validation
    valid_statuses = ["completed", "needs_clarification", "blocked", "failed", "unknown"]
    status = output.get("status")
    if status and status not in valid_statuses:
        warnings.append(f"Unexpected status value: {status}")

    # Validate completion fields when status is 'completed'
    if status == "completed":
        completion_fields = ["files_created", "files_modified", "tests_written", "tests_passed"]
        for field in completion_fields:
            if field not in output:
                warnings.append(f"Completion field missing: {field}")

        # Check tests_passed is boolean
        tests_passed = output.get("tests_passed")
        if tests_passed is not None and not isinstance(tests_passed, bool):
            warnings.append(f"tests_passed should be boolean, got {type(tests_passed).__name__}")

        # Check file lists are arrays
        for field in ["files_created", "files_modified", "tests_written"]:
            value = output.get(field)
            if value is not None and not isinstance(value, list):
                warnings.append(f"{field} should be a list, got {type(value).__name__}")

    # Validate clarification fields when status is 'needs_clarification'
    if status == "needs_clarification":
        if "question" not in output:
            errors.append("needs_clarification status requires 'question' field")
        if "options" in output and not isinstance(output.get("options"), list):
            warnings.append("'options' should be a list")

    # Try jsonschema validation if available
    try:
        import jsonschema

        schema = get_task_output_schema()
        if schema:
            try:
                jsonschema.validate(instance=output, schema=schema)
            except jsonschema.ValidationError as e:
                warnings.append(f"Schema validation: {e.message}")
    except ImportError:
        pass  # jsonschema not available, skip

    is_valid = len(errors) == 0

    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "errors": errors,
    }


def get_task_output_schema() -> Optional[dict]:
    """Load the task output JSON schema if available.

    Searches for task-output-schema.json in standard locations.

    Returns:
        Schema dict or None if not found
    """
    search_paths = [
        Path(__file__).parent.parent.parent.parent / "schemas" / "task-output-schema.json",
        Path.home() / ".config" / "conductor" / "schemas" / "task-output-schema.json",
    ]

    for path in search_paths:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load schema from {path}: {e}")
                return None

    return None
