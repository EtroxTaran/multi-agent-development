"""Coverage check node.

Verifies that test coverage meets configured thresholds
after verification.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState
from ...validators import CoverageChecker
from ...config import load_project_config

logger = logging.getLogger(__name__)


async def coverage_check_node(state: WorkflowState) -> dict[str, Any]:
    """Check test coverage against threshold.

    Args:
        state: Current workflow state

    Returns:
        State updates with coverage check results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running coverage check for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.coverage_check:
        logger.info("Coverage check disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Run coverage check
    checker = CoverageChecker(
        project_dir,
        threshold=config.quality.coverage_threshold,
        blocking=config.quality.coverage_blocking,
    )
    result = checker.check()

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save(phase=4, output_type="coverage_check", content=result.to_dict()))

    # Log result
    if result.status.value == "skipped":
        logger.info("No coverage report found, skipping coverage check")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    logger.info(
        f"Coverage: {result.overall_percent:.1f}% "
        f"(threshold: {result.threshold}%, status: {result.status.value})"
    )

    # Handle low coverage
    if result.status.value == "failed":
        # Blocking failure
        error_message = (
            f"Coverage {result.overall_percent:.1f}% is below "
            f"blocking threshold {result.threshold}%\n"
        )

        if result.uncovered_files:
            error_message += f"\nUncovered files ({len(result.uncovered_files)}):\n"
            for f in result.uncovered_files[:10]:
                error_message += f"  - {f}\n"

        if result.low_coverage_files:
            error_message += f"\nLow coverage files:\n"
            for f, pct in result.low_coverage_files[:10]:
                error_message += f"  - {f}: {pct:.1f}%\n"

        return {
            "errors": [{
                "type": "coverage_below_threshold",
                "message": error_message,
                "coverage": result.overall_percent,
                "threshold": result.threshold,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "retry",  # Retry implementation to add tests
            "updated_at": datetime.now().isoformat(),
        }

    elif result.status.value == "warning":
        # Non-blocking warning
        logger.warning(
            f"Coverage {result.overall_percent:.1f}% is below threshold "
            f"{result.threshold}% but coverage is non-blocking"
        )

    return {
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
