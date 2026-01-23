#!/usr/bin/env python3
"""
Starts the Runtime Watchdog to monitor error logs and self-heal the system.
Usage: uv run scripts/start_watchdog.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from orchestrator.observability.watchdog import RuntimeWatchdog


async def main():
    # Identify workspace root (parent of conductor dir)
    workspace_root = project_root.parent
    print(f"Workspace root: {workspace_root}")

    from orchestrator.project_manager import ProjectManager

    pm = ProjectManager(workspace_root)
    projects = pm.list_projects()

    if not projects:
        print("No projects found to watch.")
        return

    tasks = []
    print(f"Starting Watchdogs for {len(projects)} projects...")

    for proj in projects:
        p_path = Path(proj["path"])
        p_name = proj["name"]
        print(f"  - Watching {p_name} at {p_path}")
        watchdog = RuntimeWatchdog(p_path)
        # Run each watchdog in background
        tasks.append(asyncio.create_task(watchdog.start()))

    # Keep main loop alive
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nStopping Watchdog...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
