"""Security scan node.

Scans source code for security vulnerabilities
before completing the workflow.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import load_project_config
from ...validators import SecurityScanner
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def security_scan_node(state: WorkflowState) -> dict[str, Any]:
    """Scan for security vulnerabilities.

    Args:
        state: Current workflow state

    Returns:
        State updates with security scan results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running security scan for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.security_scan:
        logger.info("Security scan disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    if not config.security.enabled:
        logger.info("Security disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Run security scan
    scanner = SecurityScanner(
        project_dir,
        blocking_severities=config.security.blocking_severities,
    )
    result = scanner.scan()

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save_output(phase=4, output_type="security_scan", content=result.to_dict()))

    logger.info(
        f"Security scan complete: {result.total_findings} findings, "
        f"{result.blocking_findings} blocking, "
        f"{result.files_scanned} files scanned"
    )

    if not result.passed:
        # Format error message
        error_message = f"Security scan found {result.blocking_findings} blocking issues:\n\n"

        # Group by severity
        by_severity: dict[str, list] = {}
        for finding in result.findings:
            if finding.severity in config.security.blocking_severities:
                sev = finding.severity.value.upper()
                if sev not in by_severity:
                    by_severity[sev] = []
                by_severity[sev].append(finding)

        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if severity in by_severity:
                error_message += f"\n{severity} ({len(by_severity[severity])}):\n"
                for finding in by_severity[severity][:5]:  # Limit to 5 per severity
                    error_message += (
                        f"  - {finding.file_path}:{finding.line_number}\n"
                        f"    {finding.message}\n"
                    )
                    if finding.suggestion:
                        error_message += f"    Fix: {finding.suggestion}\n"

        return {
            "errors": [
                {
                    "type": "security_vulnerabilities",
                    "message": error_message,
                    "total_findings": result.total_findings,
                    "blocking_findings": result.blocking_findings,
                    "findings_by_severity": {
                        k.value: v for k, v in result.findings_by_severity.items()
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "retry",  # Retry implementation to fix issues
            "updated_at": datetime.now().isoformat(),
        }

    # Log warnings for non-blocking findings
    if result.total_findings > 0:
        logger.warning(
            f"Security scan found {result.total_findings} non-blocking issues. "
            f"Review {scan_dir / 'security_scan.json'} for details."
        )

    return {
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
