"""Guardrails Agent Node.

Applies guardrails from the central collection to the project.
Runs early in the workflow to ensure proper context is set up.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def guardrails_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Apply guardrails from collection to project.

    This node:
    1. Runs gap analysis on project documentation
    2. Finds matching collection items
    3. Copies files to project .conductor/ folder
    4. Generates cursor rules
    5. Records applied items in database
    6. Stores gaps in state for research phase

    Args:
        state: Current workflow state

    Returns:
        State updates with guardrails applied
    """
    project_name = state.get("project_name", "unknown")
    project_dir = Path(state["project_dir"])

    logger.info(f"Applying guardrails for project: {project_name}")

    try:
        # Import services
        from ...collection.gap_analysis import GapAnalysisEngine
        from ...collection.project_setup import ProjectGuardrailsSetup
        from ...collection.service import CollectionService
        from ...db.connection import get_connection

        # Initialize services
        collection_service = CollectionService()
        gap_engine = GapAnalysisEngine(collection_service)
        project_setup = ProjectGuardrailsSetup(collection_service)

        # Step 1: Run gap analysis
        logger.debug(f"Running gap analysis for {project_dir}")
        analysis = await gap_engine.analyze_project(project_dir, project_name)

        matching_items = analysis.matching_items
        gaps = analysis.gaps

        logger.info(
            f"Gap analysis complete: {len(matching_items)} matching items, "
            f"{len(gaps)} gaps identified"
        )

        # Step 2: Apply matching items to project
        if matching_items:
            apply_result = await project_setup.apply_guardrails(
                project_path=project_dir,
                items=matching_items,
                project_id=project_name,
            )

            logger.info(
                f"Applied {len(apply_result.items_applied)} items: "
                f"{len(apply_result.files_created)} files, "
                f"{len(apply_result.cursor_rules_created)} cursor rules"
            )

            if apply_result.errors:
                logger.warning(f"Errors during apply: {apply_result.errors}")

        # Step 3: Update agent files with templates if available
        template_items = [
            item for item in matching_items if "template" in str(item.item_type).lower()
        ]
        if template_items or not (project_dir / "CLAUDE.md").exists():
            await project_setup.update_agent_files(project_dir, template_items)
            logger.debug("Updated agent context files")

        # Step 4: Record applied items in database
        try:
            async with get_connection(project_name) as conn:
                for item in matching_items:
                    # Check if already exists
                    existing = await conn.query(
                        "SELECT * FROM project_guardrails WHERE project_id = $pid AND item_id = $iid",
                        {"pid": project_name, "iid": item.id},
                    )

                    if not existing:
                        await conn.create(
                            "project_guardrails",
                            {
                                "project_id": project_name,
                                "item_id": item.id,
                                "item_type": (
                                    item.item_type.value
                                    if hasattr(item.item_type, "value")
                                    else str(item.item_type)
                                ),
                                "enabled": True,
                                "delivery_method": "file",
                                "version_applied": item.version,
                            },
                        )

                # Cache gap analysis results
                await conn.query(
                    "DELETE FROM gap_analysis_results WHERE project_id = $pid",
                    {"pid": project_name},
                )

                await conn.create(
                    "gap_analysis_results",
                    {
                        "project_id": project_name,
                        "technologies": list(analysis.requirements.technologies),
                        "features": list(analysis.requirements.features),
                        "matched_items": [item.id for item in matching_items],
                        "gaps": [
                            {
                                "type": gap.gap_type,
                                "value": gap.value,
                                "research": gap.recommended_research,
                            }
                            for gap in gaps
                        ],
                    },
                )

                logger.debug(f"Recorded {len(matching_items)} guardrails in database")

        except Exception as e:
            logger.warning(f"Failed to record guardrails in database: {e}")
            # Non-fatal - files are already applied

        # Step 5: Prepare state updates
        guardrails_summary = {
            "items_applied": len(matching_items) if matching_items else 0,
            "gaps_identified": len(gaps),
            "technologies_detected": list(analysis.requirements.technologies),
            "features_detected": list(analysis.requirements.features),
            "applied_at": datetime.now().isoformat(),
        }

        # Store gaps for potential research phase
        gap_items = [
            {
                "type": gap.gap_type,
                "value": gap.value,
                "recommended_research": gap.recommended_research,
            }
            for gap in gaps
        ]

        logger.info(
            f"Guardrails agent complete: applied {guardrails_summary['items_applied']} items"
        )

        return {
            "guardrails_summary": guardrails_summary,
            "guardrails_gaps": gap_items,
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    except Exception as e:
        logger.error(f"Guardrails agent failed: {e}", exc_info=True)

        # Non-fatal - workflow can continue without guardrails
        return {
            "guardrails_summary": {
                "error": str(e),
                "applied_at": datetime.now().isoformat(),
            },
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",  # Don't block workflow
        }
