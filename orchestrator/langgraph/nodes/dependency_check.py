"""Dependency check node.

Analyzes project dependencies for:
- Outdated npm packages
- Security vulnerabilities
- Docker image security
- Framework version compatibility

This node runs after security_scan and before completion.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import load_project_config
from ...validators import DependencyChecker, DependencySeverity
from ..state import WorkflowState, create_error_context

logger = logging.getLogger(__name__)


async def dependency_check_node(state: WorkflowState) -> dict[str, Any]:
    """Run dependency analysis.

    Args:
        state: Current workflow state

    Returns:
        State updates with dependency check results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running dependency check for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.dependency_check:
        logger.info("Dependency check disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    if not config.dependency.enabled:
        logger.info("Dependency check disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Map config severities to enum
    blocking_severities = []
    for sev_str in config.dependency.blocking_severities:
        try:
            blocking_severities.append(DependencySeverity(sev_str.lower()))
        except ValueError:
            logger.warning(f"Unknown severity: {sev_str}")

    # Run dependency check
    checker = DependencyChecker(
        project_dir,
        check_npm=config.dependency.check_npm,
        check_docker=config.dependency.check_docker,
        check_frameworks=config.dependency.check_frameworks,
        blocking_severities=blocking_severities,
    )
    result = checker.check()

    # Build output for storage
    dependency_check_result = {
        "agent": "A14",
        "task_id": "dependency-check",
        "status": "passed" if result.passed else "failed",
        "passed": result.passed,
        "total_findings": result.total_findings,
        "blocking_findings": result.blocking_findings,
        "npm_analysis": result.npm_analysis,
        "docker_analysis": result.docker_analysis,
        "framework_analysis": result.framework_analysis,
        "recommendations": result.recommendations,
        "auto_fixable": result.auto_fixable,
        "blocking_issues": [],
        "timestamp": datetime.now().isoformat(),
    }

    # Build blocking issues list
    if not result.passed:
        for finding in result.findings:
            if finding.severity in blocking_severities:
                dependency_check_result["blocking_issues"].append(
                    f"{finding.severity.value.upper()}: {finding.package} - {finding.message}"
                )

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(
        repo.save_output(phase=4, output_type="dependency_check", content=dependency_check_result)
    )

    logger.info(
        f"Dependency check {'passed' if result.passed else 'failed'}: "
        f"{result.total_findings} findings, {result.blocking_findings} blocking"
    )

    # Generate dependabot.yml if missing and configured
    if config.dependency.generate_dependabot:
        _generate_dependabot_if_missing(project_dir)

    if not result.passed:
        # Format error message for blocking issues
        error_message = f"Dependency check found {result.blocking_findings} blocking issues:\n\n"

        for finding in result.findings[:10]:  # Limit to 10
            if finding.severity in blocking_severities:
                error_message += (
                    f"- [{finding.severity.value.upper()}] {finding.package}: {finding.message}\n"
                )
                if finding.fix_command:
                    error_message += f"  Fix: {finding.fix_command}\n"

        # Create error context
        error_ctx = create_error_context(
            source_node="dependency_check",
            exception=Exception(
                f"Dependency check failed: {result.blocking_findings} blocking issues"
            ),
            state=state,
            recoverable=True,
            suggested_actions=[
                "Run 'npm audit fix' for auto-fixable vulnerabilities",
                "Review and upgrade packages with security issues",
                "Pin Docker image versions to specific tags",
            ],
        )

        return {
            "dependency_check_result": dependency_check_result,
            "errors": [error_ctx],
            "next_decision": "escalate",  # Escalate to human for approval
            "updated_at": datetime.now().isoformat(),
        }

    # Log warnings for non-blocking findings
    if result.total_findings > 0:
        logger.warning(
            f"Dependency check found {result.total_findings} non-blocking issues. "
            f"Review dependency_check results for details."
        )

    return {
        "dependency_check_result": dependency_check_result,
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }


def _generate_dependabot_if_missing(project_dir: Path) -> None:
    """Generate .github/dependabot.yml if missing.

    Args:
        project_dir: Project directory path
    """
    github_dir = project_dir / ".github"
    dependabot_file = github_dir / "dependabot.yml"

    if dependabot_file.exists():
        return

    # Check if this is an npm project
    has_npm = (project_dir / "package.json").exists()
    has_docker = (project_dir / "Dockerfile").exists()

    if not has_npm and not has_docker:
        return

    try:
        github_dir.mkdir(parents=True, exist_ok=True)

        content = """# Dependabot configuration - auto-generated by A14
version: 2
updates:
"""
        if has_npm:
            content += """  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
"""

        if has_docker:
            content += """  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
"""

        dependabot_file.write_text(content)
        logger.info(f"Generated {dependabot_file}")

    except Exception as e:
        logger.warning(f"Could not generate dependabot.yml: {e}")
