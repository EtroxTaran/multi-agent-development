#!/usr/bin/env python3
"""Migrate existing .workflow/ file data to SurrealDB.

This script is a one-time migration tool for projects that have
existing .workflow/ directories with file-based state storage.

Usage:
    python scripts/migrate_workflow_to_db.py <project-name>
    python scripts/migrate_workflow_to_db.py --path /path/to/project
    python scripts/migrate_workflow_to_db.py --all  # Migrate all projects

Requirements:
    - SURREAL_URL environment variable must be set
    - Project must have existing .workflow/ directory
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Check for required dependencies
try:
    import websockets  # noqa: F401
except ImportError:
    print("ERROR: Missing required dependency 'websockets'")
    print("Install with: pip install websockets")
    sys.exit(1)

from orchestrator.db.config import require_db, get_db_config
from orchestrator.db.connection import get_connection
from orchestrator.db.schema import ensure_schema
from orchestrator.db.repositories.phase_outputs import get_phase_output_repository
from orchestrator.db.repositories.logs import get_logs_repository
from orchestrator.db.repositories.workflow import get_workflow_repository

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# Mapping of file paths to phase outputs
FILE_TO_PHASE_OUTPUT = {
    "phases/product_validation/product_validation.json": (0, "product_validation"),
    "phases/planning/plan.json": (1, "plan"),
    "phases/task_breakdown/tasks.json": (1, "task_breakdown"),
    "phases/validation/cursor_feedback.json": (2, "cursor_feedback"),
    "phases/validation/gemini_feedback.json": (2, "gemini_feedback"),
    "phases/validation/consolidated.json": (2, "validation_consolidated"),
    "phases/pre_implementation/pre_implementation_check.json": (3, "pre_implementation_check"),
    "phases/implementation/result.json": (3, "implementation_result"),
    "phases/implementation/partial_result.json": (3, "partial_result"),
    "phases/implementation/clarifications_needed.json": (3, "clarifications_needed"),
    "phases/security_scan/security_scan.json": (4, "security_scan"),
    "phases/coverage_check/coverage_check.json": (4, "coverage_check"),
    "phases/build_verification/build_verification.json": (4, "build_verification"),
    "phases/verification/cursor_review.json": (4, "cursor_review"),
    "phases/verification/gemini_review.json": (4, "gemini_review"),
    "phases/verification/consolidated.json": (4, "verification_consolidated"),
    "phases/completion/summary.json": (5, "summary"),
}

# Mapping of file paths to logs
FILE_TO_LOG = {
    "phases/research/findings.json": "research_aggregated",
    "escalation.json": "escalation",
    "blockers.md": "blocker",
    "clarification_answers.json": "clarification_answers",
}


async def migrate_project(project_dir: Path, project_name: str) -> dict[str, Any]:
    """Migrate a single project's .workflow/ data to SurrealDB.

    Args:
        project_dir: Path to project directory
        project_name: Project name for database

    Returns:
        Migration result summary
    """
    workflow_dir = project_dir / ".workflow"
    if not workflow_dir.exists():
        return {
            "status": "skipped",
            "reason": "No .workflow/ directory found",
            "project": project_name,
        }

    logger.info(f"Migrating project: {project_name}")
    logger.info(f"  Source: {workflow_dir}")

    # Ensure schema exists
    await ensure_schema(project_name)

    # Initialize repositories
    phase_repo = get_phase_output_repository(project_name)
    logs_repo = get_logs_repository(project_name)
    workflow_repo = get_workflow_repository(project_name)

    results = {
        "project": project_name,
        "status": "success",
        "migrated_files": [],
        "skipped_files": [],
        "errors": [],
    }

    # Migrate state.json
    state_file = workflow_dir / "state.json"
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            await workflow_repo.save_state(state_data)
            results["migrated_files"].append("state.json")
            logger.info("  Migrated: state.json")
        except Exception as e:
            results["errors"].append(f"state.json: {e}")
            logger.error(f"  Failed: state.json - {e}")

    # Migrate phase outputs
    for file_path, (phase, output_type) in FILE_TO_PHASE_OUTPUT.items():
        full_path = workflow_dir / file_path
        if full_path.exists():
            try:
                content = json.loads(full_path.read_text())
                await phase_repo.save(phase=phase, output_type=output_type, content=content)
                results["migrated_files"].append(file_path)
                logger.info(f"  Migrated: {file_path}")
            except Exception as e:
                results["errors"].append(f"{file_path}: {e}")
                logger.error(f"  Failed: {file_path} - {e}")
        else:
            results["skipped_files"].append(file_path)

    # Migrate task results (dynamic paths)
    task_results_dir = workflow_dir / "phases" / "implementation" / "task_results"
    if task_results_dir.exists():
        for task_file in task_results_dir.glob("*.json"):
            try:
                content = json.loads(task_file.read_text())
                task_id = task_file.stem
                await phase_repo.save(
                    phase=3,
                    output_type="task_result",
                    content=content,
                    task_id=task_id,
                )
                results["migrated_files"].append(f"task_results/{task_file.name}")
                logger.info(f"  Migrated: task_results/{task_file.name}")
            except Exception as e:
                results["errors"].append(f"task_results/{task_file.name}: {e}")
                logger.error(f"  Failed: task_results/{task_file.name} - {e}")

    # Migrate task verifications (dynamic paths)
    task_verify_dir = workflow_dir / "phases" / "task_verification"
    if task_verify_dir.exists():
        for verify_file in task_verify_dir.glob("*_verification.json"):
            try:
                content = json.loads(verify_file.read_text())
                task_id = verify_file.stem.replace("_verification", "")
                await phase_repo.save(
                    phase=4,
                    output_type="task_verification",
                    content=content,
                    task_id=task_id,
                )
                results["migrated_files"].append(f"task_verification/{verify_file.name}")
                logger.info(f"  Migrated: task_verification/{verify_file.name}")
            except Exception as e:
                results["errors"].append(f"task_verification/{verify_file.name}: {e}")
                logger.error(f"  Failed: task_verification/{verify_file.name} - {e}")

    # Migrate logs
    for file_path, log_type in FILE_TO_LOG.items():
        full_path = workflow_dir / file_path
        if full_path.exists():
            try:
                if file_path.endswith(".md"):
                    content = {"markdown": full_path.read_text()}
                else:
                    content = json.loads(full_path.read_text())
                await logs_repo.save(log_type=log_type, content=content)
                results["migrated_files"].append(file_path)
                logger.info(f"  Migrated: {file_path}")
            except Exception as e:
                results["errors"].append(f"{file_path}: {e}")
                logger.error(f"  Failed: {file_path} - {e}")
        else:
            results["skipped_files"].append(file_path)

    # Migrate research agent outputs
    research_dir = workflow_dir / "phases" / "research"
    if research_dir.exists():
        for research_file in research_dir.glob("*.json"):
            if research_file.name != "findings.json":  # Already handled above
                try:
                    content = json.loads(research_file.read_text())
                    agent_id = research_file.stem
                    await logs_repo.save(
                        log_type="research",
                        content={"agent_id": agent_id, "findings": content},
                    )
                    results["migrated_files"].append(f"research/{research_file.name}")
                    logger.info(f"  Migrated: research/{research_file.name}")
                except Exception as e:
                    results["errors"].append(f"research/{research_file.name}: {e}")
                    logger.error(f"  Failed: research/{research_file.name} - {e}")

    # Migrate approval responses
    approvals_dir = workflow_dir / "phases" / "approvals"
    if approvals_dir.exists():
        for approval_file in approvals_dir.glob("*.json"):
            try:
                content = json.loads(approval_file.read_text())
                if "context" in approval_file.name:
                    log_type = "approval_context"
                else:
                    log_type = "approval_response"
                await logs_repo.save(log_type=log_type, content=content)
                results["migrated_files"].append(f"approvals/{approval_file.name}")
                logger.info(f"  Migrated: approvals/{approval_file.name}")
            except Exception as e:
                results["errors"].append(f"approvals/{approval_file.name}: {e}")
                logger.error(f"  Failed: approvals/{approval_file.name} - {e}")

    # Summary
    if results["errors"]:
        results["status"] = "partial"

    logger.info(f"  Summary: {len(results['migrated_files'])} migrated, "
                f"{len(results['skipped_files'])} skipped, "
                f"{len(results['errors'])} errors")

    return results


def get_all_projects(conductor_root: Path) -> list[tuple[Path, str]]:
    """Get all projects in the projects/ directory.

    Args:
        conductor_root: Root directory of conductor

    Returns:
        List of (project_dir, project_name) tuples
    """
    projects_dir = conductor_root / "projects"
    if not projects_dir.exists():
        return []

    projects = []
    for item in projects_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            workflow_dir = item / ".workflow"
            if workflow_dir.exists():
                projects.append((item, item.name))

    return projects


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate .workflow/ file data to SurrealDB"
    )
    parser.add_argument(
        "project",
        nargs="?",
        help="Project name (for nested projects in projects/)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        help="Path to external project directory",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Migrate all projects in projects/ directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.project and not args.path and not args.all:
        parser.error("Must specify project name, --path, or --all")

    # Check database configuration
    try:
        require_db()
    except Exception as e:
        logger.error(f"Database not configured: {e}")
        logger.error("Set SURREAL_URL environment variable and try again.")
        sys.exit(1)

    conductor_root = Path(__file__).parent.parent

    # Determine projects to migrate
    projects_to_migrate = []

    if args.all:
        projects_to_migrate = get_all_projects(conductor_root)
        if not projects_to_migrate:
            logger.warning("No projects found with .workflow/ directories")
            sys.exit(0)
    elif args.path:
        project_dir = args.path.resolve()
        if not project_dir.exists():
            logger.error(f"Project directory not found: {project_dir}")
            sys.exit(1)
        project_name = project_dir.name
        projects_to_migrate = [(project_dir, project_name)]
    else:
        project_dir = conductor_root / "projects" / args.project
        if not project_dir.exists():
            logger.error(f"Project not found: {args.project}")
            sys.exit(1)
        projects_to_migrate = [(project_dir, args.project)]

    if args.dry_run:
        logger.info("DRY RUN - No changes will be made")
        for project_dir, project_name in projects_to_migrate:
            workflow_dir = project_dir / ".workflow"
            if workflow_dir.exists():
                files = list(workflow_dir.rglob("*.json")) + list(workflow_dir.rglob("*.md"))
                logger.info(f"\n{project_name}:")
                logger.info(f"  Would migrate {len(files)} files from {workflow_dir}")
        sys.exit(0)

    # Run migrations
    all_results = []
    for project_dir, project_name in projects_to_migrate:
        result = await migrate_project(project_dir, project_name)
        all_results.append(result)

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)

    total_migrated = 0
    total_errors = 0
    for result in all_results:
        status_icon = "✓" if result["status"] == "success" else "⚠" if result["status"] == "partial" else "○"
        logger.info(f"{status_icon} {result['project']}: {result['status']}")
        if result.get("migrated_files"):
            total_migrated += len(result["migrated_files"])
        if result.get("errors"):
            total_errors += len(result["errors"])
            for error in result["errors"]:
                logger.info(f"    Error: {error}")

    logger.info(f"\nTotal: {total_migrated} files migrated, {total_errors} errors")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
