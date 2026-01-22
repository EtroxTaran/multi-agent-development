"""Kanban Board Synchronization.

Synchronizes the internal WorkflowState tasks with the markdown-based
Kanban board in .board/.

The board structure is:
- .board/backlog.md
- .board/in-progress.md
- .board/review.md
- .board/done.md
- .board/blocked.md
- .board/archive/YYYY-MM-DD.md
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..state import Task, TaskStatus, WorkflowState

logger = logging.getLogger(__name__)


class BoardSyncer:
    """Synchronizes WorkflowState tasks to .board/ markdown files."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.board_dir = project_dir / ".board"
        self.archive_dir = self.board_dir / "archive"

    def sync(self, state: WorkflowState) -> None:
        """Sync the current state to the board files.
        
        This is a one-way sync from State -> Board.
        The Board is a view of the State.
        """
        tasks = state.get("tasks", [])
        if not tasks:
            return

        # Ensure directories exist
        self.board_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Categorize tasks
        backlog = []
        in_progress = []
        review = []
        done = []
        blocked = []

        for task in tasks:
            status = task.get("status", TaskStatus.PENDING)
            # Normalize status to lowercase string
            status_str = status.value if hasattr(status, "value") else str(status).lower()

            if status_str == "pending":
                backlog.append(task)
            elif status_str == "in_progress":
                in_progress.append(task)
            elif status_str == "review" or status_str == "verification": # Handle variations
                review.append(task)
            elif status_str == "completed":
                done.append(task)
            elif status_str == "blocked" or status_str == "failed":
                blocked.append(task)
            else:
                # Default to backlog if unknown
                backlog.append(task)

        # Write files
        self._write_list(self.board_dir / "backlog.md", "Backlog", backlog)
        self._write_list(self.board_dir / "in-progress.md", "In Progress", in_progress)
        self._write_list(self.board_dir / "review.md", "Review / Verification", review)
        self._write_list(self.board_dir / "done.md", "Done", done)
        self._write_list(self.board_dir / "blocked.md", "Blocked / Failed", blocked)
        
        logger.info(f"Synced board: {len(tasks)} tasks updated across .board/ files")

    def _write_list(self, file_path: Path, title: str, tasks: List[Task]) -> None:
        """Write a list of tasks to a markdown file."""
        lines = [f"# {title}", "", f"Count: {len(tasks)}", ""]

        if not tasks:
            lines.append("_No tasks_")
        else:
            # Sort by priority/id
            # Priority map: critical=0, high=1, medium=2, low=3
            priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            
            def sort_key(t):
                p = t.get("priority", "medium").lower()
                return (priority_map.get(p, 2), t.get("id", ""))

            sorted_tasks = sorted(tasks, key=sort_key)

            for task in sorted_tasks:
                lines.append(self._format_task_card(task))
                lines.append("---")

        file_path.write_text("\n".join(lines))

    def _format_task_card(self, task: Task) -> str:
        """Format a single task as a markdown card."""
        tid = task.get("id", "UNKNOWN")
        title = task.get("title", "Untitled")
        priority = task.get("priority", "medium").upper()
        complexity = task.get("estimated_complexity", "medium")
        agent = "A04 (Impl)" # Default
        
        # Determine agent based on type/status if possible, but keep it simple for now
        
        lines = [
            f"## [{tid}] {title}",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **ID** | {tid} |",
            f"| **Priority** | {priority} |",
            f"| **Complexity** | {complexity} |",
            f"| **Agent** | {agent} |",
            ""
        ]
        
        deps = task.get("dependencies", [])
        if deps:
            lines.append(f"**Dependencies:** {', '.join(deps)}")
            lines.append("")
            
        user_story = task.get("user_story")
        if user_story:
            lines.append("### User Story")
            lines.append(user_story)
            lines.append("")

        criteria = task.get("acceptance_criteria", [])
        if criteria:
            lines.append("### Acceptance Criteria")
            for c in criteria:
                lines.append(f"- [ ] {c}")
            lines.append("")
            
        return "\n".join(lines)

def sync_board(state: WorkflowState) -> None:
    """Helper function to sync board from state."""
    try:
        project_dir = Path(state["project_dir"])
        syncer = BoardSyncer(project_dir)
        syncer.sync(state)
    except Exception as e:
        logger.warning(f"Failed to sync board: {e}")
