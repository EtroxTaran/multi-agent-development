"""Documentation discovery workflow node.

Reads ALL documentation from docs/ folder to provide comprehensive
context for AI agents. Only escalates if no docs folder exists.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import load_project_config
from ...validators.documentation_discovery import DocumentationScanner
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def documentation_discovery_node(state: WorkflowState) -> dict[str, Any]:
    """Discover and read ALL project documentation.

    Reads all markdown files from docs/ folder recursively.
    Builds comprehensive context for agents to reference.
    Only escalates to human if no documentation exists.

    Args:
        state: Current workflow state

    Returns:
        State updates with discovered documentation
    """
    project_dir = Path(state["project_dir"])
    project_name = state["project_name"]
    logger.info(f"Discovering documentation for project: {project_name}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is disabled
    if not getattr(config.workflow.features, "documentation_discovery", True):
        logger.info("Documentation discovery disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Discover documentation
    scanner = DocumentationScanner()
    result = scanner.discover(project_dir)

    # Save discovery results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    discovery_result = {
        "timestamp": datetime.now().isoformat(),
        "source_folders": result.source_folders,
        "document_count": len(result.documents),
        "documents": [
            {"path": str(d.path), "title": d.title, "category": d.category.value}
            for d in result.documents
        ],
    }

    repo = get_phase_output_repository(project_name)
    run_async(
        repo.save_output(
            phase=0,
            output_type="documentation_discovery",
            content=discovery_result,
        )
    )

    # Save full discovered context for agents (includes content)
    discovered_context = result.to_dict()
    run_async(
        repo.save_output(
            phase=0,
            output_type="discovered_context",
            content=discovered_context,
        )
    )

    # Save discovered context to .workflow for easy agent access
    workflow_dir = project_dir / ".workflow" / "phases" / "0"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    context_file = workflow_dir / "discovered_context.json"
    try:
        context_file.write_text(json.dumps(discovered_context, indent=2))
        logger.info(f"Saved discovered context to {context_file}")
    except Exception as e:
        logger.warning(f"Could not save discovered_context.json: {e}")

    # Only escalate if NO documentation exists
    if not result.is_valid:
        logger.warning("No documentation found - escalating to human")
        return {
            "errors": [
                {
                    "type": "no_documentation",
                    "message": (
                        "No documentation found in project.\n\n"
                        "Please create a docs/ folder with your project documentation:\n"
                        "- Product vision and requirements\n"
                        "- Technical design and architecture\n"
                        "- Implementation guides\n\n"
                        "All markdown files in docs/ will be read automatically."
                    ),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info(
        f"Documentation discovered: {len(result.documents)} files from {result.source_folders}"
    )

    return {
        "documentation_discovery": discovery_result,
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
