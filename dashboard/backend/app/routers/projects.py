"""Project management API routes."""


# Import orchestrator modules
import sys
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_settings
from ..deps import get_project_manager
from ..models import ErrorResponse, FolderInfo, ProjectInitResponse, ProjectStatus, ProjectSummary
from ..security import DeletionConfirmationManager, get_deletion_manager

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
    description="Delete a project (removes workflow state only, not source files). "
    "For destructive operations (remove_source=true), requires a confirmation token.",
    responses={404: {"model": ErrorResponse}},
)
async def delete_project(
    project_name: str,
    remove_source: bool = Query(default=False, description="Also remove source files"),
    confirmation_token: Optional[str] = Query(
        default=None, description="Confirmation token for destructive deletion"
    ),
    project_manager: ProjectManager = Depends(get_project_manager),
    deletion_manager: DeletionConfirmationManager = Depends(get_deletion_manager),
) -> dict:
    """Delete a project.

    For safe deletion (workflow state only), no confirmation needed.
    For destructive deletion (remove_source=true), a two-step process:
    1. Call without token -> returns token and files to be deleted
    2. Call with token -> performs the deletion
    """
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    import shutil

    # If requesting source removal, require confirmation
    if remove_source:
        if confirmation_token:
            # Verify and consume the token
            confirmation = deletion_manager.verify_and_consume(confirmation_token)
            if not confirmation:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid or expired confirmation token. Request a new one.",
                )
            if confirmation.project_name != project_name:
                raise HTTPException(
                    status_code=400,
                    detail="Confirmation token is for a different project.",
                )

            # Perform the destructive deletion
            shutil.rmtree(project_dir)
            return {
                "message": f"Project '{project_name}' and all files deleted",
                "files_deleted": confirmation.files_to_delete,
            }
        else:
            # Generate confirmation token and return files preview
            confirmation = deletion_manager.create_confirmation(
                project_name=project_name,
                project_dir=project_dir,
                remove_source=True,
            )
            return {
                "requires_confirmation": True,
                "confirmation_token": confirmation.token,
                "expires_in_seconds": 300,
                "files_to_delete": confirmation.files_to_delete,
                "message": "This will permanently delete all project files. "
                "To confirm, call DELETE again with the confirmation_token.",
            }

    # Safe deletion - just remove workflow state
    workflow_dir = project_dir / ".workflow"
    if workflow_dir.exists():
        shutil.rmtree(workflow_dir)

    config_file = project_dir / ".project-config.json"
    if config_file.exists():
        config_file.unlink()

    return {"message": f"Project '{project_name}' workflow state deleted"}


# =============================================================================
# Guardrails Endpoints
# =============================================================================


