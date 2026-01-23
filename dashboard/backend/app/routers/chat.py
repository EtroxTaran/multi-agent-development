"""Chat and Claude integration API routes."""

import asyncio
import json
import subprocess

# Import orchestrator modules
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..deps import get_project_dir, get_project_manager
from ..models import (
    ChatRequest,
    ChatResponse,
    CommandRequest,
    CommandResponse,
    ErrorResponse,
    EscalationResponse,
)
from ..websocket import get_connection_manager

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.project_manager import ProjectManager

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send chat message",
    description="Send a message to Claude and get a response.",
)
async def send_chat_message(
    request: ChatRequest,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ChatResponse:
    """Send a chat message to Claude."""
    # Determine working directory
    if request.project_name:
        project_dir = project_manager.get_project(request.project_name)
        if not project_dir:
            raise HTTPException(
                status_code=404, detail=f"Project '{request.project_name}' not found"
            )
        cwd = str(project_dir)
    else:
        cwd = str(get_settings().conductor_root)

    # Build Claude command
    cmd = ["claude", "-p", request.message, "--output-format", "text"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=get_settings().claude_timeout,
        )
        return ChatResponse(
            message=result.stdout if result.returncode == 0 else result.stderr,
            streaming=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Claude request timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Claude CLI not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/chat/command",
    response_model=CommandResponse,
    summary="Execute Claude command",
    description="Execute a Claude slash command.",
)
async def execute_command(
    request: CommandRequest,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> CommandResponse:
    """Execute a Claude command."""
    # Determine working directory
    if request.project_name:
        project_dir = project_manager.get_project(request.project_name)
        if not project_dir:
            raise HTTPException(
                status_code=404, detail=f"Project '{request.project_name}' not found"
            )
        cwd = str(project_dir)
    else:
        cwd = str(get_settings().conductor_root)

    # Format command as prompt
    command_prompt = f"/{request.command}"
    if request.args:
        command_prompt += " " + " ".join(request.args)

    # Build Claude command
    cmd = ["claude", "-p", command_prompt, "--output-format", "text"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=get_settings().claude_timeout,
        )
        return CommandResponse(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResponse(success=False, error="Command timed out")
    except FileNotFoundError:
        return CommandResponse(success=False, error="Claude CLI not found")
    except Exception as e:
        return CommandResponse(success=False, error=str(e))


@router.websocket("/chat/stream")
async def chat_stream(
    websocket: WebSocket,
    project_name: Optional[str] = None,
):
    """WebSocket endpoint for streaming chat responses."""
    manager = get_connection_manager()
    await manager.connect(websocket)

    project_manager = get_project_manager()

    # Determine working directory
    if project_name:
        project_dir = project_manager.get_project(project_name)
        if not project_dir:
            await websocket.close(code=4004, reason=f"Project '{project_name}' not found")
            return
        cwd = str(project_dir)
    else:
        cwd = str(get_settings().conductor_root)

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            message = message_data.get("message", "")

            if not message:
                continue

            # Build Claude command with streaming output
            cmd = ["claude", "-p", message, "--output-format", "stream-json"]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )

                # Stream output
                async for line in process.stdout:
                    if line:
                        try:
                            chunk = json.loads(line.decode())
                            await manager.send_to_connection(
                                websocket,
                                "chat_chunk",
                                {"content": chunk.get("content", "")},
                            )
                        except json.JSONDecodeError:
                            await manager.send_to_connection(
                                websocket,
                                "chat_chunk",
                                {"content": line.decode()},
                            )

                await process.wait()

                # Send completion
                await manager.send_to_connection(
                    websocket,
                    "chat_complete",
                    {"success": process.returncode == 0},
                )

            except Exception as e:
                await manager.send_to_connection(
                    websocket,
                    "chat_error",
                    {"error": str(e)},
                )

    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@router.get(
    "/projects/{project_name}/feedback/{phase}",
    summary="Get phase feedback",
    description="Get feedback from validation or verification phase.",
    responses={404: {"model": ErrorResponse}},
)
async def get_phase_feedback(
    project_name: str,
    phase: int,
    project_dir: Path = Depends(get_project_dir),
) -> dict:
    """Get feedback for a phase."""
    # Determine phase directory
    if phase == 2:
        phase_name = "validation"
    elif phase == 4:
        phase_name = "verification"
    else:
        raise HTTPException(
            status_code=400, detail="Only phases 2 (validation) and 4 (verification) have feedback"
        )

    phase_dir = project_dir / ".workflow" / "phases" / phase_name
    if not phase_dir.exists():
        raise HTTPException(status_code=404, detail=f"No feedback found for phase {phase}")

    feedback = {}

    # Load Cursor feedback
    cursor_file = (
        phase_dir / "cursor_feedback.json" if phase == 2 else phase_dir / "cursor_review.json"
    )
    if cursor_file.exists():
        try:
            feedback["cursor"] = json.loads(cursor_file.read_text())
        except json.JSONDecodeError:
            pass

    # Load Gemini feedback
    gemini_file = (
        phase_dir / "gemini_feedback.json" if phase == 2 else phase_dir / "gemini_review.json"
    )
    if gemini_file.exists():
        try:
            feedback["gemini"] = json.loads(gemini_file.read_text())
        except json.JSONDecodeError:
            pass

    if not feedback:
        raise HTTPException(status_code=404, detail=f"No feedback files found for phase {phase}")

    return feedback


@router.post(
    "/projects/{project_name}/escalation/respond",
    summary="Respond to escalation",
    description="Provide a response to an escalation question.",
    responses={404: {"model": ErrorResponse}},
)
async def respond_to_escalation(
    project_name: str,
    response: EscalationResponse,
    project_dir: Path = Depends(get_project_dir),
) -> dict:
    """Respond to an escalation question."""
    # Store the response
    escalation_dir = project_dir / ".workflow" / "escalations"
    escalation_dir.mkdir(parents=True, exist_ok=True)

    response_file = escalation_dir / f"{response.question_id}_response.json"
    response_file.write_text(
        json.dumps(
            {
                "question_id": response.question_id,
                "answer": response.answer,
                "additional_context": response.additional_context,
            }
        )
    )

    # Broadcast response to workflow (if connected)
    manager = get_connection_manager()
    await manager.broadcast_to_project(
        project_name,
        "escalation_response",
        {
            "question_id": response.question_id,
            "answer": response.answer,
        },
    )

    return {"message": "Response recorded", "question_id": response.question_id}
