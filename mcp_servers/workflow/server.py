"""MCP Server for workflow operations.

Provides access to workflow state, plans, and phase management
for AI agents coordinating multi-phase development workflows.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

logger = logging.getLogger(__name__)

# Get projects root from environment or default
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "projects"))


def create_server() -> Server:
    """Create and configure the MCP workflow server.

    Returns:
        Configured MCP Server instance
    """
    server = Server("mcp-workflow")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_state",
                description=(
                    "Get the current workflow state for a project. "
                    "Returns phase status, blockers, and progress."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="update_phase",
                description=(
                    "Update the status of a workflow phase. "
                    "Used to mark phases as in_progress, completed, or failed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Phase number (1-5)",
                            "minimum": 1,
                            "maximum": 5,
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "failed"],
                            "description": "New phase status",
                        },
                        "error": {
                            "type": "string",
                            "description": "Error message if status is failed",
                        },
                    },
                    "required": ["project", "phase", "status"],
                },
            ),
            Tool(
                name="get_plan",
                description=(
                    "Get the implementation plan for a project. "
                    "Returns the plan created during Phase 1."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="save_plan",
                description=(
                    "Save an implementation plan for a project. "
                    "Used in Phase 1 to store the generated plan."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "plan": {
                            "type": "object",
                            "description": "The implementation plan",
                        },
                    },
                    "required": ["project", "plan"],
                },
            ),
            Tool(
                name="create_checkpoint",
                description=(
                    "Create a checkpoint of the current workflow state. "
                    "Useful for rollback and recovery."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "label": {
                            "type": "string",
                            "description": "Checkpoint label/description",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="get_phase_feedback",
                description=(
                    "Get feedback for a specific phase. "
                    "Returns validation or verification feedback."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Phase number (2 or 4)",
                            "enum": [2, 4],
                        },
                    },
                    "required": ["project", "phase"],
                },
            ),
            Tool(
                name="save_phase_feedback",
                description=(
                    "Save feedback for a validation or verification phase. "
                    "Used by review agents to store their assessments."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Phase number (2 or 4)",
                            "enum": [2, 4],
                        },
                        "agent": {
                            "type": "string",
                            "description": "Agent name (cursor, gemini)",
                        },
                        "feedback": {
                            "type": "object",
                            "description": "Feedback content",
                        },
                    },
                    "required": ["project", "phase", "agent", "feedback"],
                },
            ),
            Tool(
                name="add_blocker",
                description=("Add a blocker to a phase. " "Blockers prevent phase completion."),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Phase number (1-5)",
                        },
                        "blocker": {
                            "type": "string",
                            "description": "Blocker description",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Blocker severity",
                            "default": "high",
                        },
                    },
                    "required": ["project", "phase", "blocker"],
                },
            ),
            Tool(
                name="resolve_blocker",
                description="Mark a blocker as resolved.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "phase": {
                            "type": "integer",
                            "description": "Phase number (1-5)",
                        },
                        "blocker_id": {
                            "type": "integer",
                            "description": "Index of the blocker to resolve",
                        },
                    },
                    "required": ["project", "phase", "blocker_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "get_state":
                result = await get_state(arguments["project"])
            elif name == "update_phase":
                result = await update_phase(
                    project=arguments["project"],
                    phase=arguments["phase"],
                    status=arguments["status"],
                    error=arguments.get("error"),
                )
            elif name == "get_plan":
                result = await get_plan(arguments["project"])
            elif name == "save_plan":
                result = await save_plan(
                    project=arguments["project"],
                    plan=arguments["plan"],
                )
            elif name == "create_checkpoint":
                result = await create_checkpoint(
                    project=arguments["project"],
                    label=arguments.get("label"),
                )
            elif name == "get_phase_feedback":
                result = await get_phase_feedback(
                    project=arguments["project"],
                    phase=arguments["phase"],
                )
            elif name == "save_phase_feedback":
                result = await save_phase_feedback(
                    project=arguments["project"],
                    phase=arguments["phase"],
                    agent=arguments["agent"],
                    feedback=arguments["feedback"],
                )
            elif name == "add_blocker":
                result = await add_blocker(
                    project=arguments["project"],
                    phase=arguments["phase"],
                    blocker=arguments["blocker"],
                    severity=arguments.get("severity", "high"),
                )
            elif name == "resolve_blocker":
                result = await resolve_blocker(
                    project=arguments["project"],
                    phase=arguments["phase"],
                    blocker_id=arguments["blocker_id"],
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        resources = []

        if PROJECTS_ROOT.exists():
            for project_dir in PROJECTS_ROOT.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    workflow_dir = project_dir / ".workflow"
                    if workflow_dir.exists():
                        resources.append(
                            Resource(
                                uri=f"workflow://{project_dir.name}/state",
                                name=f"Workflow State: {project_dir.name}",
                                description=f"Current workflow state for {project_dir.name}",
                                mimeType="application/json",
                            )
                        )

        return resources

    return server


def _get_workflow_dir(project: str) -> Path:
    """Get workflow directory for a project."""
    return PROJECTS_ROOT / project / ".workflow"


def _load_state(project: str) -> dict:
    """Load workflow state for a project."""
    state_file = _get_workflow_dir(project) / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return _create_default_state(project)


def _save_state(project: str, state: dict) -> None:
    """Save workflow state for a project."""
    workflow_dir = _get_workflow_dir(project)
    workflow_dir.mkdir(parents=True, exist_ok=True)

    state["updated_at"] = datetime.now().isoformat()
    state_file = workflow_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))


def _create_default_state(project: str) -> dict:
    """Create default workflow state."""
    return {
        "project_name": project,
        "current_phase": 1,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "phases": {
            "1": {"status": "pending", "attempts": 0, "blockers": []},
            "2": {"status": "pending", "attempts": 0, "blockers": []},
            "3": {"status": "pending", "attempts": 0, "blockers": []},
            "4": {"status": "pending", "attempts": 0, "blockers": []},
            "5": {"status": "pending", "attempts": 0, "blockers": []},
        },
        "git_commits": [],
        "checkpoints": [],
    }


async def get_state(project: str) -> dict:
    """Get workflow state for a project."""
    project_dir = PROJECTS_ROOT / project
    if not project_dir.exists():
        return {"error": f"Project not found: {project}"}

    return _load_state(project)


async def update_phase(
    project: str,
    phase: int,
    status: str,
    error: Optional[str] = None,
) -> dict:
    """Update phase status."""
    state = _load_state(project)

    phase_key = str(phase)
    if phase_key not in state["phases"]:
        return {"error": f"Invalid phase: {phase}"}

    state["phases"][phase_key]["status"] = status
    state["phases"][phase_key]["attempts"] += 1

    if status == "in_progress":
        state["phases"][phase_key]["started_at"] = datetime.now().isoformat()
        state["current_phase"] = phase
    elif status == "completed":
        state["phases"][phase_key]["completed_at"] = datetime.now().isoformat()
    elif status == "failed" and error:
        state["phases"][phase_key]["error"] = error

    _save_state(project, state)

    return {
        "success": True,
        "project": project,
        "phase": phase,
        "status": status,
    }


async def get_plan(project: str) -> dict:
    """Get implementation plan for a project."""
    plan_file = _get_workflow_dir(project) / "phases" / "planning" / "plan.json"

    if not plan_file.exists():
        return {"error": "Plan not found", "project": project}

    return {
        "project": project,
        "plan": json.loads(plan_file.read_text()),
    }


async def save_plan(project: str, plan: dict) -> dict:
    """Save implementation plan."""
    plan_dir = _get_workflow_dir(project) / "phases" / "planning"
    plan_dir.mkdir(parents=True, exist_ok=True)

    plan_file = plan_dir / "plan.json"
    plan_file.write_text(json.dumps(plan, indent=2))

    return {
        "success": True,
        "project": project,
        "plan_file": str(plan_file),
    }


async def create_checkpoint(project: str, label: Optional[str] = None) -> dict:
    """Create a workflow checkpoint."""
    state = _load_state(project)

    checkpoint = {
        "id": len(state.get("checkpoints", [])) + 1,
        "label": label or f"Checkpoint {len(state.get('checkpoints', [])) + 1}",
        "created_at": datetime.now().isoformat(),
        "phase": state["current_phase"],
        "state_snapshot": {
            "phases": state["phases"].copy(),
            "iteration_count": state["iteration_count"],
        },
    }

    if "checkpoints" not in state:
        state["checkpoints"] = []
    state["checkpoints"].append(checkpoint)

    _save_state(project, state)

    return {
        "success": True,
        "checkpoint_id": checkpoint["id"],
        "label": checkpoint["label"],
    }


async def get_phase_feedback(project: str, phase: int) -> dict:
    """Get feedback for a phase."""
    if phase not in (2, 4):
        return {"error": "Feedback only available for phases 2 and 4"}

    phase_name = "validation" if phase == 2 else "verification"
    feedback_dir = _get_workflow_dir(project) / "phases" / phase_name

    if not feedback_dir.exists():
        return {"error": f"No feedback found for phase {phase}"}

    feedback = {}
    for agent in ["cursor", "gemini"]:
        feedback_file = feedback_dir / f"{agent}_feedback.json"
        if feedback_file.exists():
            feedback[agent] = json.loads(feedback_file.read_text())

    return {
        "project": project,
        "phase": phase,
        "feedback": feedback,
    }


async def save_phase_feedback(
    project: str,
    phase: int,
    agent: str,
    feedback: dict,
) -> dict:
    """Save feedback for a phase."""
    if phase not in (2, 4):
        return {"error": "Feedback only available for phases 2 and 4"}

    phase_name = "validation" if phase == 2 else "verification"
    feedback_dir = _get_workflow_dir(project) / "phases" / phase_name
    feedback_dir.mkdir(parents=True, exist_ok=True)

    feedback_file = feedback_dir / f"{agent}_feedback.json"
    feedback["saved_at"] = datetime.now().isoformat()
    feedback_file.write_text(json.dumps(feedback, indent=2))

    return {
        "success": True,
        "project": project,
        "phase": phase,
        "agent": agent,
    }


async def add_blocker(
    project: str,
    phase: int,
    blocker: str,
    severity: str = "high",
) -> dict:
    """Add a blocker to a phase."""
    state = _load_state(project)
    phase_key = str(phase)

    if phase_key not in state["phases"]:
        return {"error": f"Invalid phase: {phase}"}

    blocker_entry = {
        "description": blocker,
        "severity": severity,
        "created_at": datetime.now().isoformat(),
        "resolved": False,
    }

    state["phases"][phase_key]["blockers"].append(blocker_entry)
    _save_state(project, state)

    return {
        "success": True,
        "project": project,
        "phase": phase,
        "blocker_id": len(state["phases"][phase_key]["blockers"]) - 1,
    }


async def resolve_blocker(project: str, phase: int, blocker_id: int) -> dict:
    """Resolve a blocker."""
    state = _load_state(project)
    phase_key = str(phase)

    if phase_key not in state["phases"]:
        return {"error": f"Invalid phase: {phase}"}

    blockers = state["phases"][phase_key]["blockers"]
    if blocker_id < 0 or blocker_id >= len(blockers):
        return {"error": f"Invalid blocker_id: {blocker_id}"}

    blockers[blocker_id]["resolved"] = True
    blockers[blocker_id]["resolved_at"] = datetime.now().isoformat()

    _save_state(project, state)

    return {
        "success": True,
        "project": project,
        "phase": phase,
        "blocker_id": blocker_id,
    }


async def run_server():
    """Run the MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
