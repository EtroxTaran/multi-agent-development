"""Product specification validation node.

Validates PRODUCT.md content for completeness and quality
before starting the planning phase.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus
from ...validators import ProductValidator
from ...config import load_project_config

logger = logging.getLogger(__name__)


async def product_validation_node(state: WorkflowState) -> dict[str, Any]:
    """Validate PRODUCT.md specification.

    Checks:
    - Required sections are present
    - No placeholder text
    - Minimum content quality

    Args:
        state: Current workflow state

    Returns:
        State updates with validation results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Validating PRODUCT.md for project: {state['project_name']}")

    # Load project config for threshold
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.product_validation:
        logger.info("Product validation disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Validate PRODUCT.md
    product_file = project_dir / "PRODUCT.md"
    validator = ProductValidator()
    result = validator.validate_file(product_file)

    # Save validation results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    validation_result = {
        "timestamp": datetime.now().isoformat(),
        "valid": result.valid,
        "score": result.score,
        "issues": [i.to_dict() for i in result.issues],
        "section_scores": result.section_scores,
        "placeholder_count": result.placeholder_count,
    }
    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save_output(phase=0, output_type="product_validation", content=validation_result))

    if not result.valid:
        logger.warning(f"PRODUCT.md validation failed: score={result.score}, issues={len(result.issues)}")

        # Format error message
        error_details = []
        for issue in result.issues:
            error_details.append(f"- [{issue.severity.value}] {issue.section}: {issue.message}")
            if issue.suggestion:
                error_details.append(f"  Suggestion: {issue.suggestion}")

        error_message = (
            f"PRODUCT.md validation failed with score {result.score}/10\n"
            f"Issues found:\n" + "\n".join(error_details)
        )

        return {
            "errors": [{
                "type": "product_validation_failed",
                "message": error_message,
                "score": result.score,
                "issues": [i.to_dict() for i in result.issues],
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info(f"PRODUCT.md validation passed: score={result.score}")

    return {
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
