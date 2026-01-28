"""Pre-implementation environment check node.

Validates that the development environment is ready
before starting implementation. Also proactively installs
dependencies to prevent runtime errors.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...config import load_project_config
from ...validators import EnvironmentChecker
from ..state import WorkflowState

logger = logging.getLogger(__name__)

# Timeout for dependency installation (5 minutes for large projects)
INSTALL_TIMEOUT = 300


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

    # Proactively install dependencies before implementation
    install_result = _install_dependencies(project_dir, result.project_type.value)
    if install_result and not install_result.get("success"):
        logger.warning(f"Dependency installation issue: {install_result.get('error')}")
        # Non-blocking - continue with environment check but log the issue

    # Save check results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    check_result = {
        "timestamp": datetime.now().isoformat(),
        "ready": result.ready,
        "project_type": result.project_type.value,
        "complexity": result.complexity.value,
        "checks": [c.to_dict() for c in result.checks],
        "test_framework": result.test_framework,
        "build_command": result.build_command,
        "test_command": result.test_command,
    }
    repo = get_phase_output_repository(state["project_name"])
    run_async(
        repo.save_output(phase=3, output_type="pre_implementation_check", content=check_result)
    )

    if not result.ready:
        # Format failed checks
        failed_checks = [c for c in result.checks if c.status.value == "failed"]
        error_details = []
        for check in failed_checks:
            error_details.append(f"- {check.name}: {check.message}")
            if check.details:
                error_details.append(f"  Details: {check.details}")

        error_message = "Environment not ready for implementation\n" "Failed checks:\n" + "\n".join(
            error_details
        )

        logger.warning(f"Pre-implementation check failed: {len(failed_checks)} issues")

        return {
            "errors": [
                {
                    "type": "environment_not_ready",
                    "message": error_message,
                    "failed_checks": [c.to_dict() for c in failed_checks],
                    "timestamp": datetime.now().isoformat(),
                }
            ],
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


def _install_dependencies(project_dir: Path, project_type: str) -> Optional[dict[str, Any]]:
    """Proactively install project dependencies.

    Detects the project type and runs the appropriate package manager
    to install dependencies before implementation starts.

    Args:
        project_dir: Project directory path
        project_type: Detected project type (node, python, etc.)

    Returns:
        Dictionary with installation result or None if skipped
    """
    install_command = _get_install_command(project_dir, project_type)

    if not install_command:
        logger.debug("No install command detected, skipping dependency installation")
        return None

    logger.info(f"Installing dependencies: {install_command}")

    try:
        result = subprocess.run(
            install_command,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
        )

        if result.returncode == 0:
            logger.info("Dependencies installed successfully")
            return {
                "success": True,
                "command": install_command,
                "output": result.stdout[-1000:],  # Last 1000 chars
            }
        else:
            logger.warning(f"Dependency installation failed with exit code {result.returncode}")
            return {
                "success": False,
                "command": install_command,
                "exit_code": result.returncode,
                "error": result.stderr[-2000:] if result.stderr else result.stdout[-2000:],
            }

    except subprocess.TimeoutExpired:
        logger.error(f"Dependency installation timed out after {INSTALL_TIMEOUT} seconds")
        return {
            "success": False,
            "command": install_command,
            "error": f"Installation timed out after {INSTALL_TIMEOUT} seconds",
        }
    except Exception as e:
        logger.error(f"Error installing dependencies: {e}")
        return {
            "success": False,
            "command": install_command,
            "error": str(e),
        }


def _get_install_command(project_dir: Path, project_type: str) -> Optional[str]:
    """Get the appropriate install command for the project type.

    Args:
        project_dir: Project directory path
        project_type: Detected project type

    Returns:
        Install command string or None
    """
    # Node.js projects - detect package manager from lock files
    if project_type in ("node", "react", "node-api"):
        if (project_dir / "pnpm-lock.yaml").exists():
            return "pnpm install"
        if (project_dir / "yarn.lock").exists():
            return "yarn install"
        if (project_dir / "bun.lockb").exists():
            return "bun install"
        if (project_dir / "package-lock.json").exists():
            return "npm install"
        # Default to npm if package.json exists but no lock file
        if (project_dir / "package.json").exists():
            return "npm install"

    # Python projects
    elif project_type == "python":
        # Check for pyproject.toml with pip install -e .
        if (project_dir / "pyproject.toml").exists():
            # Check if it's a pip-installable project
            try:
                content = (project_dir / "pyproject.toml").read_text()
                if "[project]" in content or "[build-system]" in content:
                    return "pip install -e ."
            except Exception:
                pass

        # Check for requirements.txt
        if (project_dir / "requirements.txt").exists():
            return "pip install -r requirements.txt"

        # Check for requirements-dev.txt
        if (project_dir / "requirements-dev.txt").exists():
            return "pip install -r requirements-dev.txt"

    # Go projects
    elif project_type == "go":
        if (project_dir / "go.mod").exists():
            return "go mod download"

    # Rust projects
    elif project_type == "rust":
        if (project_dir / "Cargo.toml").exists():
            return "cargo fetch"

    # Java/Spring projects
    elif project_type == "java-spring":
        if (project_dir / "gradlew").exists():
            return "./gradlew dependencies"
        if (project_dir / "pom.xml").exists():
            return "mvn dependency:resolve"

    return None
