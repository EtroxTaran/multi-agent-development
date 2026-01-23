import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Fix paths to find orchestrator module
# stored in dashboard/backend-nestjs/scripts/runner.py
# Root is ../../../
CURRENT_DIR = Path(__file__).parent.resolve()
CONDUCTOR_ROOT = CURRENT_DIR.parent.parent.parent.resolve()
sys.path.insert(0, str(CONDUCTOR_ROOT))

from orchestrator.orchestrator import Orchestrator

# Configure logging to stderr to avoid polluting stdout (which is for JSON events)
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)


class JSONProgressCallback:
    def __init__(self):
        pass

    def _emit(self, event_type, data):
        print(json.dumps({"type": event_type, "data": data}), flush=True)

    def on_node_start(self, node_name: str, state: dict):
        self._emit("node_start", {"node": node_name, "status": "active"})

    def on_node_end(self, node_name: str, state: dict):
        self._emit("node_end", {"node": node_name, "status": "completed"})

    def on_task_start(self, task_id: str, task_title: str):
        self._emit("action", {"type": "task_start", "task_id": task_id, "title": task_title})

    def on_task_complete(self, task_id: str, success: bool):
        self._emit("action", {"type": "task_complete", "task_id": task_id, "success": success})

    def on_interrupt(self, pending):
        self._emit("interrupt", pending)


async def main():
    parser = argparse.ArgumentParser(description="Conductor Runner")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--start", action="store_true", help="Start workflow")
    parser.add_argument("--resume", action="store_true", help="Resume workflow")
    parser.add_argument("--rollback", type=int, help="Rollback to phase")
    parser.add_argument("--reset", action="store_true", help="Reset workflow")
    parser.add_argument("--phase", type=int, default=1, help="Start phase")
    parser.add_argument("--end-phase", type=int, default=5, help="End phase")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation")
    parser.add_argument("--autonomous", action="store_true", help="Autonomous mode")
    parser.add_argument("--graph", action="store_true", help="Dump graph definition")

    args = parser.parse_args()

    project_dir = CONDUCTOR_ROOT / "projects" / args.project
    if not project_dir.exists():
        print(json.dumps({"error": f"Project {args.project} not found"}), flush=True)
        sys.exit(1)

    orchestrator = Orchestrator(
        project_dir=project_dir,
        console_output=False,  # Disable rich console output
    )

    callback = JSONProgressCallback()

    try:
        if args.start:
            await orchestrator.run_langgraph(
                start_phase=args.phase,
                end_phase=args.end_phase,
                skip_validation=args.skip_validation,
                autonomous=args.autonomous,
                use_rich_display=False,
                progress_callback=callback,
            )
        elif args.resume:
            await orchestrator.resume_langgraph(
                autonomous=args.autonomous, use_rich_display=False, progress_callback=callback
            )
        elif args.rollback:
            result = orchestrator.rollback_to_phase(args.rollback)
            print(json.dumps({"type": "rollback", "data": result}), flush=True)
        elif args.reset:
            orchestrator.reset()
            print(json.dumps({"type": "reset", "data": {"success": True}}), flush=True)
        elif args.graph:
            graph = orchestrator.get_workflow_definition()
            print(json.dumps(graph), flush=True)

    except Exception as e:
        print(json.dumps({"type": "error", "data": {"error": str(e)}}), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
