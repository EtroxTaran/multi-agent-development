"""Session handoff for workflow resumability.

Generates context briefs for resuming interrupted workflows,
capturing the current state, recent actions, and next steps.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .action_log import get_action_log
from .error_aggregator import AggregatedError, get_error_aggregator

logger = logging.getLogger(__name__)


@dataclass
class HandoffBrief:
    """Context for resuming a workflow session."""

    generated_at: str
    project: str

    # Progress
    current_phase: int
    phase_status: dict[str, str]
    current_task: Optional[str] = None
    completed_tasks: list[str] = field(default_factory=list)
    total_tasks: int = 0

    # Context
    last_actions: list[dict] = field(default_factory=list)
    pending_work: list[str] = field(default_factory=list)

    # Issues
    unresolved_errors: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    # Resume hints
    next_action: str = ""
    files_in_progress: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    # Metadata
    workflow_duration_minutes: Optional[float] = None
    last_activity: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "project": self.project,
            "current_phase": self.current_phase,
            "phase_status": self.phase_status,
            "current_task": self.current_task,
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "last_actions": self.last_actions,
            "pending_work": self.pending_work,
            "unresolved_errors": self.unresolved_errors,
            "blockers": self.blockers,
            "next_action": self.next_action,
            "files_in_progress": self.files_in_progress,
            "open_questions": self.open_questions,
            "workflow_duration_minutes": self.workflow_duration_minutes,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HandoffBrief":
        return cls(**data)

    def to_markdown(self) -> str:
        """Generate a human-readable markdown version."""
        lines = [
            f"# Handoff Brief: {self.project}",
            "",
            f"**Generated:** {self.generated_at}",
            f"**Last Activity:** {self.last_activity or 'Unknown'}",
            "",
            "## Current State",
            "",
            f"**Phase:** {self.current_phase}/5",
        ]

        if self.current_task:
            lines.append(f"**Current Task:** {self.current_task}")

        if self.total_tasks > 0:
            progress = len(self.completed_tasks) / self.total_tasks * 100
            lines.append(
                f"**Task Progress:** {len(self.completed_tasks)}/{self.total_tasks} ({progress:.0f}%)"
            )

        lines.extend(
            [
                "",
                "### Phase Status",
                "",
            ]
        )

        phase_names = [
            "1. Planning",
            "2. Validation",
            "3. Implementation",
            "4. Verification",
            "5. Completion",
        ]
        for i, name in enumerate(phase_names, 1):
            status = self.phase_status.get(
                str(i),
                self.phase_status.get(
                    ["planning", "validation", "implementation", "verification", "completion"][
                        i - 1
                    ],
                    "pending",
                ),
            )
            emoji = {"completed": "✅", "in_progress": "🔄", "failed": "❌", "blocked": "🚫"}.get(
                status, "⏳"
            )
            lines.append(f"- {emoji} {name}: {status}")

        if self.last_actions:
            lines.extend(
                [
                    "",
                    "## Recent Actions",
                    "",
                ]
            )
            for action in self.last_actions[:10]:
                timestamp = action.get("timestamp", "")
                if timestamp:
                    timestamp = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
                agent = f"[{action.get('agent')}]" if action.get("agent") else ""
                phase = f"[P{action.get('phase')}]" if action.get("phase") else ""
                lines.append(f"- {timestamp} {phase} {agent} {action.get('message', '')}")

        if self.unresolved_errors:
            lines.extend(
                [
                    "",
                    f"## Unresolved Errors ({len(self.unresolved_errors)})",
                    "",
                ]
            )
            for error in self.unresolved_errors[:5]:
                severity = error.get("severity", "error")
                emoji = {"critical": "🔴", "error": "🟠", "warning": "🟡"}.get(severity, "⚪")
                phase = f"P{error.get('phase')}" if error.get("phase") else ""
                task = error.get("task_id", "")
                location = f"[{phase}/{task}]" if phase or task else ""
                lines.append(f"- {emoji} {location} {error.get('message', '')[:100]}")

        if self.blockers:
            lines.extend(
                [
                    "",
                    "## Blockers",
                    "",
                ]
            )
            for blocker in self.blockers:
                lines.append(f"- 🚫 {blocker}")

        if self.pending_work:
            lines.extend(
                [
                    "",
                    "## Pending Work",
                    "",
                ]
            )
            for work in self.pending_work:
                lines.append(f"- [ ] {work}")

        if self.open_questions:
            lines.extend(
                [
                    "",
                    "## Open Questions",
                    "",
                ]
            )
            for question in self.open_questions:
                lines.append(f"- ❓ {question}")

        lines.extend(
            [
                "",
                "## Next Action",
                "",
                f"**{self.next_action}**",
            ]
        )

        if self.files_in_progress:
            lines.extend(
                [
                    "",
                    "### Files in Progress",
                    "",
                ]
            )
            for file in self.files_in_progress:
                lines.append(f"- `{file}`")

        return "\n".join(lines)


class HandoffGenerator:
    """Generates handoff briefs for session resumption."""

    def __init__(self, project_dir: str | Path):
        """Initialize the handoff generator.

        Args:
            project_dir: Root project directory
        """
        self.project_dir = Path(project_dir)
        self.workflow_dir = self.project_dir / ".workflow"
        self.handoff_file = self.workflow_dir / "handoff_brief.json"
        self.handoff_md_file = self.workflow_dir / "handoff_brief.md"

    def _load_state(self) -> Optional[dict]:
        """Load workflow state from database.

        Reads state from SurrealDB via WorkflowStorageAdapter.
        """
        try:
            from ..storage.workflow_adapter import get_workflow_storage

            project_name = self.project_dir.name
            storage = get_workflow_storage(self.project_dir, project_name)
            state_data = storage.get_state()

            if state_data is not None:
                # Convert WorkflowStateData to dict for handoff generation
                return {
                    "project_name": state_data.project_name,
                    "current_phase": state_data.current_phase,
                    "phases": state_data.phases or {},
                    "execution_mode": state_data.execution_mode,
                    "iteration_count": state_data.iteration_count,
                    "errors": state_data.errors or [],
                    "created_at": state_data.created_at,
                    "updated_at": state_data.updated_at,
                }
        except Exception as e:
            logger.debug(f"Failed to load state from database: {e}, using default state")

        return None

    def _load_tasks(self) -> tuple[list[dict], Optional[str]]:
        """Load task information from database.

        Returns:
            Tuple of (all_tasks, current_task_id)
        """
        try:
            from ..db.repositories.phase_outputs import get_phase_output_repository
            from ..storage.async_utils import run_async

            project_name = self.project_dir.name
            repo = get_phase_output_repository(project_name)
            plan = run_async(repo.get_plan())

            if not plan:
                return [], None

            tasks = plan.get("tasks", [])
            current = None
            for task in tasks:
                if task.get("status") == "in_progress":
                    current = task.get("id")
                    break
            return tasks, current
        except Exception as e:
            logger.debug(f"Failed to load tasks from database: {e}")
            return [], None

    def _determine_next_action(
        self,
        state: dict,
        errors: list[AggregatedError],
        current_task: Optional[str],
    ) -> str:
        """Determine the recommended next action."""
        # Check for critical errors
        critical_errors = [e for e in errors if e.severity.value == "critical"]
        if critical_errors:
            return f"Resolve critical error: {critical_errors[0].message[:80]}"

        # Check phase status
        current_phase = state.get("current_phase", 1)
        phases = state.get("phases", {})

        phase_names = ["planning", "validation", "implementation", "verification", "completion"]
        if current_phase <= len(phase_names):
            phase_name = phase_names[current_phase - 1]
            phase_data = phases.get(phase_name, {})
            phase_status = phase_data.get("status", "pending")

            if phase_status == "failed":
                error = phase_data.get("error", "Unknown error")
                attempts = phase_data.get("attempts", 0)
                max_attempts = phase_data.get("max_attempts", 3)
                if attempts < max_attempts:
                    return f"Retry phase {current_phase} ({phase_name}): {error[:60]}"
                else:
                    return f"Investigate phase {current_phase} failure (max retries exceeded)"

            if phase_status == "blocked":
                blockers = phase_data.get("blockers", [])
                if blockers:
                    return f"Resolve blocker: {blockers[0][:60]}"
                return f"Investigate blocked phase {current_phase}"

            if phase_status == "in_progress":
                if current_task:
                    return f"Continue task {current_task} in phase {current_phase}"
                return f"Continue phase {current_phase} ({phase_name})"

            if phase_status == "pending":
                return f"Start phase {current_phase} ({phase_name})"

            if phase_status == "completed" and current_phase < 5:
                return f"Proceed to phase {current_phase + 1}"

        return "Review workflow status and determine next steps"

    def _get_pending_work(self, state: dict, tasks: list[dict]) -> list[str]:
        """Get list of pending work items."""
        pending = []

        # Check incomplete phases
        current_phase = state.get("current_phase", 1)
        phase_names = ["Planning", "Validation", "Implementation", "Verification", "Completion"]

        for i, name in enumerate(phase_names, 1):
            if i > current_phase:
                pending.append(f"Complete Phase {i}: {name}")
            elif i == current_phase:
                phases = state.get("phases", {})
                phase_key = name.lower()
                if phases.get(phase_key, {}).get("status") not in ["completed"]:
                    pending.append(f"Finish Phase {i}: {name}")

        # Check incomplete tasks
        for task in tasks:
            if task.get("status") in ["pending", "blocked"]:
                pending.append(f"Task {task.get('id', '?')}: {task.get('title', 'Unknown')}")

        return pending[:10]  # Limit to 10 items

    def _get_files_in_progress(
        self, tasks: list[dict], current_task_id: Optional[str]
    ) -> list[str]:
        """Get files currently being worked on."""
        files = set()

        for task in tasks:
            if task.get("status") == "in_progress" or task.get("id") == current_task_id:
                files.update(task.get("files_to_create", []))
                files.update(task.get("files_to_modify", []))
                files.update(task.get("test_files", []))

        return list(files)[:10]

    def _get_open_questions(self) -> list[str]:
        """Get open questions requiring human input from database."""
        questions = []

        try:
            from ..db.repositories.logs import get_logs_repository
            from ..storage.async_utils import run_async

            project_name = self.project_dir.name
            repo = get_logs_repository(project_name)

            # Check for pending clarification requests
            clarification_logs = run_async(repo.get_by_type("clarification_request"))
            for log in clarification_logs:
                content = log.get("content", {})
                for q in content.get("pending_questions", []):
                    questions.append(q.get("question", ""))

            # Check for escalations requiring human input
            escalation_logs = run_async(repo.get_by_type("escalation"))
            for log in escalation_logs:
                content = log.get("content", {})
                if content.get("requires_human_input"):
                    questions.append(content.get("question", "Human input required"))

        except Exception as e:
            logger.debug(f"Failed to get open questions from database: {e}")

        return questions

    def generate(self, include_actions: int = 20) -> HandoffBrief:
        """Generate a handoff brief.

        Args:
            include_actions: Number of recent actions to include

        Returns:
            HandoffBrief with current context
        """
        now = datetime.now().isoformat()

        # Load state
        state = self._load_state() or {
            "project_name": self.project_dir.name,
            "current_phase": 1,
            "phases": {},
        }

        # Load tasks
        tasks, current_task_id = self._load_tasks()
        completed_tasks = [t.get("id", "") for t in tasks if t.get("status") == "completed"]

        # Load action log
        action_log = get_action_log(self.workflow_dir)
        recent_actions = action_log.get_recent(include_actions)

        # Load errors
        error_aggregator = get_error_aggregator(self.workflow_dir)
        unresolved_errors = error_aggregator.get_unresolved()

        # Build phase status
        phase_status = {}
        phases = state.get("phases", {})
        for phase_name, phase_data in phases.items():
            phase_num = {
                "planning": "1",
                "validation": "2",
                "implementation": "3",
                "verification": "4",
                "completion": "5",
            }.get(phase_name)
            if phase_num:
                phase_status[phase_num] = phase_data.get("status", "pending")

        # Collect blockers
        blockers = []
        for phase_data in phases.values():
            blockers.extend(phase_data.get("blockers", []))

        # Calculate workflow duration
        created_at = state.get("created_at")
        duration_minutes = None
        if created_at:
            try:
                start = datetime.fromisoformat(created_at)
                duration_minutes = (datetime.now() - start).total_seconds() / 60
            except ValueError:
                pass

        # Get last activity timestamp
        last_activity = state.get("updated_at")
        if recent_actions:
            last_activity = recent_actions[0].timestamp

        # Generate brief
        brief = HandoffBrief(
            generated_at=now,
            project=state.get("project_name", self.project_dir.name),
            current_phase=state.get("current_phase", 1),
            phase_status=phase_status,
            current_task=current_task_id,
            completed_tasks=completed_tasks,
            total_tasks=len(tasks),
            last_actions=[a.to_dict() for a in recent_actions],
            pending_work=self._get_pending_work(state, tasks),
            unresolved_errors=[e.to_dict() for e in unresolved_errors[:10]],
            blockers=blockers,
            next_action=self._determine_next_action(state, unresolved_errors, current_task_id),
            files_in_progress=self._get_files_in_progress(tasks, current_task_id),
            open_questions=self._get_open_questions(),
            workflow_duration_minutes=round(duration_minutes, 1) if duration_minutes else None,
            last_activity=last_activity,
        )

        return brief

    def save(self, brief: Optional[HandoffBrief] = None) -> tuple[Path, Path]:
        """Generate and save handoff brief to files.

        Args:
            brief: Optional pre-generated brief (generates new one if not provided)

        Returns:
            Tuple of (json_path, markdown_path)
        """
        if brief is None:
            brief = self.generate()

        # Ensure workflow directory exists
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        with open(self.handoff_file, "w", encoding="utf-8") as f:
            json.dump(brief.to_dict(), f, indent=2)

        # Save Markdown
        with open(self.handoff_md_file, "w", encoding="utf-8") as f:
            f.write(brief.to_markdown())

        return self.handoff_file, self.handoff_md_file

    def load(self) -> Optional[HandoffBrief]:
        """Load existing handoff brief.

        Returns:
            HandoffBrief if exists, None otherwise
        """
        if not self.handoff_file.exists():
            return None

        try:
            with open(self.handoff_file, encoding="utf-8") as f:
                data = json.load(f)
            return HandoffBrief.from_dict(data)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load handoff brief: {e}")
            return None


def generate_handoff(project_dir: str | Path, save: bool = True) -> HandoffBrief:
    """Generate a handoff brief for a project.

    Args:
        project_dir: Project directory
        save: Whether to save to files

    Returns:
        The generated HandoffBrief
    """
    generator = HandoffGenerator(project_dir)
    brief = generator.generate()

    if save:
        generator.save(brief)

    return brief
