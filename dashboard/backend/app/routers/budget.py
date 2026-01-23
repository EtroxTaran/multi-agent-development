"""Budget management API routes."""

# Import orchestrator modules
import sys
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_settings
from ..deps import get_budget_manager
from ..models import BudgetReportResponse, BudgetStatus, ErrorResponse, TaskSpending

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.agents.budget import BudgetManager

router = APIRouter(prefix="/projects/{project_name}/budget", tags=["budget"])


@router.get(
    "",
    response_model=BudgetStatus,
    summary="Get budget status",
    description="Get the current budget status for a project.",
    responses={404: {"model": ErrorResponse}},
)
async def get_budget_status(
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> BudgetStatus:
    """Get budget status."""
    status = budget_manager.get_budget_status()
    return BudgetStatus(**status)


@router.get(
    "/report",
    response_model=BudgetReportResponse,
    summary="Get budget report",
    description="Get detailed spending report by task.",
    responses={404: {"model": ErrorResponse}},
)
async def get_budget_report(
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> BudgetReportResponse:
    """Get detailed budget report."""
    status = budget_manager.get_budget_status()
    task_report = budget_manager.get_task_spending_report()

    return BudgetReportResponse(
        status=BudgetStatus(**status),
        task_spending=[TaskSpending(**t) for t in task_report],
    )


@router.post(
    "/limit/project",
    summary="Set project budget limit",
    description="Set the total budget limit for the project.",
    responses={404: {"model": ErrorResponse}},
)
async def set_project_budget(
    limit_usd: Optional[float] = Query(
        default=None, description="Budget limit in USD (null for unlimited)"
    ),
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> dict:
    """Set project budget limit."""
    budget_manager.set_project_budget(limit_usd)
    return {
        "message": f"Project budget set to ${limit_usd:.2f}"
        if limit_usd
        else "Project budget set to unlimited"
    }


@router.post(
    "/limit/task/{task_id}",
    summary="Set task budget limit",
    description="Set the budget limit for a specific task.",
    responses={404: {"model": ErrorResponse}},
)
async def set_task_budget(
    task_id: str,
    limit_usd: Optional[float] = Query(
        default=None, description="Budget limit in USD (null to remove)"
    ),
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> dict:
    """Set task budget limit."""
    budget_manager.set_task_budget(task_id, limit_usd)
    return {
        "message": f"Task {task_id} budget set to ${limit_usd:.2f}"
        if limit_usd
        else f"Task {task_id} budget limit removed"
    }


@router.post(
    "/reset",
    summary="Reset budget",
    description="Reset all spending records (preserves limits).",
    responses={404: {"model": ErrorResponse}},
)
async def reset_budget(
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> dict:
    """Reset all spending records."""
    budget_manager.reset_all()
    return {"message": "Budget spending reset"}


@router.post(
    "/reset/task/{task_id}",
    summary="Reset task spending",
    description="Reset spending for a specific task.",
    responses={404: {"model": ErrorResponse}},
)
async def reset_task_spending(
    task_id: str,
    budget_manager: BudgetManager = Depends(get_budget_manager),
) -> dict:
    """Reset spending for a task."""
    if budget_manager.reset_task_spending(task_id):
        return {"message": f"Spending for task {task_id} reset"}
    raise HTTPException(status_code=404, detail=f"No spending found for task {task_id}")
