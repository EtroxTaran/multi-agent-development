"""Debug CLI for Time Travel Debugging.

Allows interactive inspection, rollback, and replay of workflow states.
"""

import asyncio
import cmd
import logging
import sys
from datetime import datetime
from pathlib import Path

from orchestrator.storage import get_checkpoint_storage
from orchestrator.utils.setup_logging import setup_logging

logger = logging.getLogger(__name__)


class TimeTravelDebugger(cmd.Cmd):
    """Interactive debugger for time travel."""

    intro = "Welcome to Time Travel Debugger. Type help or ? to list commands.\n"
    prompt = "(debug) "

    def __init__(self, project_dir: Path):
        super().__init__()
        self.project_dir = project_dir
        self.checkpoint_storage = get_checkpoint_storage(project_dir)
        self.checkpoints = []
        self._refresh_checkpoints()

    def _refresh_checkpoints(self):
        """Refresh checkpoint list."""
        self.checkpoints = self.checkpoint_storage.list_checkpoints()
        # Sort by creation time desc
        self.checkpoints.sort(key=lambda c: c.created_at, reverse=True)

    def do_list(self, arg):
        """List available checkpoints."""
        self._refresh_checkpoints()
        print(f"\nFound {len(self.checkpoints)} checkpoints:\n")

        print(f"{'ID':<10} {'Time':<20} {'Name':<30} {'Phase':<10} {'Notes'}")
        print("-" * 90)

        for i, cp in enumerate(self.checkpoints):
            cp_id = cp.id[:8]
            time_str = datetime.fromisoformat(cp.created_at).strftime("%Y-%m-%d %H:%M")
            name = (cp.name or "Auto-checkpoint")[:28]
            phase = str(cp.phase)
            notes = (cp.notes or "")[:20]
            print(f"{cp_id:<10} {time_str:<20} {name:<30} {phase:<10} {notes}")
        print("")

    def do_checkout(self, arg):
        """Rollback to a checkpoint. Usage: checkout <checkpoint_id_prefix>"""
        if not arg:
            print("Usage: checkout <checkpoint_id_prefix>")
            return

        target_id = arg.strip()
        matches = [cp for cp in self.checkpoints if cp.id.startswith(target_id)]

        if not matches:
            print(f"No checkpoint found starting with '{target_id}'")
            return

        if len(matches) > 1:
            print(f"Ambiguous ID '{target_id}'. Matches:")
            for cp in matches:
                print(f"  {cp.id[:8]} - {cp.name}")
            return

        checkpoint = matches[0]
        print(f"Rolling back to checkpoint: {checkpoint.name} ({checkpoint.id[:8]})...")

        confirm = input("This will overwrite current state. Continue? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

        success = self.checkpoint_storage.rollback_to_checkpoint(checkpoint.id, confirm=True)
        if success:
            print("Rollback successful. State restored.")
        else:
            print("Rollback failed.")

    def do_replay(self, arg):
        """Resume workflow from current state."""
        print("Resuming workflow...")
        try:
            # Run async resume in sync context
            from orchestrator.orchestrator import resume_workflow

            asyncio.run(resume_workflow(self.project_dir))
            print("\nWorkflow execution finished.")
        except Exception as e:
            print(f"Execution error: {e}")

    def do_inspect(self, arg):
        """Inspect current state or a checkpoint. Usage: inspect [checkpoint_id]"""
        target_cp = None
        if arg:
            target_id = arg.strip()
            matches = [cp for cp in self.checkpoints if cp.id.startswith(target_id)]
            if matches:
                target_cp = matches[0]
        else:
            # Inspect current state (requires workflow adapter, implementing simple version here)
            print("Inspecting current state not fully implemented in CLI yet.")
            return

        if target_cp:
            print(f"\nCheckpoint: {target_cp.name}")
            print(f"ID: {target_cp.id}")
            print(f"Phase: {target_cp.phase}")
            print(f"State Snapshot Keys: {list(target_cp.state_snapshot.keys())}")
            # print(json.dumps(target_cp.state_snapshot, indent=2)) # Too verbose usually

    def do_exit(self, arg):
        """Exit the debugger."""
        print("Bye!")
        return True

    def do_quit(self, arg):
        """Exit the debugger."""
        return self.do_exit(arg)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m orchestrator.cli.debug <project_name>")
        sys.exit(1)

    project_name = sys.argv[1]
    # Assume nested project structure for now or resolve path
    project_dir = Path(f"projects/{project_name}")
    if not project_dir.exists():
        # Try current dir if it looks like a project
        if (Path.cwd() / "PRODUCT.md").exists() and Path.cwd().name == project_name:
            project_dir = Path.cwd()
        else:
            print(f"Project directory not found: {project_dir}")
            sys.exit(1)

    setup_logging(project_dir, debug=True)

    try:
        debugger = TimeTravelDebugger(project_dir)
        debugger.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
