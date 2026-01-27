"""Collection API endpoints.

Provides CRUD operations for the rules & skills collection,
gap analysis, and copy-to-project functionality.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from orchestrator.collection import (
    CollectionItem,
    CollectionService,
    CollectionTags,
    CopyResult,
    ItemType,
)
from orchestrator.collection.gap_analysis import GapAnalysisEngine
from orchestrator.project_manager import ProjectManager
from pydantic import BaseModel, Field

from ..deps import pagination_params
from ..services import GuardrailsService, get_guardrails_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collection", tags=["collection"])

# Initialize services
collection_service = CollectionService()
gap_engine = GapAnalysisEngine(collection_service)

# Get conductor root for project manager
CONDUCTOR_ROOT = Path(__file__).parent.parent.parent.parent.parent


# ----- Request/Response Models -----


class TagsModel(BaseModel):
    """Tags for a collection item."""

    technology: list[str] = Field(default_factory=list)
    feature: list[str] = Field(default_factory=list)
    priority: str = "medium"


class CollectionItemResponse(BaseModel):
    """Response model for a collection item."""

    id: str
    name: str
    item_type: str
    category: str
    file_path: str
    summary: str
    tags: TagsModel
    version: int
    is_active: bool
    content: Optional[str] = None


class CreateItemRequest(BaseModel):
    """Request to create a new collection item."""

    name: str
    item_type: str  # rule, skill, template
    category: str
    content: str
    tags: TagsModel
    summary: str = ""


class UpdateItemRequest(BaseModel):
    """Request to update a collection item."""

    content: Optional[str] = None
    tags: Optional[TagsModel] = None
    summary: Optional[str] = None


class SyncResultResponse(BaseModel):
    """Response from filesystem sync."""

    items_added: int
    items_updated: int
    items_removed: int
    errors: list[str]


class GapItemResponse(BaseModel):
    """A gap identified during analysis."""

    gap_type: str
    value: str
    recommended_research: str


class RequirementsResponse(BaseModel):
    """Extracted project requirements."""

    project_name: str
    technologies: list[str]
    features: list[str]
    description: str


class GapAnalysisResponse(BaseModel):
    """Gap analysis result."""

    project_name: str
    requirements: RequirementsResponse
    matching_items: list[CollectionItemResponse]
    gaps: list[GapItemResponse]


class CopyRequest(BaseModel):
    """Request to copy items to a project."""

    item_ids: list[str]


class CopyResultResponse(BaseModel):
    """Result of copying items to a project."""

    project_name: str
    items_copied: list[str]
    files_created: list[str]
    errors: list[str]


class TagsListResponse(BaseModel):
    """Available tags by category."""

    technology: list[str]
    feature: list[str]
    priority: list[str]


# ----- Endpoints -----


class PaginatedCollectionResponse(BaseModel):
    """Paginated response for collection items."""

    items: list[CollectionItemResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


@router.get("/items", response_model=PaginatedCollectionResponse)
async def list_items(
    item_type: Optional[str] = Query(None, description="Filter by type: rule, skill, template"),
    technologies: Optional[str] = Query(None, description="Comma-separated technology tags"),
    features: Optional[str] = Query(None, description="Comma-separated feature tags"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    include_content: bool = Query(False, description="Include file content"),
    pagination: dict = Depends(pagination_params),
):
    """List all collection items with optional filters and pagination."""
    tech_list = technologies.split(",") if technologies else None
    feature_list = features.split(",") if features else None

    # Get all items matching filters
    all_items = await collection_service.list_items(
        item_type=item_type,
        technologies=tech_list,
        features=feature_list,
        priority=priority,
        include_content=include_content,
    )

    # Apply pagination
    offset = pagination["offset"]
    limit = pagination["limit"]
    total = len(all_items)
    paginated_items = all_items[offset : offset + limit]

    return PaginatedCollectionResponse(
        items=[_item_to_response(item) for item in paginated_items],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
    )


@router.get("/items/{item_id}", response_model=CollectionItemResponse)
async def get_item(item_id: str):
    """Get a single collection item with content."""
    item = await collection_service.get_item(item_id, include_content=True)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return _item_to_response(item)


@router.post("/items", response_model=CollectionItemResponse)
async def create_item(request: CreateItemRequest):
    """Create a new collection item."""
    try:
        item_type = ItemType(request.item_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid item_type: {request.item_type}")

    tags = CollectionTags(
        technology=request.tags.technology,
        feature=request.tags.feature,
        priority=request.tags.priority,
    )

    item = await collection_service.create_item(
        name=request.name,
        item_type=item_type,
        category=request.category,
        content=request.content,
        tags=tags,
        summary=request.summary,
    )

    return _item_to_response(item)


@router.put("/items/{item_id}", response_model=CollectionItemResponse)
async def update_item(item_id: str, request: UpdateItemRequest):
    """Update an existing collection item."""
    tags = None
    if request.tags:
        tags = CollectionTags(
            technology=request.tags.technology,
            feature=request.tags.feature,
            priority=request.tags.priority,
        )

    item = await collection_service.update_item(
        item_id=item_id,
        content=request.content,
        tags=tags,
        summary=request.summary,
    )

    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")

    return _item_to_response(item)


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, hard: bool = Query(False, description="Permanently delete")):
    """Delete a collection item (soft delete by default)."""
    success = await collection_service.delete_item(item_id, hard_delete=hard)
    if not success:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return {"success": True, "item_id": item_id, "hard_delete": hard}


@router.post("/sync", response_model=SyncResultResponse)
async def sync_from_filesystem():
    """Sync database metadata from filesystem.

    Scans the collection/ directory and updates the database
    to reflect the current state of files.
    """
    result = await collection_service.sync_from_filesystem()
    return SyncResultResponse(
        items_added=result.items_added,
        items_updated=result.items_updated,
        items_removed=result.items_removed,
        errors=result.errors,
    )


@router.get("/tags", response_model=TagsListResponse)
async def list_available_tags():
    """Get all available tags grouped by category."""
    tags = await collection_service.get_available_tags()
    return TagsListResponse(
        technology=tags.get("technology", []),
        feature=tags.get("feature", []),
        priority=tags.get("priority", []),
    )


@router.post("/gap-analysis/{project_name}", response_model=GapAnalysisResponse)
async def run_gap_analysis(project_name: str):
    """Run gap analysis for a project.

    Analyzes project documentation to extract requirements,
    finds matching collection items, and identifies gaps.
    """
    project_manager = ProjectManager(CONDUCTOR_ROOT)
    project_path = project_manager.get_project(project_name)

    if not project_path:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    result = await gap_engine.analyze_project(project_path, project_name)

    return GapAnalysisResponse(
        project_name=result.project_name,
        requirements=RequirementsResponse(
            project_name=result.requirements.project_name,
            technologies=result.requirements.technologies,
            features=result.requirements.features,
            description=result.requirements.description,
        ),
        matching_items=[_item_to_response(item) for item in result.matching_items],
        gaps=[
            GapItemResponse(
                gap_type=gap.gap_type,
                value=gap.value,
                recommended_research=gap.recommended_research,
            )
            for gap in result.gaps
        ],
    )


@router.post("/copy-to-project/{project_name}", response_model=CopyResultResponse)
async def copy_items_to_project(project_name: str, request: CopyRequest):
    """Copy selected collection items to a project folder.

    Creates copies of rules, skills, and templates in the
    appropriate locations within the project.
    """
    project_manager = ProjectManager(CONDUCTOR_ROOT)
    project_path = project_manager.get_project(project_name)

    if not project_path:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    result = CopyResult(project_name=project_name)

    for item_id in request.item_ids:
        item = await collection_service.get_item(item_id, include_content=True)
        if not item:
            result.errors.append(f"Item '{item_id}' not found")
            continue

        try:
            # Determine destination path based on item type
            if item.item_type == ItemType.RULE:
                dest_dir = project_path / "shared-rules"
            elif item.item_type == ItemType.SKILL:
                dest_dir = project_path / "skills"
            elif item.item_type == ItemType.TEMPLATE:
                # Templates go to root (CLAUDE.md, GEMINI.md)
                dest_dir = project_path
            else:
                dest_dir = project_path

            dest_dir.mkdir(parents=True, exist_ok=True)

            # Determine filename
            if item.item_type == ItemType.SKILL:
                dest_path = dest_dir / item.name / "SKILL.md"
                dest_path.parent.mkdir(parents=True, exist_ok=True)
            elif item.item_type == ItemType.TEMPLATE:
                # Use appropriate filename for templates
                if "claude" in item.category.lower():
                    dest_path = dest_dir / "CLAUDE.md"
                elif "gemini" in item.category.lower():
                    dest_path = dest_dir / "GEMINI.md"
                else:
                    dest_path = dest_dir / f"{item.name}.md"
            else:
                dest_path = dest_dir / f"{item.name}.md"

            # Write content
            dest_path.write_text(item.content or "")
            result.items_copied.append(item_id)
            result.files_created.append(str(dest_path.relative_to(project_path)))

        except Exception as e:
            result.errors.append(f"Failed to copy '{item_id}': {e}")

    return CopyResultResponse(
        project_name=result.project_name,
        items_copied=result.items_copied,
        files_created=result.files_created,
        errors=result.errors,
    )


# ----- Project Guardrails Endpoints -----


class ProjectGuardrailResponse(BaseModel):
    """A guardrail applied to a specific project."""

    item_id: str
    item_type: str
    enabled: bool
    delivery_method: str
    version_applied: int
    applied_at: str
    file_path: Optional[str] = None


class ProjectGuardrailsListResponse(BaseModel):
    """List of guardrails applied to a project."""

    project_name: str
    guardrails: list[ProjectGuardrailResponse]
    total: int
    enabled_count: int
    disabled_count: int


class EnableDisableRequest(BaseModel):
    """Request to enable/disable a guardrail."""

    enabled: bool


@router.get("/projects/{project_name}/guardrails", response_model=ProjectGuardrailsListResponse)
async def list_project_guardrails(project_name: str):
    """List all guardrails applied to a project.

    Args:
        project_name: Name of the project

    Returns:
        List of applied guardrails with their status
    """
    from orchestrator.db.connection import get_connection

    try:
        async with get_connection(project_name) as conn:
            results = await conn.query(
                "SELECT * FROM project_guardrails WHERE project_id = $pid ORDER BY applied_at DESC",
                {"pid": project_name},
            )

            guardrails = []
            enabled_count = 0
            disabled_count = 0

            for record in results:
                is_enabled = record.get("enabled", True)
                if is_enabled:
                    enabled_count += 1
                else:
                    disabled_count += 1

                guardrails.append(
                    ProjectGuardrailResponse(
                        item_id=record.get("item_id", ""),
                        item_type=record.get("item_type", ""),
                        enabled=is_enabled,
                        delivery_method=record.get("delivery_method", "file"),
                        version_applied=record.get("version_applied", 1),
                        applied_at=record.get("applied_at", ""),
                        file_path=record.get("file_path"),
                    )
                )

            return ProjectGuardrailsListResponse(
                project_name=project_name,
                guardrails=guardrails,
                total=len(guardrails),
                enabled_count=enabled_count,
                disabled_count=disabled_count,
            )

    except Exception as e:
        logger.error(f"Failed to list project guardrails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/guardrails/{item_id}/toggle")
async def toggle_project_guardrail(
    project_name: str,
    item_id: str,
    request: EnableDisableRequest,
):
    """Enable or disable a guardrail for a project.

    Args:
        project_name: Name of the project
        item_id: ID of the guardrail to toggle
        request: Enable/disable flag

    Returns:
        Updated guardrail status
    """
    from orchestrator.db.connection import get_connection

    try:
        async with get_connection(project_name) as conn:
            # Check if guardrail exists for this project
            existing = await conn.query(
                "SELECT * FROM project_guardrails WHERE project_id = $pid AND item_id = $iid",
                {"pid": project_name, "iid": item_id},
            )

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail=f"Guardrail '{item_id}' not found for project '{project_name}'",
                )

            # Update enabled status
            await conn.query(
                "UPDATE project_guardrails SET enabled = $enabled WHERE project_id = $pid AND item_id = $iid",
                {"pid": project_name, "iid": item_id, "enabled": request.enabled},
            )

            return {
                "message": f"Guardrail '{item_id}' {'enabled' if request.enabled else 'disabled'}",
                "item_id": item_id,
                "enabled": request.enabled,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle guardrail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/guardrails/{item_id}/promote")
async def promote_guardrail_to_global(
    project_name: str,
    item_id: str,
    guardrails_service: GuardrailsService = Depends(get_guardrails_service),
):
    """Promote a project-specific guardrail to the global collection.

    This copies the guardrail content to the central collection folder
    and creates metadata in the database.

    Args:
        project_name: Name of the project
        item_id: ID of the guardrail to promote
        guardrails_service: Injected guardrails service

    Returns:
        Details of the promoted item
    """
    # Get project path
    project_manager = ProjectManager(CONDUCTOR_ROOT)
    project = project_manager.get_project(project_name)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        project_path = Path(project.get("path", "")) if isinstance(project, dict) else project

        # Use the service to promote
        result = await guardrails_service.promote_to_global(
            project_name=project_name,
            project_dir=project_path,
            item_id=item_id,
        )

        if not result.promoted:
            if "not found" in result.message.lower():
                raise HTTPException(status_code=404, detail=result.message)
            raise HTTPException(status_code=400, detail=result.message)

        return {
            "message": result.message,
            "item_id": result.item_id,
            "source_project": result.source_project,
            "destination_path": result.destination_path,
            "errors": result.errors if result.errors else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to promote guardrail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/apply-recommended")
async def apply_recommended_guardrails(project_name: str):
    """Apply recommended guardrails to a project based on gap analysis.

    Runs gap analysis and applies all matching items.

    Args:
        project_name: Name of the project

    Returns:
        Summary of applied items
    """
    from orchestrator.collection.project_setup import ProjectGuardrailsSetup

    # Get project path
    project_manager = ProjectManager(CONDUCTOR_ROOT)
    project = project_manager.get_project(project_name)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        project_path = Path(project.get("path", ""))

        # Run gap analysis
        analysis = await gap_engine.analyze_project(project_path, project_name)

        if not analysis.matching_items:
            return {
                "message": "No matching guardrails found",
                "items_applied": 0,
            }

        # Apply matching items
        setup = ProjectGuardrailsSetup(collection_service)
        result = await setup.apply_guardrails(
            project_path=project_path,
            items=analysis.matching_items,
            project_id=project_name,
        )

        return {
            "message": f"Applied {len(result.items_applied)} guardrails",
            "items_applied": len(result.items_applied),
            "files_created": result.files_created,
            "cursor_rules_created": result.cursor_rules_created,
            "errors": result.errors,
        }

    except Exception as e:
        logger.error(f"Failed to apply recommended guardrails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----- Helper Functions -----


def _item_to_response(item: CollectionItem) -> CollectionItemResponse:
    """Convert CollectionItem to response model."""
    return CollectionItemResponse(
        id=str(item.id),
        name=item.name,
        item_type=item.item_type.value if isinstance(item.item_type, ItemType) else item.item_type,
        category=item.category,
        file_path=item.file_path,
        summary=item.summary,
        tags=TagsModel(
            technology=item.tags.technology,
            feature=item.tags.feature,
            priority=item.tags.priority,
        ),
        version=item.version,
        is_active=item.is_active,
        content=item.content,
    )
