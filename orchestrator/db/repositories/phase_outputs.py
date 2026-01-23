"""Phase Outputs repository for storing workflow phase artifacts.

Stores structured output from each workflow phase:
- Phase 1: plan (planning output)
- Phase 2: cursor_feedback, gemini_feedback (validation)
- Phase 3: task_result (per-task implementation output)
- Phase 4: cursor_review, gemini_review (verification)
- Phase 5: summary (completion output)
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


# Output type constants
class OutputType:
    """Phase output type constants."""

    # Phase 1 - Planning
    PLAN = "plan"

    # Phase 2 - Validation
    CURSOR_FEEDBACK = "cursor_feedback"
    GEMINI_FEEDBACK = "gemini_feedback"

    # Phase 3 - Implementation
    TASK_RESULT = "task_result"

    # Phase 4 - Verification
    CURSOR_REVIEW = "cursor_review"
    GEMINI_REVIEW = "gemini_review"

    # Phase 5 - Completion
    SUMMARY = "summary"


@dataclass
class PhaseOutput:
    """Phase output record."""

    phase: int
    output_type: str
    content: dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        # Remove None values and id (managed by SurrealDB)
        return {k: v for k, v in data.items() if v is not None and k != "id"}


class PhaseOutputRepository(BaseRepository[PhaseOutput]):
    """Repository for phase output records."""

    table_name = "phase_outputs"

    def _to_record(self, data: dict[str, Any]) -> PhaseOutput:
        """Convert database record to PhaseOutput."""
        return PhaseOutput(
            id=str(data.get("id", "")),
            phase=data.get("phase", 0),
            output_type=data.get("output_type", ""),
            content=data.get("content", {}),
            task_id=data.get("task_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    async def save_output(
        self,
        phase: int,
        output_type: str,
        content: dict[str, Any],
        task_id: Optional[str] = None,
    ) -> PhaseOutput:
        """Save or update a phase output.

        If an output with the same phase/output_type/task_id exists, it's updated.
        Otherwise a new record is created.

        Args:
            phase: Workflow phase number (1-5)
            output_type: Type of output (see OutputType constants)
            content: Output content as dictionary
            task_id: Optional task ID for task-specific outputs

        Returns:
            Saved PhaseOutput record
        """
        async with get_connection(self.project_name) as conn:
            # Check if record exists
            if task_id:
                existing = await conn.query(
                    """
                    SELECT * FROM phase_outputs
                    WHERE phase = $phase
                    AND output_type = $output_type
                    AND task_id = $task_id
                    LIMIT 1
                    """,
                    {"phase": phase, "output_type": output_type, "task_id": task_id},
                )
            else:
                existing = await conn.query(
                    """
                    SELECT * FROM phase_outputs
                    WHERE phase = $phase
                    AND output_type = $output_type
                    AND task_id IS NONE
                    LIMIT 1
                    """,
                    {"phase": phase, "output_type": output_type},
                )

            now = datetime.now().isoformat()

            if existing:
                # Update existing record
                record_id = str(existing[0]["id"]).split(":")[-1]
                result = await conn.update(
                    f"phase_outputs:{record_id}",
                    {"content": content, "updated_at": now},
                )
                return self._to_record(result)
            else:
                # Create new record
                data = {
                    "phase": phase,
                    "output_type": output_type,
                    "content": content,
                    "task_id": task_id,
                    "created_at": now,
                    "updated_at": now,
                }
                result = await conn.create(self.table_name, data)
                return self._to_record(result)

    async def get_output(
        self,
        phase: int,
        output_type: str,
        task_id: Optional[str] = None,
    ) -> Optional[PhaseOutput]:
        """Get a specific phase output.

        Args:
            phase: Workflow phase number
            output_type: Type of output
            task_id: Optional task ID

        Returns:
            PhaseOutput if found, None otherwise
        """
        async with get_connection(self.project_name) as conn:
            if task_id:
                results = await conn.query(
                    """
                    SELECT * FROM phase_outputs
                    WHERE phase = $phase
                    AND output_type = $output_type
                    AND task_id = $task_id
                    LIMIT 1
                    """,
                    {"phase": phase, "output_type": output_type, "task_id": task_id},
                )
            else:
                results = await conn.query(
                    """
                    SELECT * FROM phase_outputs
                    WHERE phase = $phase
                    AND output_type = $output_type
                    AND task_id IS NONE
                    LIMIT 1
                    """,
                    {"phase": phase, "output_type": output_type},
                )

            if results:
                return self._to_record(results[0])
            return None

    async def get_phase_outputs(self, phase: int) -> list[PhaseOutput]:
        """Get all outputs for a specific phase.

        Args:
            phase: Workflow phase number

        Returns:
            List of phase outputs
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM phase_outputs
                WHERE phase = $phase
                ORDER BY created_at ASC
                """,
                {"phase": phase},
            )
            return [self._to_record(r) for r in results]

    async def get_task_outputs(self, task_id: str) -> list[PhaseOutput]:
        """Get all outputs for a specific task.

        Args:
            task_id: Task identifier

        Returns:
            List of phase outputs for the task
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM phase_outputs
                WHERE task_id = $task_id
                ORDER BY phase ASC, created_at ASC
                """,
                {"task_id": task_id},
            )
            return [self._to_record(r) for r in results]

    # Convenience methods for common output types

    async def save_plan(self, plan: dict[str, Any]) -> PhaseOutput:
        """Save the implementation plan (Phase 1)."""
        return await self.save_output(1, OutputType.PLAN, plan)

    async def get_plan(self) -> Optional[dict[str, Any]]:
        """Get the implementation plan."""
        output = await self.get_output(1, OutputType.PLAN)
        return output.content if output else None

    async def save_cursor_feedback(self, feedback: dict[str, Any]) -> PhaseOutput:
        """Save Cursor validation feedback (Phase 2)."""
        return await self.save_output(2, OutputType.CURSOR_FEEDBACK, feedback)

    async def save_gemini_feedback(self, feedback: dict[str, Any]) -> PhaseOutput:
        """Save Gemini validation feedback (Phase 2)."""
        return await self.save_output(2, OutputType.GEMINI_FEEDBACK, feedback)

    async def get_validation_feedback(self) -> dict[str, Optional[dict[str, Any]]]:
        """Get both validation feedbacks."""
        cursor = await self.get_output(2, OutputType.CURSOR_FEEDBACK)
        gemini = await self.get_output(2, OutputType.GEMINI_FEEDBACK)
        return {
            "cursor": cursor.content if cursor else None,
            "gemini": gemini.content if gemini else None,
        }

    async def save_task_result(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> PhaseOutput:
        """Save task implementation result (Phase 3)."""
        return await self.save_output(3, OutputType.TASK_RESULT, result, task_id)

    async def get_task_result(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get task implementation result."""
        output = await self.get_output(3, OutputType.TASK_RESULT, task_id)
        return output.content if output else None

    async def save_cursor_review(self, review: dict[str, Any]) -> PhaseOutput:
        """Save Cursor verification review (Phase 4)."""
        return await self.save_output(4, OutputType.CURSOR_REVIEW, review)

    async def save_gemini_review(self, review: dict[str, Any]) -> PhaseOutput:
        """Save Gemini verification review (Phase 4)."""
        return await self.save_output(4, OutputType.GEMINI_REVIEW, review)

    async def get_verification_reviews(self) -> dict[str, Optional[dict[str, Any]]]:
        """Get both verification reviews."""
        cursor = await self.get_output(4, OutputType.CURSOR_REVIEW)
        gemini = await self.get_output(4, OutputType.GEMINI_REVIEW)
        return {
            "cursor": cursor.content if cursor else None,
            "gemini": gemini.content if gemini else None,
        }

    async def save_summary(self, summary: dict[str, Any]) -> PhaseOutput:
        """Save completion summary (Phase 5)."""
        return await self.save_output(5, OutputType.SUMMARY, summary)

    async def get_summary(self) -> Optional[dict[str, Any]]:
        """Get completion summary."""
        output = await self.get_output(5, OutputType.SUMMARY)
        return output.content if output else None

    async def clear_phase(self, phase: int) -> int:
        """Clear all outputs for a phase.

        Args:
            phase: Phase number to clear

        Returns:
            Number of records deleted
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                DELETE FROM phase_outputs
                WHERE phase = $phase
                RETURN BEFORE
                """,
                {"phase": phase},
            )
            return len(results)


# Global repository cache
_repos: dict[str, PhaseOutputRepository] = {}


def get_phase_output_repository(project_name: str) -> PhaseOutputRepository:
    """Get or create a phase output repository for a project.

    Args:
        project_name: Project name

    Returns:
        PhaseOutputRepository instance
    """
    if project_name not in _repos:
        _repos[project_name] = PhaseOutputRepository(project_name)
    return _repos[project_name]
