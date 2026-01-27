"""Migration 0003: Flexible Types for Nested Objects.

Updates object fields to use FLEXIBLE TYPE for proper nested object support.
SurrealDB v2.x requires FLEXIBLE TYPE for nested objects in SCHEMAFULL tables.
Regular TYPE object strips nested data.
"""

from ....security import validate_sql_field, validate_sql_table
from ..base import BaseMigration, MigrationContext


class MigrationFlexibleTypes(BaseMigration):
    """Migrate object fields to FLEXIBLE TYPE for nested object support."""

    version = "0003"
    name = "flexible_types"
    dependencies = ["0002"]

    # Fields that need FLEXIBLE TYPE for nested objects
    FLEXIBLE_FIELDS = {
        "workflow_state": [
            ("phase_status", "FLEXIBLE TYPE object DEFAULT {}"),
            ("plan", "FLEXIBLE TYPE option<object>"),
            ("validation_feedback", "FLEXIBLE TYPE option<object>"),
            ("verification_feedback", "FLEXIBLE TYPE option<object>"),
            ("implementation_result", "FLEXIBLE TYPE option<object>"),
            ("research_findings", "FLEXIBLE TYPE option<object>"),
            ("token_usage", "FLEXIBLE TYPE option<object>"),
        ],
        "audit_entries": [
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "error_patterns": [
            ("error_context", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "checkpoints": [
            ("task_progress", "FLEXIBLE TYPE object DEFAULT {}"),
            ("state_snapshot", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "workflow_events": [
            ("event_data", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "phase_outputs": [
            ("content", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "logs": [
            ("content", "FLEXIBLE TYPE object DEFAULT {}"),
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
    }

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration."""
        for table, fields in self.FLEXIBLE_FIELDS.items():
            # Check if table exists
            if not await ctx.table_exists(table):
                continue

            # Validate table name to prevent SQL injection
            validated_table = validate_sql_table(table)

            for field_name, field_def in fields:
                # Validate field name to prevent SQL injection
                validated_field = validate_sql_field(field_name)
                # Remove old field definition and add new one
                await ctx.execute(
                    f"REMOVE FIELD IF EXISTS {validated_field} ON TABLE {validated_table}"
                )
                await ctx.execute(
                    f"DEFINE FIELD {validated_field} ON TABLE {validated_table} {field_def}"
                )

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback by reverting to regular TYPE object.

        Note: This may cause data loss for nested objects.
        """
        # Revert to non-FLEXIBLE types
        regular_fields = {
            "workflow_state": [
                ("phase_status", "TYPE object DEFAULT {}"),
                ("plan", "TYPE option<object>"),
                ("validation_feedback", "TYPE option<object>"),
                ("verification_feedback", "TYPE option<object>"),
                ("implementation_result", "TYPE option<object>"),
                ("research_findings", "TYPE option<object>"),
                ("token_usage", "TYPE option<object>"),
            ],
            "audit_entries": [
                ("metadata", "TYPE object DEFAULT {}"),
            ],
            "error_patterns": [
                ("error_context", "TYPE object DEFAULT {}"),
            ],
            "checkpoints": [
                ("task_progress", "TYPE object DEFAULT {}"),
                ("state_snapshot", "TYPE object DEFAULT {}"),
            ],
            "workflow_events": [
                ("event_data", "TYPE object DEFAULT {}"),
            ],
            "phase_outputs": [
                ("content", "TYPE object DEFAULT {}"),
            ],
            "logs": [
                ("content", "TYPE object DEFAULT {}"),
                ("metadata", "TYPE object DEFAULT {}"),
            ],
        }

        for table, fields in regular_fields.items():
            if not await ctx.table_exists(table):
                continue

            # Validate table name to prevent SQL injection
            validated_table = validate_sql_table(table)

            for field_name, field_def in fields:
                # Validate field name to prevent SQL injection
                validated_field = validate_sql_field(field_name)
                await ctx.execute(
                    f"REMOVE FIELD IF EXISTS {validated_field} ON TABLE {validated_table}"
                )
                await ctx.execute(
                    f"DEFINE FIELD {validated_field} ON TABLE {validated_table} {field_def}"
                )
