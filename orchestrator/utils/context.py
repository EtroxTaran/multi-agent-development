"""Context management and versioning for the orchestration workflow.

Provides checksums and drift detection for context files to ensure
consistency across workflow phases.

Includes progress files support for agentic memory across sessions.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class CheckpointTrigger(Enum):
    """Triggers for creating checkpoints."""

    PHASE_TRANSITION = "phase_transition"
    FEEDBACK_RECEIVED = "feedback_received"
    IMPLEMENTATION_MILESTONE = "implementation_milestone"
    ERROR_BLOCKER = "error_blocker"
    MANUAL = "manual"


@dataclass
class ProgressEntry:
    """A single progress entry for agentic memory."""

    timestamp: str
    action: str
    details: str
    phase: Optional[int] = None
    completion_pct: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProgressEntry":
        return cls(**data)


@dataclass
class Checkpoint:
    """Checkpoint for resumable workflows."""

    checkpoint_id: str
    timestamp: str
    phase: int
    trigger: str
    state_hash: str
    files_changed: list[str] = field(default_factory=list)
    resumable: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(**data)


@dataclass
class FileChecksum:
    """Checksum information for a tracked file."""

    path: str
    checksum: str
    last_modified: str
    size: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FileChecksum":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ContextState:
    """State of all tracked context files."""

    files: dict[str, FileChecksum] = field(default_factory=dict)
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "captured_at": self.captured_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextState":
        """Create from dictionary."""
        files = {k: FileChecksum.from_dict(v) for k, v in data.get("files", {}).items()}
        return cls(
            files=files,
            captured_at=data.get("captured_at", datetime.now().isoformat()),
            version=data.get("version", "1.0"),
        )


@dataclass
class DriftResult:
    """Result of drift detection."""

    has_drift: bool
    changed_files: list[str] = field(default_factory=list)
    added_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    details: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class ContextManager:
    """Manages context file versioning and drift detection.

    Tracks important context files (AGENTS.md, PRODUCT.md, etc.) and
    detects when they change during a workflow execution.

    Also manages progress files for agentic memory across sessions.
    """

    # Files tracked by default
    TRACKED_FILES = {
        "agents": "AGENTS.md",
        "product": "PRODUCT.md",
        "cursor_rules": ".cursor/rules",
        "gemini": "GEMINI.md",
        "claude": "CLAUDE.md",
    }

    # Progress files for agentic memory
    PROGRESS_FILES = {
        "current_task": ".workflow/progress/current-task.md",
        "decisions": ".workflow/progress/decisions.md",
        "blockers": ".workflow/progress/blockers.md",
        "handoff_notes": ".workflow/progress/handoff-notes.md",
    }

    # Checkpoint directory
    CHECKPOINT_DIR = ".workflow/checkpoints"

    def __init__(self, project_dir: str | Path):
        """Initialize context manager.

        Args:
            project_dir: Root directory of the project
        """
        self.project_dir = Path(project_dir)
        self._tracked_files = self.TRACKED_FILES.copy()

    def add_tracked_file(self, key: str, relative_path: str) -> None:
        """Add a file to be tracked.

        Args:
            key: Unique identifier for the file
            relative_path: Path relative to project directory
        """
        self._tracked_files[key] = relative_path

    def remove_tracked_file(self, key: str) -> None:
        """Remove a file from tracking.

        Args:
            key: Identifier of the file to remove
        """
        self._tracked_files.pop(key, None)

    def compute_checksum(self, file_path: Path) -> str:
        """Compute SHA-256 checksum of a file.

        Args:
            file_path: Absolute path to the file

        Returns:
            Hexadecimal checksum string
        """
        if not file_path.exists():
            return ""

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_file_info(self, file_path: Path) -> Optional[FileChecksum]:
        """Get checksum information for a file.

        Args:
            file_path: Absolute path to the file

        Returns:
            FileChecksum if file exists, None otherwise
        """
        if not file_path.exists():
            return None

        stat = file_path.stat()
        return FileChecksum(
            path=str(file_path.relative_to(self.project_dir)),
            checksum=self.compute_checksum(file_path),
            last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            size=stat.st_size,
        )

    def capture_context(self) -> ContextState:
        """Capture current state of all tracked files.

        Returns:
            ContextState with checksums of all tracked files
        """
        context = ContextState()

        for key, rel_path in self._tracked_files.items():
            file_path = self.project_dir / rel_path
            file_info = self.get_file_info(file_path)
            if file_info:
                context.files[key] = file_info

        return context

    def validate_context(self, stored_state: ContextState) -> DriftResult:
        """Validate current context against stored state.

        Args:
            stored_state: Previously captured context state

        Returns:
            DriftResult with details about any changes
        """
        current_state = self.capture_context()
        result = DriftResult(has_drift=False)

        stored_keys = set(stored_state.files.keys())
        current_keys = set(current_state.files.keys())

        # Check for added files
        added = current_keys - stored_keys
        if added:
            result.added_files = list(added)
            result.has_drift = True

        # Check for removed files
        removed = stored_keys - current_keys
        if removed:
            result.removed_files = list(removed)
            result.has_drift = True

        # Check for changed files
        for key in stored_keys & current_keys:
            stored_file = stored_state.files[key]
            current_file = current_state.files[key]

            if stored_file.checksum != current_file.checksum:
                result.changed_files.append(key)
                result.has_drift = True
                result.details[key] = {
                    "old_checksum": stored_file.checksum[:12] + "...",
                    "new_checksum": current_file.checksum[:12] + "...",
                    "old_modified": stored_file.last_modified,
                    "new_modified": current_file.last_modified,
                    "old_size": stored_file.size,
                    "new_size": current_file.size,
                }

        return result

    def sync_context(self, current_state: Optional[ContextState] = None) -> ContextState:
        """Sync and return current context state.

        If current_state is provided, it will be updated with current checksums.
        Otherwise, captures fresh state.

        Args:
            current_state: Optional existing state to update

        Returns:
            Updated ContextState
        """
        return self.capture_context()

    def get_drift_summary(self, drift_result: DriftResult) -> str:
        """Generate a human-readable summary of context drift.

        Args:
            drift_result: Result from validate_context

        Returns:
            Formatted summary string
        """
        if not drift_result.has_drift:
            return "No context drift detected."

        lines = ["Context drift detected:"]

        if drift_result.changed_files:
            lines.append(f"  Modified: {', '.join(drift_result.changed_files)}")
            for key, details in drift_result.details.items():
                lines.append(f"    - {key}: {details['old_size']}B -> {details['new_size']}B")

        if drift_result.added_files:
            lines.append(f"  Added: {', '.join(drift_result.added_files)}")

        if drift_result.removed_files:
            lines.append(f"  Removed: {', '.join(drift_result.removed_files)}")

        return "\n".join(lines)

    def save_context_snapshot(self, output_path: Path) -> ContextState:
        """Save current context state to a file.

        Args:
            output_path: Path to save the snapshot

        Returns:
            The captured ContextState
        """
        state = self.capture_context()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)

        return state

    def load_context_snapshot(self, input_path: Path) -> Optional[ContextState]:
        """Load context state from a file.

        Args:
            input_path: Path to load the snapshot from

        Returns:
            ContextState if file exists, None otherwise
        """
        if not input_path.exists():
            return None

        with open(input_path) as f:
            data = json.load(f)

        return ContextState.from_dict(data)

    # ========== Progress Files Support ==========

    def _get_progress_path(self, key: str) -> Path:
        """Get path to a progress file.

        Args:
            key: Key from PROGRESS_FILES

        Returns:
            Absolute path to the progress file
        """
        return self.project_dir / self.PROGRESS_FILES[key]

    def init_progress_directory(self) -> None:
        """Initialize the progress directory structure."""
        progress_dir = self.project_dir / ".workflow/progress"
        progress_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_dir = self.project_dir / self.CHECKPOINT_DIR
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def update_current_task(
        self,
        task_name: str,
        phase: int,
        step: str,
        completion_pct: int,
        recent_actions: list[str],
        pending_items: list[str],
        notes: str = "",
    ) -> None:
        """Update the current task progress file.

        Args:
            task_name: Name of the current task
            phase: Current workflow phase (1-5)
            step: Current step description
            completion_pct: Completion percentage (0-100)
            recent_actions: List of recent actions taken
            pending_items: List of pending items
            notes: Optional notes for resumption
        """
        self.init_progress_directory()
        path = self._get_progress_path("current_task")

        content = f"""# Progress: {task_name}
