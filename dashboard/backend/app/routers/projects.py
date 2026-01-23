"""Project management API routes."""


# Import orchestrator modules
import sys

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_settings
from ..deps import get_project_manager
from ..models import ErrorResponse, FolderInfo, ProjectInitResponse, ProjectStatus, ProjectSummary

settings = get_settings()
sys.path.insert(0, str(settings.conductor_root))
from orchestrator.project_manager import ProjectManager

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=list[ProjectSummary],
    summary="List all projects",
    description="Get a list of all initialized projects in the projects directory.",
)
async def list_projects(
    project_manager: ProjectManager = Depends(get_project_manager),
) -> list[ProjectSummary]:
    """List all projects."""
    projects = project_manager.list_projects()
    return [ProjectSummary(**p) for p in projects]


@router.get(
    "/{project_name}",
    response_model=ProjectStatus,
    summary="Get project status",
    description="Get detailed status for a specific project.",
    responses={404: {"model": ErrorResponse}},
)
async def get_project(
    project_name: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectStatus:
    """Get detailed project status."""
    status = project_manager.get_project_status(project_name)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return ProjectStatus(**status)


@router.post(
    "/{project_name}/init",
    response_model=ProjectInitResponse,
    summary="Initialize a project",
    description="Initialize a new project with the basic directory structure.",
    responses={400: {"model": ErrorResponse}},
)
async def init_project(
    project_name: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectInitResponse:
    """Initialize a new project."""
    result = project_manager.init_project(project_name)
    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to initialize project")
        )
    return ProjectInitResponse(**result)


@router.get(
    "/workspace/folders",
    response_model=list[FolderInfo],
    summary="List workspace folders",
    description="Get a list of all folders in the workspace that could be projects.",
)
async def list_workspace_folders(
    project_manager: ProjectManager = Depends(get_project_manager),
) -> list[FolderInfo]:
    """List all folders in the workspace."""
    settings = get_settings()
    workspace_path = settings.projects_path

    if not workspace_path.exists():
        return []

    folders = []
    for item in sorted(workspace_path.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            folder_info = FolderInfo(
                name=item.name,
                path=str(item),
                is_project=(item / ".project-config.json").exists(),
                has_workflow=(item / ".workflow").exists(),
                has_product_md=(item / "PRODUCT.md").exists()
                or (item / "Docs" / "PRODUCT.md").exists(),
            )
            folders.append(folder_info)

    return folders


@router.delete(
    "/{project_name}",
    summary="Delete a project",
    description="Delete a project (removes workflow state only, not source files).",
    responses={404: {"model": ErrorResponse}},
)
async def delete_project(
    project_name: str,
    remove_source: bool = Query(default=False, description="Also remove source files"),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Delete a project."""
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    import shutil

    # Remove workflow state
    workflow_dir = project_dir / ".workflow"
    if workflow_dir.exists():
        shutil.rmtree(workflow_dir)

    config_file = project_dir / ".project-config.json"
    if config_file.exists():
        config_file.unlink()

    if remove_source:
        # Remove entire project directory
        shutil.rmtree(project_dir)
        return {"message": f"Project '{project_name}' and all files deleted"}

    return {"message": f"Project '{project_name}' workflow state deleted"}
