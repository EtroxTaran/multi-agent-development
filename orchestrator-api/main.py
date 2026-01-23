"""
Orchestrator Microservice - Thin REST API layer for Python orchestrator.

This microservice exposes the Python orchestrator (ProjectManager, Orchestrator)
as REST endpoints, allowing the NestJS backend to call orchestrator functions
via HTTP instead of importing Python modules directly.
"""

import asyncio
import json
import logging
import os
import sys
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Optional, List, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add orchestrator to path
CONDUCTOR_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONDUCTOR_ROOT))

from orchestrator.orchestrator import Orchestrator
from orchestrator.project_manager import ProjectManager
from orchestrator.storage.audit_adapter import get_audit_storage
from orchestrator.agents.budget import BudgetManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
PROJECTS_PATH = CONDUCTOR_ROOT / "projects"


# Enums
class WorkflowStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


# Request/Response Models
class ProjectSummary(BaseModel):
    name: str
    path: str
    created_at: Optional[str] = None
    current_phase: int = 0
    has_documents: bool = False
    has_product_spec: bool = False
    has_claude_md: bool = False
    has_gemini_md: bool = False
    has_cursor_rules: bool = False


class ProjectStatusResponse(BaseModel):
    name: str
    path: str
    config: Optional[dict] = None
    state: Optional[dict] = None
    files: dict[str, bool] = Field(default_factory=dict)
    phases: dict[str, dict] = Field(default_factory=dict)


class InitProjectResponse(BaseModel):
    success: bool
    project_dir: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    mode: str = "langgraph"
    status: WorkflowStatus
    project: Optional[str] = None
    current_phase: Optional[int] = None
    phase_status: dict[str, str] = Field(default_factory=dict)
    pending_interrupt: Optional[dict] = None
    message: Optional[str] = None


class WorkflowHealthResponse(BaseModel):
    status: str
    project: Optional[str] = None
    current_phase: Optional[int] = None
    phase_status: Optional[str] = None
    iteration_count: int = 0
    last_updated: Optional[str] = None
    agents: dict[str, bool] = Field(default_factory=dict)
    langgraph_enabled: bool = False
    has_context: bool = False
    total_commits: int = 0


class WorkflowStartRequest(BaseModel):
    start_phase: int = Field(default=1, ge=1, le=5)
    end_phase: int = Field(default=5, ge=1, le=5)
    skip_validation: bool = False
    autonomous: bool = False


class WorkflowStartResponse(BaseModel):
    success: bool
    mode: str = "langgraph"
    paused: bool = False
    message: Optional[str] = None
    error: Optional[str] = None
    results: Optional[dict] = None