@router.get(
    "/{project_name}/guardrails",
    summary="List project guardrails",
    description="Get all guardrails applied to a project.",
    responses={404: {"model": ErrorResponse}},
)
async def list_project_guardrails(
    project_name: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> list[dict]:
    """List all guardrails applied to a project."""
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Try to read from database
    try:
        from orchestrator.db.connection import get_connection

        async with get_connection(project_name) as conn:
            results = await conn.query(
                "SELECT * FROM project_guardrails WHERE project_id = $pid",
                {"pid": project_name},
            )
            return results if results else []
    except Exception:
        # Fallback: read from manifest file
        manifest_path = project_dir / ".conductor" / "manifest.json"
        if manifest_path.exists():
            import json

            manifest = json.loads(manifest_path.read_text())
            return manifest.get("items", [])
        return []


@router.post(
    "/{project_name}/guardrails/{item_id}/toggle",
    summary="Toggle guardrail",
    description="Enable or disable a guardrail for a project.",
    responses={404: {"model": ErrorResponse}},
)
async def toggle_guardrail(
    project_name: str,
    item_id: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Toggle a guardrail's enabled status."""
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        from orchestrator.db.connection import get_connection

        async with get_connection(project_name) as conn:
            # Find existing record
            results = await conn.query(
                "SELECT * FROM project_guardrails WHERE project_id = $pid AND item_id = $iid",
                {"pid": project_name, "iid": item_id},
            )

            if not results:
                raise HTTPException(
                    status_code=404, detail=f"Guardrail '{item_id}' not found for project"
                )

            record = results[0]
            new_enabled = not record.get("enabled", True)

            # Update record
            await conn.query(
                "UPDATE project_guardrails SET enabled = $enabled WHERE project_id = $pid AND item_id = $iid",
                {"pid": project_name, "iid": item_id, "enabled": new_enabled},
            )

            return {
                "item_id": item_id,
                "enabled": new_enabled,
                "message": f"Guardrail {'enabled' if new_enabled else 'disabled'}",
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{project_name}/guardrails/{item_id}/promote",
    summary="Promote to global",
    description="Promote a project-specific guardrail to the global collection.",
    responses={404: {"model": ErrorResponse}},
)
async def promote_guardrail(
    project_name: str,
    item_id: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Promote a project-specific guardrail to the global collection."""
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Find the guardrail file in project
    conductor_dir = project_dir / ".conductor"
    if not conductor_dir.exists():
        raise HTTPException(status_code=404, detail="No guardrails directory found in project")

    # Search for the item file and determine type from subdirectory
    item_file = None
    item_subdir = None
    for subdir in ["guardrails", "rules", "skills"]:
        path = conductor_dir / subdir / f"{item_id}.md"
        if path.exists():
            item_file = path
            item_subdir = subdir
            break

    if not item_file:
        raise HTTPException(
            status_code=404, detail=f"Guardrail file '{item_id}' not found in project"
        )

    # Register in global collection
    try:
        from orchestrator.collection.models import CollectionTags, ItemType
        from orchestrator.collection.service import CollectionService

        service = CollectionService()

        # Read file content
        content = item_file.read_text()

        # Parse YAML frontmatter
        metadata = service._parse_file_metadata(item_file)
        if not metadata:
            raise HTTPException(
                status_code=400,
                detail=f"Could not parse metadata from '{item_id}'. Ensure file has YAML frontmatter.",
            )

        # Determine ItemType from subdirectory
        type_map = {
            "guardrails": ItemType.RULE,
            "rules": ItemType.RULE,
            "skills": ItemType.SKILL,
        }
        item_type = type_map.get(item_subdir, ItemType.RULE)

        # Extract tags from metadata
        tags_data = metadata.get("tags", {})
        tags = CollectionTags.from_dict(tags_data)

        # Get name and summary from metadata
        name = metadata.get("name", item_id)
        summary = metadata.get("summary", metadata.get("description", ""))
        category = metadata.get("category", "project-promoted")

        # Create item in global collection
        created_item = await service.create_item(
            name=name,
            item_type=item_type,
            category=category,
            content=content,
            tags=tags,
            summary=summary,
        )

        return {
            "item_id": item_id,
            "global_id": created_item.id,
            "global_path": created_item.file_path,
            "promoted": True,
            "message": f"Guardrail '{item_id}' promoted to global collection as '{created_item.id}'",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{project_name}/apply-recommended",
    summary="Apply recommended guardrails",
    description="Run gap analysis and apply matching collection items to the project.",
    responses={404: {"model": ErrorResponse}},
)
async def apply_recommended_guardrails(
    project_name: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Apply recommended guardrails based on gap analysis."""
    project_dir = project_manager.get_project(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        from orchestrator.collection.gap_analysis import GapAnalysisEngine
        from orchestrator.collection.project_setup import ProjectGuardrailsSetup
        from orchestrator.collection.service import CollectionService

        # Run gap analysis
        collection_service = CollectionService()
        gap_engine = GapAnalysisEngine(collection_service)
        project_setup = ProjectGuardrailsSetup(collection_service)

        analysis = await gap_engine.analyze_project(project_dir, project_name)

        # Apply matching items
        if analysis.matching_items:
            result = await project_setup.apply_guardrails(
                project_path=project_dir,
                items=analysis.matching_items,
                project_id=project_name,
            )

            return {
                "items_applied": len(result.items_applied),
                "files_created": len(result.files_created),
                "cursor_rules_created": len(result.cursor_rules_created),
                "gaps_identified": len(analysis.gaps),
                "technologies_detected": list(analysis.requirements.technologies),
                "features_detected": list(analysis.requirements.features),
            }

        return {
            "items_applied": 0,
            "gaps_identified": len(analysis.gaps),
            "technologies_detected": list(analysis.requirements.technologies),
            "features_detected": list(analysis.requirements.features),
            "message": "No matching collection items found",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
