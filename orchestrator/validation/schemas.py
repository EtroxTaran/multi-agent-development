"""
Schema validation for agent outputs.

Validates agent outputs against JSON schemas to ensure
correct structure and data types.

Usage:
    from orchestrator.validation import SchemaValidator, validate_output

    validator = SchemaValidator(schemas_dir)
    errors = validator.validate("implementer_output.json", output)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates data against JSON schemas."""

    def __init__(
        self,
        schemas_dir: Optional[Path] = None,
    ):
        """Initialize schema validator.

        Args:
            schemas_dir: Directory containing JSON schema files
        """
        if schemas_dir:
            self.schemas_dir = Path(schemas_dir)
        else:
            # Find schemas directory relative to this file
            self.schemas_dir = Path(__file__).parent.parent.parent / "schemas"

        self._schema_cache: Dict[str, Dict[str, Any]] = {}

    def load_schema(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """Load a JSON schema by name.

        Args:
            schema_name: Schema filename (e.g., "implementer_output.json")

        Returns:
            Schema dictionary or None if not found
        """
        if schema_name in self._schema_cache:
            return self._schema_cache[schema_name]

        schema_path = self.schemas_dir / schema_name
        if not schema_path.exists():
            logger.warning(f"Schema not found: {schema_path}")
            return None

        try:
            schema = json.loads(schema_path.read_text())
            self._schema_cache[schema_name] = schema
            return schema
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema {schema_name}: {e}")
            return None

    def validate(
        self,
        schema_name: str,
        data: Dict[str, Any],
    ) -> List[str]:
        """Validate data against a schema.

        Args:
            schema_name: Schema filename
            data: Data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        schema = self.load_schema(schema_name)
        if not schema:
            return [f"Schema '{schema_name}' not found"]

        try:
            import jsonschema

            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors(data))

            return [
                f"{error.path}: {error.message}" if error.path else error.message
                for error in errors
            ]

        except ImportError:
            logger.warning("jsonschema not installed, using basic validation")
            return self._basic_validate(schema, data)

    def _basic_validate(
        self,
        schema: Dict[str, Any],
        data: Dict[str, Any],
    ) -> List[str]:
        """Basic validation without jsonschema library.

        Args:
            schema: JSON schema
            data: Data to validate

        Returns:
            List of validation errors
        """
        errors = []

        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Check field types
        properties = schema.get("properties", {})
        for field, value in data.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type:
                    if not self._check_type(value, expected_type):
                        errors.append(
                            f"Field '{field}' has wrong type: "
                            f"expected {expected_type}, got {type(value).__name__}"
                        )

        return errors

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON schema type.

        Args:
            value: Value to check
            expected_type: JSON schema type name

        Returns:
            True if type matches
        """
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        if expected_type not in type_map:
            return True  # Unknown type, allow it

        return isinstance(value, type_map[expected_type])

    def get_schema_info(self, schema_name: str) -> Dict[str, Any]:
        """Get information about a schema.

        Args:
            schema_name: Schema filename

        Returns:
            Dictionary with schema info
        """
        schema = self.load_schema(schema_name)
        if not schema:
            return {"error": "Schema not found"}

        return {
            "title": schema.get("title", "Unknown"),
            "description": schema.get("description", ""),
            "required": schema.get("required", []),
            "properties": list(schema.get("properties", {}).keys()),
        }


def validate_output(
    schema_path: str,
    data: Dict[str, Any],
    schemas_dir: Optional[Path] = None,
) -> List[str]:
    """Convenience function to validate output against schema.

    Args:
        schema_path: Path to schema file (relative or absolute)
        data: Data to validate
        schemas_dir: Optional schemas directory

    Returns:
        List of validation errors (empty if valid)
    """
    if schemas_dir:
        validator = SchemaValidator(schemas_dir)
    else:
        # Try to determine schemas dir from schema_path
        if "/" in schema_path:
            schemas_dir = Path(schema_path).parent
            schema_name = Path(schema_path).name
            validator = SchemaValidator(schemas_dir)
        else:
            validator = SchemaValidator()
            schema_name = schema_path

    return validator.validate(schema_name if "/" not in schema_path else Path(schema_path).name, data)


def validate_agent_output(
    agent_id: str,
    output: Dict[str, Any],
) -> List[str]:
    """Validate output for a specific agent.

    Args:
        agent_id: Agent identifier (e.g., "A04")
        output: Agent output to validate

    Returns:
        List of validation errors
    """
    # Map agent IDs to schema names
    schema_map = {
        "A01": "planner_output.json",
        "A03": "test_writer_output.json",
        "A04": "implementer_output.json",
        "A07": "reviewer_output.json",
        "A08": "reviewer_output.json",
        "A10": "integration_tester_output.json",
    }

    schema_name = schema_map.get(agent_id)
    if not schema_name:
        return []  # No schema defined for this agent

    validator = SchemaValidator()
    return validator.validate(schema_name, output)