## Last Updated: {datetime.now().isoformat()}

## Current Status
- Phase: {phase}
- Step: {step}
- Completion: {completion_pct}%

## Recent Actions
{chr(10).join(f'{i+1}. {action}' for i, action in enumerate(recent_actions[-5:]))}

## Pending Items
{chr(10).join(f'- [ ] {item}' for item in pending_items)}

## Notes for Resumption
{notes if notes else 'No additional notes.'}
"""
        path.write_text(content)

    def record_decision(self, decision: str, rationale: str) -> None:
        """Record a key decision to the decisions file.

        Args:
            decision: The decision made
            rationale: Reasoning behind the decision
        """
        self.init_progress_directory()
        path = self._get_progress_path("decisions")

        entry = f"""
## {datetime.now().isoformat()}
**Decision**: {decision}
**Rationale**: {rationale}

---
"""
        # Append to existing file
        existing = path.read_text() if path.exists() else "# Key Decisions\n"
        path.write_text(existing + entry)

    def record_blocker(
        self,
        description: str,
        severity: str,
        potential_solutions: list[str],
    ) -> None:
        """Record a blocker to the blockers file.

        Args:
            description: Description of the blocker
            severity: high, medium, or low
            potential_solutions: List of potential solutions
        """
        self.init_progress_directory()
        path = self._get_progress_path("blockers")

        entry = f"""
## Blocker: {datetime.now().isoformat()}
**Severity**: {severity}
**Description**: {description}

**Potential Solutions**:
{chr(10).join(f'- {sol}' for sol in potential_solutions)}

