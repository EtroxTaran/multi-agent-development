"""Agent management API routes."""

# Import orchestrator modules
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..config import get_settings
from ..deps import get_audit_adapter, get_project_dir
from ..models import (
    AgentStatus,
    AgentStatusResponse,
    AgentType,
    AuditEntry,
    AuditResponse,
    AuditStatistics,
    ErrorResponse,
    SessionInfo,
    SessionListResponse,
)

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.storage.audit_adapter import AuditStorageAdapter

router = APIRouter(prefix="/projects/{project_name}", tags=["agents"])


@router.get(
    "/agents",
    response_model=AgentStatusResponse,
    summary="Get agent statuses",
    description="Get status information for all agents.",
    responses={404: {"model": ErrorResponse}},
)
async def get_agents_status(
    project_dir: Path = Depends(get_project_dir),
    audit_adapter: AuditStorageAdapter = Depends(get_audit_adapter),
) -> AgentStatusResponse:
    """Get status for all agents."""
    # Get statistics from audit
    stats = audit_adapter.get_statistics()

    agents = []
    for agent_type in AgentType:
        agent_name = agent_type.value
        agent_stats = stats.by_agent.get(agent_name, 0)

        # Get recent entries for this agent
        recent_entries = audit_adapter.query(agent=agent_name, limit=1)
        last_invocation = None
        if recent_entries:
            last_invocation = (
                recent_entries[0].timestamp.isoformat() if recent_entries[0].timestamp else None
            )

        # Calculate agent-specific metrics
        agent_entries = audit_adapter.query(agent=agent_name, limit=1000)
        total = len(agent_entries)
        success = sum(1 for e in agent_entries if e.status == "success")
        total_duration = sum(e.duration_seconds or 0 for e in agent_entries)
        total_cost = sum(e.cost_usd or 0 for e in agent_entries)

        # Check if agent is available
        from orchestrator.agents import ClaudeAgent, CursorAgent, GeminiAgent

        if agent_name == "claude":
            available = ClaudeAgent(project_dir).check_available()
        elif agent_name == "cursor":
            available = CursorAgent(project_dir).check_available()
        elif agent_name == "gemini":
            available = GeminiAgent(project_dir).check_available()
        else:
            available = False

        agents.append(
            AgentStatus(
                agent=agent_type,
                available=available,
                last_invocation=last_invocation,
                total_invocations=total,
                success_rate=success / total if total > 0 else 0.0,
                avg_duration_seconds=total_duration / total if total > 0 else 0.0,
                total_cost_usd=total_cost,
            )
        )

    return AgentStatusResponse(agents=agents)


@router.get(
    "/audit",
    response_model=AuditResponse,
    summary="Get audit entries",
    description="Query audit entries with optional filters.",
    responses={404: {"model": ErrorResponse}},
)
async def get_audit_entries(
    agent: Optional[str] = Query(default=None, description="Filter by agent"),
    task_id: Optional[str] = Query(default=None, description="Filter by task ID"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    since_hours: Optional[int] = Query(default=None, description="Entries from last N hours"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum entries"),
    audit_adapter: AuditStorageAdapter = Depends(get_audit_adapter),
) -> AuditResponse:
    """Get audit entries."""
    since = None
    if since_hours:
        since = datetime.now() - timedelta(hours=since_hours)

    entries = audit_adapter.query(
        agent=agent,
        task_id=task_id,
        status=status,
        since=since,
        limit=limit,
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
            )
            for entry in entries
        ],
        total=len(entries),
    )


@router.get(
    "/audit/statistics",
    response_model=AuditStatistics,
    summary="Get audit statistics",
    description="Get aggregated statistics from audit entries.",
    responses={404: {"model": ErrorResponse}},
)
async def get_audit_statistics(
    since_hours: Optional[int] = Query(default=None, description="Stats from last N hours"),
    audit_adapter: AuditStorageAdapter = Depends(get_audit_adapter),
) -> AuditStatistics:
    """Get audit statistics."""
    since = None
    if since_hours:
        since = datetime.now() - timedelta(hours=since_hours)

    stats = audit_adapter.get_statistics(since=since)

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
        by_status=stats.by_status,
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="Get active sessions",
    description="Get list of active agent sessions.",
    responses={404: {"model": ErrorResponse}},
)
async def get_sessions(
    project_dir: Path = Depends(get_project_dir),
) -> SessionListResponse:
    """Get active sessions."""
    import json

    sessions = []
    sessions_dir = project_dir / ".workflow" / "sessions"

    if sessions_dir.exists():
        for session_file in sessions_dir.glob("*.json"):
            try:
                session_data = json.loads(session_file.read_text())
                sessions.append(
                    SessionInfo(
                        session_id=session_data.get("session_id", session_file.stem),
                        task_id=session_data.get("task_id", ""),
                        agent=session_data.get("agent", "claude"),
                        created_at=session_data.get("created_at", ""),
                        last_active=session_data.get("last_active"),
                        iteration=session_data.get("iteration", 0),
                        active=session_data.get("active", True),
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue

    return SessionListResponse(sessions=sessions)
