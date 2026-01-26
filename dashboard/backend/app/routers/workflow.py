"""Workflow management API routes."""


# Import orchestrator modules
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..deps import get_project_dir
from ..models import (
    ErrorResponse,
    ResumeRequest,
    WorkflowHealthResponse,
    WorkflowRollbackResponse,
    WorkflowStartRequest,
    WorkflowStartResponse,
    WorkflowStatus,
    WorkflowStatusResponse,
)
from ..services import get_event_bridge
from ..websocket import get_connection_manager

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.events import create_dashboard_callback
from orchestrator.orchestrator import Orchestrator

router = APIRouter(prefix="/projects/{project_name}", tags=["workflow"])


@router.get(
    "/status",
    response_model=WorkflowStatusResponse,
    summary="Get workflow status",
    description="Get the current status of the workflow for a project.",
    responses={404: {"model": ErrorResponse}},
)
async def get_workflow_status(
    project_name: str,
    project_dir: Path = Depends(get_project_dir),
) -> WorkflowStatusResponse:
    """Get workflow status."""
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
        # Fall back to basic status
        basic_status = await orchestrator.status_async()
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


@router.get(
    "/health",
    response_model=WorkflowHealthResponse,
    summary="Get workflow health",
    description="Get health check status for the workflow and agents.",
    responses={404: {"model": ErrorResponse}},
)
async def get_workflow_health(
    project_dir: Path = Depends(get_project_dir),
) -> WorkflowHealthResponse:
    """Get workflow health status."""
    orchestrator = Orchestrator(project_dir, console_output=False)
    health = await orchestrator.health_check_async()
    return WorkflowHealthResponse(**health)


@router.get(
    "/graph",
    summary="Get workflow graph definition",
    description="Get the nodes and edges of the workflow graph.",
)
async def get_workflow_graph(
    project_dir: Path = Depends(get_project_dir),
) -> dict:
    """Get workflow graph definition."""
    orchestrator = Orchestrator(project_dir, console_output=False)

    # Get current status to pre-populate graph
    try:
        status = await orchestrator.status_langgraph()
    except Exception:
        status = None

    return await orchestrator.get_workflow_definition(status_dict=status)


@router.post(
    "/start",
    response_model=WorkflowStartResponse,
    summary="Start workflow",
    description="Start the workflow for a project.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def start_workflow(
    project_name: str,
    request: WorkflowStartRequest,
    project_dir: Path = Depends(get_project_dir),
) -> WorkflowStartResponse:
    """Start the workflow."""
    import asyncio

    orchestrator = Orchestrator(project_dir, console_output=False)

    # Check prerequisites
    prereq_ok, prereq_errors = orchestrator.check_prerequisites()
    if not prereq_ok:
        raise HTTPException(
            status_code=400,
            detail={"error": "Prerequisites not met", "details": prereq_errors},
        )

    # Start workflow as a proper async task in the SAME event loop
    # This is critical for connection pool sharing - BackgroundTasks can
    # run in a different context that breaks async connection management
    async def run_workflow():
        manager = get_connection_manager()

        # Use DashboardCallback for event persistence via SurrealDB
        # Events flow: orchestrator -> SurrealDB -> EventBridge -> WebSocket
        callback = create_dashboard_callback(
            project_name=project_name,
            enabled=True,
            current_phase=request.start_phase,
        )

        # Ensure event bridge is subscribed to this project's events
        bridge = get_event_bridge()
        await bridge.subscribe_project(project_name)

        # Emit workflow start event
        callback.on_workflow_start(
            mode="langgraph",
            start_phase=request.start_phase,
            autonomous=request.autonomous,
        )

        try:
            result = await orchestrator.run_langgraph(
                start_phase=request.start_phase,
                end_phase=request.end_phase,
                skip_validation=request.skip_validation,
                autonomous=request.autonomous,
                use_rich_display=False,
                progress_callback=callback,
            )

            # Emit workflow complete event
            callback.on_workflow_complete(
                success=result.get("success", False),
                final_phase=result.get("current_phase", 5),
                summary=result.get("results"),
            )

            # Also broadcast directly for immediate feedback
            await manager.broadcast_to_project(
                project_name,
                "workflow_complete",
                {"success": result.get("success", False), "results": result},
            )

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Workflow failed: {e}", exc_info=True)

            # Emit error event
            callback.on_error(
                error_message=str(e),
                error_type="workflow_error",
                recoverable=False,
            )

            # Also broadcast directly
            await manager.broadcast_to_project(
                project_name,
                "workflow_error",
                {"error": str(e)},
            )

        finally:
            # Flush any pending events
            await callback.emitter.close()

    # Use asyncio.create_task() to run in the same event loop as the API
    # This ensures the connection pool is shared and checkpoints are saved correctly
    asyncio.create_task(run_workflow())

    return WorkflowStartResponse(
        success=True,
        mode="langgraph",
        message="Workflow started in background",
    )