**Status**: OPEN

---
"""
        existing = path.read_text() if path.exists() else "# Blockers Log\n"
        path.write_text(existing + entry)

    def write_handoff_notes(
        self,
        current_phase: int,
        completed_work: list[str],
        in_progress_work: list[str],
        next_steps: list[str],
        important_context: str,
        warnings: list[str] = None,
    ) -> None:
        """Write comprehensive handoff notes for session resumption.

        Args:
            current_phase: Current workflow phase
            completed_work: List of completed work items
            in_progress_work: List of work items in progress
            next_steps: List of recommended next steps
            important_context: Important context to remember
            warnings: Optional list of warnings/gotchas
        """
        self.init_progress_directory()
        path = self._get_progress_path("handoff_notes")

        content = f"""# Session Handoff Notes
## Generated: {datetime.now().isoformat()}

## Workflow State
- **Current Phase**: {current_phase}
- **Status**: In Progress

## Completed Work
{chr(10).join(f'- [x] {item}' for item in completed_work)}

## In Progress
{chr(10).join(f'- [ ] {item}' for item in in_progress_work)}

## Recommended Next Steps
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(next_steps))}

## Important Context
{important_context}

"""
        if warnings:
            content += f"""## Warnings
{chr(10).join(f'⚠️ {w}' for w in warnings)}

"""
        content += """## Files to Read First
1. `.workflow/state.json` - Current workflow state
2. `.workflow/progress/current-task.md` - Current task details
3. `.workflow/progress/decisions.md` - Key decisions made
4. `PRODUCT.md` - Feature specification
"""
        path.write_text(content)

    def read_handoff_notes(self) -> Optional[str]:
        """Read handoff notes from previous session.

        Returns:
            Handoff notes content if exists, None otherwise
        """
        path = self._get_progress_path("handoff_notes")
        if path.exists():
            return path.read_text()
        return None

    # ========== Checkpoint Support ==========

    def create_checkpoint(
        self,
        phase: int,
        trigger: CheckpointTrigger,
        files_changed: list[str] = None,
        notes: str = "",
    ) -> Checkpoint:
        """Create a checkpoint for workflow resumption.

        Args:
            phase: Current workflow phase
            trigger: What triggered this checkpoint
            files_changed: List of files changed since last checkpoint
            notes: Optional notes about the checkpoint

        Returns:
            Created Checkpoint object
        """
        self.init_progress_directory()

        # Compute state hash from current context
        state = self.capture_context()
        state_hash = hashlib.sha256(
            json.dumps(state.to_dict(), sort_keys=True).encode()
        ).hexdigest()

        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            phase=phase,
            trigger=trigger.value,
            state_hash=state_hash,
            files_changed=files_changed or [],
            resumable=True,
            notes=notes,
        )

        # Save checkpoint
        checkpoint_dir = self.project_dir / self.CHECKPOINT_DIR
        checkpoint_path = checkpoint_dir / f"checkpoint-{checkpoint.checkpoint_id}.json"

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        # Also update latest checkpoint pointer
        latest_path = checkpoint_dir / "latest.json"
        with open(latest_path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        return checkpoint

    def get_latest_checkpoint(self) -> Optional[Checkpoint]:
        """Get the most recent checkpoint.

        Returns:
            Latest Checkpoint if exists, None otherwise
        """
        latest_path = self.project_dir / self.CHECKPOINT_DIR / "latest.json"
        if not latest_path.exists():
            return None

        with open(latest_path) as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)

    def list_checkpoints(self) -> list[Checkpoint]:
        """List all checkpoints in chronological order.

        Returns:
            List of Checkpoint objects
        """
        checkpoint_dir = self.project_dir / self.CHECKPOINT_DIR
        if not checkpoint_dir.exists():
            return []

        checkpoints = []
        for path in checkpoint_dir.glob("checkpoint-*.json"):
            with open(path) as f:
                data = json.load(f)
            checkpoints.append(Checkpoint.from_dict(data))

        return sorted(checkpoints, key=lambda c: c.timestamp)

    def get_resumption_context(self) -> dict:
        """Get all context needed to resume a workflow.

        Returns:
            Dictionary with handoff notes, latest checkpoint,
            current task, and recent decisions
        """
        result = {
            "handoff_notes": self.read_handoff_notes(),
            "latest_checkpoint": None,
            "current_task": None,
            "has_progress_files": False,
        }

        # Latest checkpoint
        checkpoint = self.get_latest_checkpoint()
        if checkpoint:
            result["latest_checkpoint"] = checkpoint.to_dict()

        # Current task
        task_path = self._get_progress_path("current_task")
        if task_path.exists():
            result["current_task"] = task_path.read_text()
            result["has_progress_files"] = True

        # Decisions
        decisions_path = self._get_progress_path("decisions")
        if decisions_path.exists():
            result["recent_decisions"] = decisions_path.read_text()

        # Blockers
        blockers_path = self._get_progress_path("blockers")
        if blockers_path.exists():
            result["blockers"] = blockers_path.read_text()

        return result
