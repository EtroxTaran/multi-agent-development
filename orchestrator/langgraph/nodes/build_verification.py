"""Build verification node.

Verifies that the implementation builds successfully
before proceeding to code review.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import WorkflowState
from ...config import load_project_config

logger = logging.getLogger(__name__)

# Build commands by project type
DEFAULT_BUILD_COMMANDS = {
    "node": ["npm", "run", "build"],
    "react": ["npm", "run", "build"],
    "node-api": ["npm", "run", "build"],
    "react-tanstack": ["npm", "run", "build"],
    "java-spring": ["./gradlew", "build", "-x", "test"],
    "rust": ["cargo", "build"],
    "go": ["go", "build", "./..."],
    "python": None,  # Python typically doesn't have a build step
}

# Type check commands by project type
TYPE_CHECK_COMMANDS = {
    "node": ["npm", "run", "type-check"],
    "react": ["npm", "run", "type-check"],
    "node-api": ["npm", "run", "type-check"],
    "react-tanstack": ["npm", "run", "type-check"],
}


async def build_verification_node(state: WorkflowState) -> dict[str, Any]:
    """Verify that implementation builds successfully.

    Runs:
    - Type checking (if applicable)
    - Build command

    Args:
        state: Current workflow state

    Returns:
        State updates with build verification results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running build verification for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.build_verification:
        logger.info("Build verification disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    if not config.quality.build_required:
        logger.info("Build not required by config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Get project type from pre-implementation check
    impl_result = state.get("implementation_result") or {}
    env_info = impl_result.get("environment", {})
    project_type = env_info.get("project_type", config.project_type)

    results = {
        "timestamp": datetime.now().isoformat(),
        "type_check": None,
        "build": None,
        "passed": True,
    }

    # Run type check first (if available)
    type_check_cmd = _detect_type_check_command(project_dir, project_type)
    if type_check_cmd:
        type_result = _run_command(type_check_cmd, project_dir, "Type check")
        results["type_check"] = type_result

        if not type_result["success"]:
            results["passed"] = False
            logger.warning(f"Type check failed: {type_result['error'][:200]}")

    # Run build
    build_cmd = _detect_build_command(project_dir, project_type)
    if build_cmd:
        build_result = _run_command(build_cmd, project_dir, "Build")
        results["build"] = build_result

        if not build_result["success"]:
            results["passed"] = False
            logger.warning(f"Build failed: {build_result['error'][:200]}")
    else:
        logger.info(f"No build command for project type: {project_type}")

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save(phase=4, output_type="build_verification", content=results))

    if not results["passed"]:
        # Format error message
        error_parts = []
        if results["type_check"] and not results["type_check"]["success"]:
            error_parts.append(f"Type check failed:\n{results['type_check']['error'][:500]}")
        if results["build"] and not results["build"]["success"]:
            error_parts.append(f"Build failed:\n{results['build']['error'][:500]}")

        # Add error to state - verification_fan_in will check for this
        # and route appropriately (retry implementation or escalate)
        return {
            "errors": [{
                "type": "build_verification_failed",
                "message": "\n\n".join(error_parts),
                "details": results,
                "timestamp": datetime.now().isoformat(),
            }],
            # Note: We set next_decision but the parallel fan-out means
            # both reviewers will still run. verification_fan_in checks
            # for build errors and handles accordingly.
            "next_decision": "retry",
            "updated_at": datetime.now().isoformat(),
        }

    logger.info("Build verification passed")

    # Store build success in implementation_result for verification to check
    impl_result = state.get("implementation_result") or {}
    impl_result["build_passed"] = True
    impl_result["build_results"] = results

    return {
        "implementation_result": impl_result,
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }


def _detect_type_check_command(
    project_dir: Path,
    project_type: str,
) -> Optional[list[str]]:
    """Detect type check command for the project."""
    package_json = project_dir / "package.json"

    if package_json.exists():
        try:
            import json as json_mod
            pkg = json_mod.loads(package_json.read_text())
            scripts = pkg.get("scripts", {})

            if "type-check" in scripts:
                return ["npm", "run", "type-check"]
            if "typecheck" in scripts:
                return ["npm", "run", "typecheck"]
            if "tsc" in scripts:
                return ["npm", "run", "tsc"]

        except Exception:
            pass

    return TYPE_CHECK_COMMANDS.get(project_type)


def _detect_build_command(
    project_dir: Path,
    project_type: str,
) -> Optional[list[str]]:
    """Detect build command for the project."""
    package_json = project_dir / "package.json"

    if package_json.exists():
        try:
            import json as json_mod
            pkg = json_mod.loads(package_json.read_text())
            scripts = pkg.get("scripts", {})

            if "build" in scripts:
                return ["npm", "run", "build"]

        except Exception:
            pass

    # Check for Gradle wrapper
    if project_type == "java-spring":
        if (project_dir / "gradlew").exists():
            return ["./gradlew", "build", "-x", "test"]
        return ["gradle", "build", "-x", "test"]

    return DEFAULT_BUILD_COMMANDS.get(project_type)


def _run_command(
    cmd: list[str],
    cwd: Path,
    name: str,
) -> dict[str, Any]:
    """Run a command and capture results.

    Args:
        cmd: Command and arguments
        cwd: Working directory
        name: Name for logging

    Returns:
        Result dict with success, output, error
    """
    logger.info(f"Running {name}: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        return {
            "command": " ".join(cmd),
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "output": result.stdout[:5000] if result.stdout else "",
            "error": result.stderr[:5000] if result.stderr else "",
        }

    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(cmd),
            "success": False,
            "return_code": -1,
            "output": "",
            "error": f"{name} timed out after 5 minutes",
        }

    except FileNotFoundError:
        return {
            "command": " ".join(cmd),
            "success": False,
            "return_code": -1,
            "output": "",
            "error": f"Command not found: {cmd[0]}",
        }

    except Exception as e:
        return {
            "command": " ".join(cmd),
            "success": False,
            "return_code": -1,
            "output": "",
            "error": str(e),
        }
