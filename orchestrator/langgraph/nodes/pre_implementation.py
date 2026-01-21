"""Pre-implementation environment check node.

Validates that the development environment is ready
before starting implementation.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState
from ...validators import EnvironmentChecker
from ...config import load_project_config

logger = logging.getLogger(__name__)


async def pre_implementation_node(state: WorkflowState) -> dict[str, Any]:
    """Check environment before implementation.

    Validates:
    - Required tools are installed
    - Dependencies can be resolved
    - Test framework is detected

    Args:
        state: Current workflow state

    Returns:
        State updates with environment check results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running pre-implementation checks for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.environment_check:
        logger.info("Environment check disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Run environment checks
    checker = EnvironmentChecker(project_dir)
    result = checker.check()

    # Save check results
    check_dir = project_dir / ".workflow" / "phases" / "pre_implementation"
    check_dir.mkdir(parents=True, exist_ok=True)

    result_file = check_dir / "pre_implementation_check.json"
    result_file.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "ready": result.ready,
        "project_type": result.project_type.value,
        "complexity": result.complexity.value,
        "checks": [c.to_dict() for c in result.checks],
        "test_framework": result.test_framework,
        "build_command": result.build_command,
        "test_command": result.test_command,
    }, indent=2))

    if not result.ready:
        # Format failed checks
        failed_checks = [c for c in result.checks if c.status.value == "failed"]
        error_details = []
        for check in failed_checks:
            error_details.append(f"- {check.name}: {check.message}")
            if check.details:
                error_details.append(f"  Details: {check.details}")

        error_message = (
            f"Environment not ready for implementation\n"
            f"Failed checks:\n" + "\n".join(error_details)
        )

        logger.warning(f"Pre-implementation check failed: {len(failed_checks)} issues")

        return {
            "errors": [{
                "type": "environment_not_ready",
                "message": error_message,
                "failed_checks": [c.to_dict() for c in failed_checks],
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
            "updated_at": datetime.now().isoformat(),
        }

    # Store detected commands in implementation_result for later use
    implementation_info = state.get("implementation_result") or {}
    implementation_info["environment"] = {
        "project_type": result.project_type.value,
        "complexity": result.complexity.value,
        "test_framework": result.test_framework,
        "build_command": result.build_command,
        "test_command": result.test_command,
    }

    logger.info(
        f"Environment ready: type={result.project_type.value}, "
        f"complexity={result.complexity.value}"
    )

    return {
        "implementation_result": implementation_info,
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