@router.post(
    "/resume",
    response_model=WorkflowStartResponse,
    summary="Resume workflow",
    description="Resume a paused workflow from the last checkpoint.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def resume_workflow(
    project_name: str,
    request: Optional[ResumeRequest] = None,
    autonomous: bool = False,  # Keep query param for backward compatibility
    project_dir: Path = Depends(get_project_dir),
) -> WorkflowStartResponse:
    """Resume the workflow."""
    import asyncio

    orchestrator = Orchestrator(project_dir, console_output=False)

    # Resolve autonomous flag: prefer request body if present, else query param
    is_autonomous = request.autonomous if request else autonomous
    human_response = request.human_response if request else None

    # Resume workflow as proper async task in the SAME event loop
    async def run_resume():
        manager = get_connection_manager()

        # Use DashboardCallback for event persistence via SurrealDB
        callback = create_dashboard_callback(
            project_name=project_name,
            enabled=True,
        )

        # Ensure event bridge is subscribed
        bridge = get_event_bridge()
        await bridge.subscribe_project(project_name)

        try:
            result = await orchestrator.resume_langgraph(
                autonomous=is_autonomous,
                human_response=human_response,
                use_rich_display=False,
                progress_callback=callback,
            )

            # Emit workflow complete event
            callback.on_workflow_complete(
                success=result.get("success", False),
                final_phase=result.get("current_phase", 5),
                summary=result.get("results"),
            )

            # Also broadcast directly
            await manager.broadcast_to_project(
                project_name,
                "workflow_complete",
                {"success": result.get("success", False), "results": result},
            )

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Workflow resume failed: {e}", exc_info=True)

            # Emit error event
            callback.on_error(
                error_message=str(e),
                error_type="workflow_error",
                recoverable=False,
            )

            # Also broadcast directly
            await manager.broadcast_to_project(
                project_name,
                "workflow_error",
                {"error": str(e)},
            )

        finally:
            await callback.emitter.close()

    # Use asyncio.create_task() to run in the same event loop
    asyncio.create_task(run_resume())

    return WorkflowStartResponse(
        success=True,
        mode="langgraph",
        message="Workflow resumed in background",
    )


@router.post(
    "/pause",
    summary="Pause workflow",
    description="Request workflow pause at next checkpoint.",
    responses={404: {"model": ErrorResponse}},
)
async def pause_workflow(
    project_name: str,
    reason: Optional[str] = None,
    project_dir: Path = Depends(get_project_dir),
) -> dict:
    """Pause the workflow.

    Sets the pause_requested flag in workflow state. The workflow will
    pause at the next checkpoint (pause_check node) using LangGraph's
    interrupt() mechanism.
    """
    from orchestrator.db.repositories.workflow import WorkflowRepository

    # Update workflow state to request pause
    repo = WorkflowRepository(project_name)
    await repo.update_state(
        pause_requested=True,
        pause_reason=reason,
        paused_at_timestamp=datetime.now().isoformat(),
    )

    # Also broadcast intent to connected clients
    manager = get_connection_manager()
    await manager.broadcast_to_project(
        project_name,
        "pause_requested",
        {
            "message": "Pause requested - workflow will pause at next checkpoint",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        },
    )

    return {
        "message": "Pause requested - workflow will pause at next checkpoint",
        "paused": False,  # Not yet paused, just requested
        "reason": reason,
    }


@router.post(
    "/rollback/{phase}",
    response_model=WorkflowRollbackResponse,
    summary="Rollback workflow",
    description="Rollback the workflow to a previous phase.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def rollback_workflow(
    phase: int,
    project_dir: Path = Depends(get_project_dir),
) -> WorkflowRollbackResponse:
    """Rollback workflow to a previous phase."""
    if phase < 1 or phase > 5:
        raise HTTPException(status_code=400, detail="Phase must be between 1 and 5")

    orchestrator = Orchestrator(project_dir, console_output=False)
    result = orchestrator.rollback_to_phase(phase)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rollback failed"))

    return WorkflowRollbackResponse(**result)


@router.post(
    "/reset",
    summary="Reset workflow",
    description="Reset the workflow state completely.",
    responses={404: {"model": ErrorResponse}},
)
async def reset_workflow(
    project_dir: Path = Depends(get_project_dir),
) -> dict:
    """Reset workflow state."""
    orchestrator = Orchestrator(project_dir, console_output=False)
    orchestrator.reset()
    return {"message": "Workflow reset"}