class TaskInfo(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    dependencies: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    files_to_modify: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    complexity_score: Optional[float] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    tasks: list[TaskInfo] = Field(default_factory=list)
    total: int = 0
    completed: int = 0
    in_progress: int = 0
    pending: int = 0
    failed: int = 0


class BudgetStatus(BaseModel):
    total_spent_usd: float = 0.0
    project_budget_usd: Optional[float] = None
    project_remaining_usd: Optional[float] = None
    project_used_percent: Optional[float] = None
    task_count: int = 0
    record_count: int = 0
    task_spent: dict[str, float] = Field(default_factory=dict)
    updated_at: Optional[str] = None
    enabled: bool = True


class BudgetReportResponse(BaseModel):
    status: BudgetStatus
    task_spending: list[dict] = Field(default_factory=list)


class AgentStatus(BaseModel):
    agent: str
    available: bool
    last_invocation: Optional[str] = None
    total_invocations: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0


class AuditEntry(BaseModel):
    id: str
    agent: str
    task_id: str
    session_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    prompt_length: Optional[int] = None
    command_args: list[str] = Field(default_factory=list)
    exit_code: Optional[int] = None
    status: str = "pending"
    duration_seconds: Optional[float] = None
    output_length: Optional[int] = None
    error_length: Optional[int] = None
    parsed_output_type: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class AuditResponse(BaseModel):
    entries: list[AuditEntry] = Field(default_factory=list)
    total: int = 0


class AuditStatistics(BaseModel):
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    by_agent: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str
    project_name: Optional[str] = None
    context: Optional[dict] = None


class CommandRequest(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    project_name: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    streaming: bool = False


class CommandResponse(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None


# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_name: str):
        await websocket.accept()
        if project_name not in self.active_connections:
            self.active_connections[project_name] = []
        self.active_connections[project_name].append(websocket)
        logger.info(f"WebSocket connected for project: {project_name}")

    def disconnect(self, websocket: WebSocket, project_name: str):
        if project_name in self.active_connections:
            if websocket in self.active_connections[project_name]:
                self.active_connections[project_name].remove(websocket)
                logger.info(f"WebSocket disconnected for project: {project_name}")

    async def broadcast(self, project_name: str, message: dict):
        if project_name in self.active_connections:
            for connection in self.active_connections[project_name]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


# Progress Callback
class WebSocketProgressCallback:
    def __init__(self, project_name: str, manager: ConnectionManager):
        self.project_name = project_name
        self.manager = manager

    def on_node_start(self, node_name: str, state: dict):
        asyncio.create_task(self.manager.broadcast(self.project_name, {
            "type": "state_change", # Use state_change to map to frontend expectation
            "data": {"node": node_name, "status": "active"}
        }))
        # Also emit specific node event
        asyncio.create_task(self.manager.broadcast(self.project_name, {
            "type": "node_start",
            "data": {"node": node_name, "input": state}
        }))

    def on_node_end(self, node_name: str, state: dict):
        asyncio.create_task(self.manager.broadcast(self.project_name, {
            "type": "node_end",
            "data": {"node": node_name, "output": state}
        }))

    def on_task_start(self, task_id: str, task_title: str):
        asyncio.create_task(self.manager.broadcast(self.project_name, {
            "type": "action",
            "data": {"type": "task_start", "task_id": task_id, "title": task_title}
        }))

    def on_task_complete(self, task_id: str, success: bool):
        asyncio.create_task(self.manager.broadcast(self.project_name, {
            "type": "action",
            "data": {"type": "task_complete", "task_id": task_id, "success": success}
        }))


# Global project manager instance
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager(CONDUCTOR_ROOT)
    return _project_manager


def get_project_dir(project_name: str) -> Path:
    """Get validated project directory or raise 404."""
    pm = get_project_manager()
    project_dir = pm.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    return project_dir


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("Starting Orchestrator Microservice")
    logger.info(f"Conductor root: {CONDUCTOR_ROOT}")
    logger.info(f"Projects directory: {PROJECTS_PATH}")
    yield
    logger.info("Shutting down Orchestrator Microservice")


# Create FastAPI app
app = FastAPI(
    title="Orchestrator Microservice",
    description="REST API for Python orchestrator (ProjectManager, Orchestrator)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "orchestrator-api",
        "timestamp": datetime.now().isoformat(),
    }


# ==================== WebSocket ====================

@app.websocket("/projects/{project_name}/events")
async def websocket_endpoint(websocket: WebSocket, project_name: str):
    await manager.connect(websocket, project_name)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_name)


# ==================== Project Routes ====================


@app.get("/projects", response_model=list[ProjectSummary])
async def list_projects() -> list[ProjectSummary]:
    """List all projects."""
    pm = get_project_manager()
    projects = pm.list_projects()
    return [ProjectSummary(**p) for p in projects]


@app.get("/projects/{project_name}", response_model=ProjectStatusResponse)
async def get_project(project_name: str) -> ProjectStatusResponse:
    """Get detailed project status."""
    pm = get_project_manager()
    status = pm.get_project_status(project_name)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return ProjectStatusResponse(**status)


@app.post("/projects/{project_name}/init", response_model=InitProjectResponse)
async def init_project(project_name: str) -> InitProjectResponse:
    """Initialize a new project."""
    pm = get_project_manager()
    result = pm.init_project(project_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to initialize"))
    return InitProjectResponse(**result)


@app.delete("/projects/{project_name}")
async def delete_project(
    project_name: str,
    remove_source: bool = Query(default=False),
) -> dict:
    """Delete project (workflow state only by default)."""
    import shutil

    project_dir = get_project_dir(project_name)

    # Remove workflow state
    workflow_dir = project_dir / ".workflow"
    if workflow_dir.exists():
        shutil.rmtree(workflow_dir)

    config_file = project_dir / ".project-config.json"
    if config_file.exists():
        config_file.unlink()

    if remove_source:
        shutil.rmtree(project_dir)
        return {"message": f"Project '{project_name}' and all files deleted"}

    return {"message": f"Project '{project_name}' workflow state deleted"}


# ==================== Workflow Routes ====================


@app.get("/projects/{project_name}/workflow/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(project_name: str) -> WorkflowStatusResponse:
    """Get workflow status."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)

    try:
        status = await orchestrator.status_langgraph()
        return WorkflowStatusResponse(
            mode=status.get("mode", "langgraph"),
            status=WorkflowStatus(status.get("status", "not_started")),
            project=status.get("project"),
            current_phase=status.get("current_phase"),
            phase_status=status.get("phase_status", {}),
            pending_interrupt=status.get("pending_interrupt"),
            message=status.get("message"),
        )
    except Exception as e:
        basic_status = orchestrator.status()
        return WorkflowStatusResponse(
            mode="langgraph",
            status=WorkflowStatus.NOT_STARTED
            if not basic_status.get("current_phase")
            else WorkflowStatus.IN_PROGRESS,
            project=basic_status.get("project"),
            current_phase=basic_status.get("current_phase"),
            phase_status=basic_status.get("phase_statuses", {}),
            message=str(e),
        )


@app.get("/projects/{project_name}/workflow/health", response_model=WorkflowHealthResponse)
async def get_workflow_health(project_name: str) -> WorkflowHealthResponse:
    """Get workflow health status."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)
    health = orchestrator.health_check()
    return WorkflowHealthResponse(**health)


@app.get("/projects/{project_name}/workflow/graph")
async def get_workflow_graph(project_name: str) -> dict:
    """Get workflow graph definition."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)
    return orchestrator.get_workflow_definition()


@app.post("/projects/{project_name}/workflow/start", response_model=WorkflowStartResponse)
async def start_workflow(
    project_name: str,
    request: WorkflowStartRequest,
    background_tasks: BackgroundTasks,
) -> WorkflowStartResponse:
    """Start the workflow."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)

    # Check prerequisites
    prereq_ok, prereq_errors = orchestrator.check_prerequisites()
    if not prereq_ok:
        raise HTTPException(
            status_code=400,
            detail={"error": "Prerequisites not met", "details": prereq_errors},
        )

    # Run workflow in background
    async def run_workflow():
        try:
            callback = WebSocketProgressCallback(project_name, manager)
            await orchestrator.run_langgraph(
                start_phase=request.start_phase,
                end_phase=request.end_phase,
                skip_validation=request.skip_validation,
                autonomous=request.autonomous,
                use_rich_display=False,
                progress_callback=callback,
            )
        except Exception as e:
            logger.error(f"Workflow error: {e}")
            await manager.broadcast(project_name, {
                "type": "workflow_error",
                "data": {"error": str(e)}
            })

    background_tasks.add_task(run_workflow)

    return WorkflowStartResponse(
        success=True,
        mode="langgraph",
        message="Workflow started in background",
    )


@app.post("/projects/{project_name}/workflow/resume", response_model=WorkflowStartResponse)
async def resume_workflow(
    project_name: str,
    autonomous: bool = False,
    background_tasks: BackgroundTasks = None,
) -> WorkflowStartResponse:
    """Resume a paused workflow."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)

    async def run_resume():
        try:
            callback = WebSocketProgressCallback(project_name, manager)
            await orchestrator.resume_langgraph(
                autonomous=autonomous,
                use_rich_display=False,
                progress_callback=callback,
            )
        except Exception as e:
            logger.error(f"Resume error: {e}")
            await manager.broadcast(project_name, {
                "type": "workflow_error",
                "data": {"error": str(e)}
            })

    background_tasks.add_task(run_resume)

    return WorkflowStartResponse(
        success=True,
        mode="langgraph",
        message="Workflow resumed in background",
    )


@app.post("/projects/{project_name}/workflow/rollback/{phase}")
async def rollback_workflow(project_name: str, phase: int) -> dict:
    """Rollback workflow to a previous phase."""
    if phase < 1 or phase > 5:
        raise HTTPException(status_code=400, detail="Phase must be between 1 and 5")

    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)
    result = orchestrator.rollback_to_phase(phase)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rollback failed"))

    return result


@app.post("/projects/{project_name}/workflow/reset")
async def reset_workflow(project_name: str) -> dict:
    """Reset workflow state."""
    project_dir = get_project_dir(project_name)
    orchestrator = Orchestrator(project_dir, console_output=False)
    orchestrator.reset()
    return {"message": "Workflow reset"}


# ==================== Tasks Routes ====================


@app.get("/projects/{project_name}/tasks", response_model=TaskListResponse)
async def get_tasks(project_name: str) -> TaskListResponse:
    """Get tasks for a project."""
    project_dir = get_project_dir(project_name)

    # Read task breakdown from workflow state
    state_file = project_dir / ".workflow" / "state.json"
    tasks: list[TaskInfo] = []

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            task_breakdown = state.get("task_breakdown", {})
            raw_tasks = task_breakdown.get("tasks", [])

            for t in raw_tasks:
                tasks.append(
                    TaskInfo(
                        id=t.get("id", ""),
                        title=t.get("title", ""),
                        description=t.get("description"),
                        status=TaskStatus(t.get("status", "pending")),
                        priority=t.get("priority", 0),
                        dependencies=t.get("dependencies", []),
                        files_to_create=t.get("files_to_create", []),
                        files_to_modify=t.get("files_to_modify", []),
                        acceptance_criteria=t.get("acceptance_criteria", []),
                        complexity_score=t.get("complexity_score"),
                        created_at=t.get("created_at"),
                        completed_at=t.get("completed_at"),
                        error=t.get("error"),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            pass

    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

    return TaskListResponse(
        tasks=tasks,
        total=len(tasks),
        completed=completed,
        in_progress=in_progress,
        pending=pending,
        failed=failed,
    )


@app.get("/projects/{project_name}/tasks/{task_id}", response_model=TaskInfo)
async def get_task(project_name: str, task_id: str) -> TaskInfo:
    """Get details for a specific task."""
    project_dir = get_project_dir(project_name)
    state_file = project_dir / ".workflow" / "state.json"
    
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            task_breakdown = state.get("task_breakdown", {})
            raw_tasks = task_breakdown.get("tasks", [])
            
            for t in raw_tasks:
                if t.get("id") == task_id:
                    return TaskInfo(
                        id=t.get("id", ""),
                        title=t.get("title", ""),
                        description=t.get("description"),
                        status=TaskStatus(t.get("status", "pending")),
                        priority=t.get("priority", 0),
                        dependencies=t.get("dependencies", []),
                        files_to_create=t.get("files_to_create", []),
                        files_to_modify=t.get("files_to_modify", []),
                        acceptance_criteria=t.get("acceptance_criteria", []),
                        complexity_score=t.get("complexity_score"),
                        created_at=t.get("created_at"),
                        completed_at=t.get("completed_at"),
                        error=t.get("error"),
                    )
        except (json.JSONDecodeError, KeyError):
            pass
            
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")


@app.get("/projects/{project_name}/tasks/{task_id}/history", response_model=AuditResponse)
async def get_task_history(
    project_name: str, 
    task_id: str,
    limit: int = Query(default=100, ge=1, le=1000)
) -> AuditResponse:
    """Get audit history for a task."""
    project_dir = get_project_dir(project_name)
    audit_storage = get_audit_storage(project_dir)
    entries = audit_storage.get_task_history(task_id, limit=limit)
    
    return AuditResponse(
        entries=[
            AuditEntry(
                id=entry.id,
                agent=entry.agent,
                task_id=entry.task_id,
                session_id=entry.session_id,
                prompt_hash=entry.prompt_hash,
                prompt_length=entry.prompt_length,
                command_args=entry.command_args or [],
                exit_code=entry.exit_code,
                status=entry.status,
                duration_seconds=entry.duration_seconds,
                output_length=entry.output_length,
                error_length=entry.error_length,
                parsed_output_type=entry.parsed_output_type,
                cost_usd=entry.cost_usd,
                model=entry.model,
                metadata=entry.metadata or {},
                timestamp=entry.timestamp,
            ) for entry in entries
        ],
        total=len(entries)
    )


# ==================== Budget Routes ====================


@app.get("/projects/{project_name}/budget", response_model=BudgetStatus)
async def get_budget(project_name: str) -> BudgetStatus:
    """Get budget status for a project."""
    project_dir = get_project_dir(project_name)
    bm = BudgetManager(project_dir)
    return BudgetStatus(**bm.get_budget_status())


@app.get("/projects/{project_name}/budget/report", response_model=BudgetReportResponse)
async def get_budget_report(project_name: str) -> BudgetReportResponse:
    """Get detailed budget report."""
    project_dir = get_project_dir(project_name)
    bm = BudgetManager(project_dir)
    return BudgetReportResponse(
        status=BudgetStatus(**bm.get_budget_status()),
        task_spending=bm.get_task_spending_report()
    )


# ==================== Audit Routes ====================


@app.get("/projects/{project_name}/audit", response_model=AuditResponse)
async def get_audit(
    project_name: str,
    agent: Optional[str] = None,
    task_id: Optional[str] = None,
    status: Optional[str] = None,
    since_hours: Optional[int] = None,
    limit: int = 100
) -> AuditResponse:
    """Get audit entries."""
    project_dir = get_project_dir(project_name)
    audit_storage = get_audit_storage(project_dir)
    
    since = None
    if since_hours:
        since = datetime.now() - timedelta(hours=since_hours)
        
    entries = audit_storage.query(
        agent=agent,
        task_id=task_id,
        status=status,
        since=since,
        limit=limit
    )
    
    return AuditResponse(
        entries=[
            AuditEntry(
                id=entry.id,
                agent=entry.agent,
                task_id=entry.task_id,
                session_id=entry.session_id,
                prompt_hash=entry.prompt_hash,
                prompt_length=entry.prompt_length,
                command_args=entry.command_args or [],
                exit_code=entry.exit_code,
                status=entry.status,
                duration_seconds=entry.duration_seconds,
                output_length=entry.output_length,
                error_length=entry.error_length,
                parsed_output_type=entry.parsed_output_type,
                cost_usd=entry.cost_usd,
                model=entry.model,
                metadata=entry.metadata or {},
                timestamp=entry.timestamp,
            ) for entry in entries
        ],
        total=len(entries)
    )


@app.get("/projects/{project_name}/audit/statistics", response_model=AuditStatistics)
async def get_audit_statistics(
    project_name: str,
    since_hours: Optional[int] = None
) -> AuditStatistics:
    """Get audit statistics."""
    project_dir = get_project_dir(project_name)
    audit_storage = get_audit_storage(project_dir)
    
    since = None
    if since_hours:
        since = datetime.now() - timedelta(hours=since_hours)
        
    stats = audit_storage.get_statistics(since=since)
    
    return AuditStatistics(
        total=stats.total,
        success_count=stats.success_count,
        failed_count=stats.failed_count,
        timeout_count=stats.timeout_count,
        success_rate=stats.success_rate,
        total_cost_usd=stats.total_cost_usd,
        total_duration_seconds=stats.total_duration_seconds,
        avg_duration_seconds=stats.avg_duration_seconds,
        by_agent=stats.by_agent,
        by_status=stats.by_status
    )


# ==================== Agents Routes ====================


@app.get("/projects/{project_name}/agents", response_model=list[AgentStatus])
async def get_agents(project_name: str) -> list[AgentStatus]:
    """Get agent statuses for a project."""
    project_dir = get_project_dir(project_name)
    audit_storage = get_audit_storage(project_dir)
    
    stats = audit_storage.get_statistics()
    
    agents = []
    for agent_name in ["claude", "cursor", "gemini"]:
        # Check availability
        # We need to instantiate agents to check availability, but that might be heavy
        # For now, we assume they are available if configured
        available = True 
        
        agent_invocations = stats.by_agent.get(agent_name, 0)
        
        # Calculate specific agent stats (this is a bit inefficient without DB group by, but file-based is limited)
        # For MVP we use aggregate stats or simplified view
        
        agents.append(
            AgentStatus(
                agent=agent_name,
                available=available,
                total_invocations=agent_invocations,
                success_rate=0.0, # Placeholder
                avg_duration_seconds=0.0, # Placeholder
                total_cost_usd=0.0 # Placeholder
            )
        )

    return agents


# ==================== Chat Routes ====================


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Execute a chat request (single shot)."""
    cwd = CONDUCTOR_ROOT
    if request.project_name:
        cwd = get_project_dir(request.project_name)
        
    cmd = ["claude", "-p", request.message, "--output-format", "text"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300
        )
        return ChatResponse(
            message=result.stdout if result.returncode == 0 else result.stderr,
            streaming=False
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/command", response_model=CommandResponse)
async def execute_command(request: CommandRequest) -> CommandResponse:
    """Execute a Claude command."""
    cwd = CONDUCTOR_ROOT
    if request.project_name:
        cwd = get_project_dir(request.project_name)
        
    command_prompt = f"/{request.command}"
    if request.args:
        command_prompt += " " + " ".join(request.args)
        
    cmd = ["claude", "-p", command_prompt, "--output-format", "text"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300
        )
        return CommandResponse(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None
        )
    except Exception as e:
        return CommandResponse(success=False, error=str(e))


# ==================== Main ====================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("ORCHESTRATOR_API_PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")