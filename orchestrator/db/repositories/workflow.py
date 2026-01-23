"""Workflow state repository.

Provides persistent workflow state management with real-time updates.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from ..connection import get_connection
from .base import BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """Workflow state representation.

    Compatible with existing WorkflowState TypedDict.
    Note: project_name removed from storage in schema v2.0.0 (per-project database isolation).
    The project_name is still kept in the dataclass for identification/logging purposes.
    """

    project_dir: str = ""
    current_phase: int = 1
    phase_status: dict = field(default_factory=dict)
    iteration_count: int = 0
    plan: Optional[dict] = None
    validation_feedback: Optional[dict] = None
    verification_feedback: Optional[dict] = None
    implementation_result: Optional[dict] = None
    next_decision: Optional[str] = None
    execution_mode: str = "afk"
    discussion_complete: bool = False
    research_complete: bool = False
    research_findings: Optional[dict] = None
    token_usage: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self, include_timestamps: bool = False) -> dict[str, Any]:
        """Convert to dictionary.

        Args:
            include_timestamps: If False (default), omit created_at/updated_at
                so SurrealDB schema defaults (time::now()) handle them.
        """
        data = {
            "project_dir": self.project_dir,
            "current_phase": self.current_phase,
            "phase_status": self.phase_status,
            "iteration_count": self.iteration_count,
            "plan": self.plan,
            "validation_feedback": self.validation_feedback,
            "verification_feedback": self.verification_feedback,
            "implementation_result": self.implementation_result,
            "next_decision": self.next_decision,
            "execution_mode": self.execution_mode,
            "discussion_complete": self.discussion_complete,
            "research_complete": self.research_complete,
            "research_findings": self.research_findings,
            "token_usage": self.token_usage,
        }
        if include_timestamps:
            data["created_at"] = self.created_at.isoformat() if self.created_at else None
            data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        """Create from dictionary."""

        def parse_datetime(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            return None

        return cls(
            project_dir=data.get("project_dir", ""),
            current_phase=data.get("current_phase", 1),
            phase_status=data.get("phase_status", {}),
            iteration_count=data.get("iteration_count", 0),
            plan=data.get("plan"),
            validation_feedback=data.get("validation_feedback"),
            verification_feedback=data.get("verification_feedback"),
            implementation_result=data.get("implementation_result"),
            next_decision=data.get("next_decision"),
            execution_mode=data.get("execution_mode", "afk"),
            discussion_complete=data.get("discussion_complete", False),
            research_complete=data.get("research_complete", False),
            research_findings=data.get("research_findings"),
            token_usage=data.get("token_usage"),
            created_at=parse_datetime(data.get("created_at")),
            updated_at=parse_datetime(data.get("updated_at")),
        )


class WorkflowRepository(BaseRepository[WorkflowState]):
    """Repository for workflow state.

    Each project has exactly one workflow state record.
    """

    table_name = "workflow_state"

    def _to_record(self, data: dict[str, Any]) -> WorkflowState:
        return WorkflowState.from_dict(data)

    def _from_record(self, state: WorkflowState) -> dict[str, Any]:
        return state.to_dict()

    async def get_state(self) -> Optional[WorkflowState]:
        """Get current workflow state.

        Note: Database is already scoped to project (schema v2.0.0).
        Only one workflow_state record exists per database.

        Returns:
            WorkflowState or None if not initialized
        """
        async with get_connection(self.project_name) as conn:
            results = await conn.query(
                """
                SELECT * FROM workflow_state
                LIMIT 1
                """,
            )
            if results:
                return self._to_record(results[0])
            return None

    async def initialize_state(
        self,
        project_dir: str,
        execution_mode: str = "afk",
    ) -> WorkflowState:
        """Initialize workflow state for a new project.

        Note: Database is already scoped to project (schema v2.0.0).

        Args:
            project_dir: Project directory path
            execution_mode: Execution mode (afk or hitl)

        Returns:
            Initialized WorkflowState
        """
        # Check if state already exists
        existing = await self.get_state()
        if existing:
            logger.warning(f"State already exists for {self.project_name}, returning existing")
            return existing

        now = datetime.now()
        state = WorkflowState(
            project_dir=project_dir,
            current_phase=1,
            phase_status={
                "1": {"status": "pending", "attempts": 0},
                "2": {"status": "pending", "attempts": 0},
                "3": {"status": "pending", "attempts": 0},
                "4": {"status": "pending", "attempts": 0},
                "5": {"status": "pending", "attempts": 0},
            },
            iteration_count=0,
            execution_mode=execution_mode,
            created_at=now,
            updated_at=now,
        )

        # Use fixed record ID since there's only one state per project database
        async with get_connection(self.project_name) as conn:
            await conn.create(self.table_name, state.to_dict(), "state")

        logger.info(f"Initialized workflow state for {self.project_name}")
        return state

    async def update_state(self, **updates: Any) -> Optional[WorkflowState]:
        """Update workflow state fields.

        Args:
            **updates: Fields to update

        Returns:
            Updated state
        """
        async with get_connection(self.project_name) as conn:
            # Use two statements: MERGE updates, then SET updated_at
            # The second statement returns the final state
            result = await conn.query(
                """
                UPDATE workflow_state MERGE $updates;
                UPDATE workflow_state SET updated_at = time::now() RETURN AFTER;
                """,
                {"updates": updates},
            )
            if result:
                return self._to_record(result[0])
            return None

    async def set_phase(
        self,
        phase: int,
        status: str = "in_progress",
    ) -> Optional[WorkflowState]:
        """Set current phase and status.

        Args:
            phase: Phase number (1-5)
            status: Phase status

        Returns:
            Updated state
        """
        # Note: Using SELECT * because SurrealDB FLEXIBLE TYPE fields
        # don't work with projection queries (SELECT field_name)
        state = await self.get_state()
        if not state:
            return None

        phase_status = state.phase_status or {}
        phase_key = str(phase)

        if phase_key not in phase_status:
            phase_status[phase_key] = {"status": status, "attempts": 0}
        else:
            phase_status[phase_key]["status"] = status

        if status == "in_progress":
            phase_status[phase_key]["started_at"] = datetime.now().isoformat()
        elif status == "completed":
            phase_status[phase_key]["completed_at"] = datetime.now().isoformat()

        return await self.update_state(
            current_phase=phase,
            phase_status=phase_status,
        )

    async def increment_iteration(self) -> Optional[WorkflowState]:
        """Increment iteration counter.

        Returns:
            Updated state
        """
        async with get_connection(self.project_name) as conn:
            result = await conn.query(
                """
                UPDATE workflow_state
                SET iteration_count += 1, updated_at = time::now()
                RETURN AFTER
                """,
            )
            if result:
                return self._to_record(result[0])
            return None

    async def set_plan(self, plan: dict) -> Optional[WorkflowState]:
        """Set implementation plan.

        Args:
            plan: Plan dictionary

        Returns:
            Updated state
        """
        return await self.update_state(plan=plan)

    async def set_validation_feedback(
        self,
        agent: str,
        feedback: dict,
    ) -> Optional[WorkflowState]:
        """Set validation feedback from an agent.

        Args:
            agent: Agent identifier (cursor, gemini)
            feedback: Feedback dictionary

        Returns:
            Updated state
        """
        # Get current feedback to merge
        state = await self.get_state()
        current_feedback = state.validation_feedback or {} if state else {}
        current_feedback[agent] = feedback

        return await self.update_state(validation_feedback=current_feedback)

    async def set_verification_feedback(
        self,
        agent: str,
        feedback: dict,
    ) -> Optional[WorkflowState]:
        """Set verification feedback from an agent.

        Args:
            agent: Agent identifier (cursor, gemini)
            feedback: Feedback dictionary

        Returns:
            Updated state
        """
        state = await self.get_state()
        current_feedback = state.verification_feedback or {} if state else {}
        current_feedback[agent] = feedback

        return await self.update_state(verification_feedback=current_feedback)

    async def set_implementation_result(self, result: dict) -> Optional[WorkflowState]:
        """Set implementation result.

        Args:
            result: Implementation result dictionary

        Returns:
            Updated state
        """
        return await self.update_state(implementation_result=result)

    async def set_decision(self, decision: str) -> Optional[WorkflowState]:
        """Set next routing decision.

        Args:
            decision: Decision (continue, retry, escalate, abort)

        Returns:
            Updated state
        """
        return await self.update_state(next_decision=decision)

    async def add_token_usage(
        self,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
    ) -> Optional[WorkflowState]:
        """Add token usage metrics.

        Args:
            tokens_input: Input tokens
            tokens_output: Output tokens
            cost_usd: Cost in USD

        Returns:
            Updated state
        """
        state = await self.get_state()
        current_usage = state.token_usage or {} if state else {}

        current_usage["total_input"] = current_usage.get("total_input", 0) + tokens_input
        current_usage["total_output"] = current_usage.get("total_output", 0) + tokens_output
        current_usage["total_cost_usd"] = current_usage.get("total_cost_usd", 0) + cost_usd
        current_usage["last_updated"] = datetime.now().isoformat()

        return await self.update_state(token_usage=current_usage)

    async def reset_state(self) -> Optional[WorkflowState]:
        """Reset workflow state to initial.

        Returns:
            Reset state
        """
        state = await self.get_state()
        if not state:
            return None

        return await self.update_state(
            current_phase=1,
            phase_status={
                "1": {"status": "pending", "attempts": 0},
                "2": {"status": "pending", "attempts": 0},
                "3": {"status": "pending", "attempts": 0},
                "4": {"status": "pending", "attempts": 0},
                "5": {"status": "pending", "attempts": 0},
            },
            iteration_count=0,
            plan=None,
            validation_feedback=None,
            verification_feedback=None,
            implementation_result=None,
            next_decision=None,
            discussion_complete=False,
            research_complete=False,
            research_findings=None,
        )

    async def watch_state(
        self,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """Subscribe to state changes via Live Query.

        Args:
            callback: Function to call on state changes

        Returns:
            Live query UUID for unsubscribing
        """
        async with get_connection(self.project_name) as conn:
            return await conn.live(self.table_name, callback)

    async def get_summary(self) -> dict[str, Any]:
        """Get workflow state summary.

        Returns:
            Summary dictionary
        """
        state = await self.get_state()
        if not state:
            return {"status": "not_initialized"}

        # Calculate phase progress
        completed_phases = sum(
            1 for p in state.phase_status.values()
            if p.get("status") == "completed"
        )

        # Get git commit count
        git_commits = await self.get_git_commits()

        return {
            "project_name": self.project_name,  # From repository, not state
            "current_phase": state.current_phase,
            "completed_phases": completed_phases,
            "total_phases": 5,
            "iteration_count": state.iteration_count,
            "execution_mode": state.execution_mode,
            "has_plan": state.plan is not None,
            "has_validation": state.validation_feedback is not None,
            "has_implementation": state.implementation_result is not None,
            "has_verification": state.verification_feedback is not None,
            "discussion_complete": state.discussion_complete,
            "research_complete": state.research_complete,
            "token_usage": state.token_usage,
            "total_commits": len(git_commits),
            "created_at": state.created_at.isoformat() if state.created_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    async def record_git_commit(
        self,
        phase: int,
        commit_hash: str,
        message: str,
        task_id: Optional[str] = None,
        files_changed: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Record a git commit.

        Args:
            phase: Phase number when commit was made
            commit_hash: Git commit hash
            message: Commit message
            task_id: Optional task ID
            files_changed: Optional list of changed files

        Returns:
            Created commit record
        """
        async with get_connection(self.project_name) as conn:
            result = await conn.create(
                "git_commits",
                {
                    "phase": phase,
                    "commit_hash": commit_hash,
                    "message": message,
                    "task_id": task_id,
                    "files_changed": files_changed or [],
                },
            )
            logger.info(f"Recorded git commit {commit_hash[:8]} for phase {phase}")
            return result

    async def get_git_commits(
        self,
        phase: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get git commits with optional filters.

        Args:
            phase: Optional phase filter
            task_id: Optional task ID filter

        Returns:
            List of commit records
        """
        async with get_connection(self.project_name) as conn:
            if phase is not None:
                results = await conn.query(
                    "SELECT * FROM git_commits WHERE phase = $phase ORDER BY created_at DESC",
                    {"phase": phase},
                )
            elif task_id is not None:
                results = await conn.query(
                    "SELECT * FROM git_commits WHERE task_id = $task_id ORDER BY created_at DESC",
                    {"task_id": task_id},
                )
            else:
                results = await conn.query(
                    "SELECT * FROM git_commits ORDER BY created_at DESC"
                )
            return results or []

    async def reset_to_phase(self, phase_num: int) -> Optional[WorkflowState]:
        """Reset workflow state to before a specific phase.

        Args:
            phase_num: Phase to reset to (this phase and later will be reset)

        Returns:
            Updated state
        """
        state = await self.get_state()
        if not state:
            return None

        # Reset specified phase and all later phases
        phase_status = state.phase_status.copy()
        for i in range(phase_num, 6):
            phase_key = str(i)
            if phase_key in phase_status:
                phase_status[phase_key] = {
                    "status": "pending",
                    "attempts": 0,
                }

        return await self.update_state(
            current_phase=phase_num,
            phase_status=phase_status,
        )


# Global repository cache
_workflow_repos: dict[str, WorkflowRepository] = {}


def get_workflow_repository(project_name: str) -> WorkflowRepository:
    """Get or create workflow repository for a project.

    Args:
        project_name: Project name

    Returns:
        WorkflowRepository instance
    """
    if project_name not in _workflow_repos:
        _workflow_repos[project_name] = WorkflowRepository(project_name)
    return _workflow_repos[project_name]
