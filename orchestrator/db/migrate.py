"""Migration utility for moving from JSON files to SurrealDB.

Migrates existing workflow data from file-based storage to SurrealDB.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .config import is_surrealdb_enabled
from .repositories import (
    get_audit_repository,
    get_budget_repository,
    get_checkpoint_repository,
    get_session_repository,
    get_task_repository,
    get_workflow_repository,
)
from .schema import ensure_schema

logger = logging.getLogger(__name__)


class MigrationResult:
    """Result of a migration operation."""

    def __init__(self):
        self.success = True
        self.migrated = {
            "workflow_state": 0,
            "tasks": 0,
            "audit_entries": 0,
            "checkpoints": 0,
            "sessions": 0,
            "budget_records": 0,
        }
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, error: str) -> None:
        """Add an error and mark as failed."""
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """Add a warning."""
        self.warnings.append(warning)

    def summary(self) -> str:
        """Get migration summary."""
        lines = ["Migration Result:"]
        lines.append(f"  Success: {self.success}")
        lines.append("  Migrated:")
        for entity, count in self.migrated.items():
            lines.append(f"    - {entity}: {count}")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
            for w in self.warnings[:5]:
                lines.append(f"    - {w}")
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"    - {e}")
        return "\n".join(lines)


async def migrate_project(
    project_name: str,
    project_dir: Path,
    dry_run: bool = False,
) -> MigrationResult:
    """Migrate a project from JSON files to SurrealDB.

    Args:
        project_name: Project name
        project_dir: Project directory path
        dry_run: If True, only validate without migrating

    Returns:
        MigrationResult with details
    """
    result = MigrationResult()
    workflow_dir = project_dir / ".workflow"

    if not workflow_dir.exists():
        result.add_warning(f"No .workflow directory found in {project_dir}")
        return result

    if not is_surrealdb_enabled():
        result.add_error("SurrealDB is not enabled (SURREAL_URL not set)")
        return result

    if not dry_run:
        # Ensure schema is applied
        try:
            await ensure_schema(project_name)
        except Exception as e:
            result.add_error(f"Failed to apply schema: {e}")
            return result

    # Migrate workflow state
    state_file = workflow_dir / "state.json"
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            if not dry_run:
                repo = get_workflow_repository(project_name)
                await repo.initialize_state(
                    project_dir=str(project_dir),
                    execution_mode=state_data.get("execution_mode", "afk"),
                )
                # Update with full state
                await repo.update_state(
                    **{
                        k: v
                        for k, v in state_data.items()
                        if k not in ("project_name", "project_dir", "created_at")
                    }
                )
            result.migrated["workflow_state"] = 1
            logger.info(f"Migrated workflow state for {project_name}")
        except Exception as e:
            result.add_error(f"Failed to migrate workflow state: {e}")

    # Migrate tasks from state
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            tasks = state_data.get("tasks", [])
            if tasks and not dry_run:
                repo = get_task_repository(project_name)
                for task in tasks:
                    await repo.create_task(
                        task_id=task.get("id", ""),
                        title=task.get("title", ""),
                        user_story=task.get("user_story", ""),
                        acceptance_criteria=task.get("acceptance_criteria", []),
                        dependencies=task.get("dependencies", []),
                        priority=task.get("priority", "medium"),
                        milestone_id=task.get("milestone_id"),
                        estimated_complexity=task.get("estimated_complexity", "medium"),
                        files_to_create=task.get("files_to_create", []),
                        files_to_modify=task.get("files_to_modify", []),
                        test_files=task.get("test_files", []),
                        max_attempts=task.get("max_attempts", 3),
                    )
                    # Set status if not pending
                    if task.get("status") != "pending":
                        await repo.set_status(
                            task.get("id", ""),
                            task.get("status", "pending"),
                            task.get("error"),
                        )
            result.migrated["tasks"] = len(tasks)
            logger.info(f"Migrated {len(tasks)} tasks for {project_name}")
        except Exception as e:
            result.add_error(f"Failed to migrate tasks: {e}")

    # Migrate audit trail from JSONL
    audit_file = workflow_dir / "audit" / "invocations.jsonl"
    if audit_file.exists():
        try:
            count = 0
            repo = get_audit_repository(project_name) if not dry_run else None

            with open(audit_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry_data = json.loads(line)
                        if not dry_run and repo:
                            # Create entry (simplified - full entry creation would need more fields)
                            entry = await repo.create_entry(
                                agent=entry_data.get("agent", "unknown"),
                                task_id=entry_data.get("task_id", ""),
                                prompt="[migrated]",  # Original prompt not stored
                                session_id=entry_data.get("session_id"),
                                metadata=entry_data.get("metadata", {}),
                            )
                            # Update with result data
                            await repo.update_result(
                                entry.id,
                                success=entry_data.get("status") == "success",
                                exit_code=entry_data.get("exit_code", 0),
                                duration_seconds=entry_data.get("duration_seconds", 0),
                                output_length=entry_data.get("output_length", 0),
                                error_length=entry_data.get("error_length", 0),
                                cost_usd=entry_data.get("cost_usd"),
                                model=entry_data.get("model"),
                            )
                        count += 1
                    except json.JSONDecodeError:
                        result.add_warning("Skipped invalid JSON line in audit log")

            result.migrated["audit_entries"] = count
            logger.info(f"Migrated {count} audit entries for {project_name}")
        except Exception as e:
            result.add_error(f"Failed to migrate audit trail: {e}")

    # Migrate checkpoints
    checkpoints_dir = workflow_dir / "checkpoints"
    if checkpoints_dir.exists():
        try:
            count = 0
            repo = get_checkpoint_repository(project_name) if not dry_run else None

            index_file = checkpoints_dir / "index.json"
            if index_file.exists():
                index = json.loads(index_file.read_text())
                for checkpoint_id, meta in index.items():
                    checkpoint_file = checkpoints_dir / checkpoint_id / "checkpoint.json"
                    if checkpoint_file.exists():
                        try:
                            checkpoint_data = json.loads(checkpoint_file.read_text())
                            if not dry_run and repo:
                                await repo.create_checkpoint(
                                    name=checkpoint_data.get("name", ""),
                                    state_snapshot=checkpoint_data.get("state_snapshot", {}),
                                    phase=checkpoint_data.get("phase", 0),
                                    notes=checkpoint_data.get("notes", ""),
                                    task_progress=checkpoint_data.get("task_progress", {}),
                                    files_snapshot=checkpoint_data.get("files_snapshot", []),
                                )
                            count += 1
                        except Exception as e:
                            result.add_warning(f"Failed to migrate checkpoint {checkpoint_id}: {e}")

            result.migrated["checkpoints"] = count
            logger.info(f"Migrated {count} checkpoints for {project_name}")
        except Exception as e:
            result.add_error(f"Failed to migrate checkpoints: {e}")

    # Migrate sessions
    sessions_dir = workflow_dir / "sessions"
    if sessions_dir.exists():
        count = await migrate_sessions(project_name, sessions_dir, dry_run, result)
        result.migrated["sessions"] = count

    # Migrate budget
    budget_file = workflow_dir / "budget.json"
    if budget_file.exists():
        count = await migrate_budget(project_name, budget_file, dry_run, result)
        result.migrated["budget_records"] = count

    return result


async def migrate_sessions(
    project_name: str,
    sessions_dir: Path,
    dry_run: bool,
    result: MigrationResult,
) -> int:
    """Migrate session files to SurrealDB.

    Args:
        project_name: Project name
        sessions_dir: Directory containing session JSON files
        dry_run: If True, only validate
        result: MigrationResult to update

    Returns:
        Number of sessions migrated
    """
    count = 0

    try:
        repo = get_session_repository(project_name) if not dry_run else None

        for session_file in sessions_dir.glob("*.json"):
            try:
                session_data = json.loads(session_file.read_text())

                if not dry_run and repo:
                    # Create session
                    session = await repo.create_session(
                        session_id=session_data.get("session_id", ""),
                        task_id=session_data.get("task_id", session_file.stem),
                        agent=session_data.get("agent", "claude"),
                    )

                    # Update with iteration count if available
                    iteration = session_data.get("iteration", 1)
                    for _ in range(iteration - 1):
                        await repo.record_invocation(session.id, 0.0)

                    # Close if marked as inactive
                    if not session_data.get("is_active", True):
                        await repo.close_session(session.id)

                count += 1
            except json.JSONDecodeError:
                result.add_warning(f"Invalid JSON in session file: {session_file.name}")
            except Exception as e:
                result.add_warning(f"Failed to migrate session {session_file.name}: {e}")

        logger.info(f"Migrated {count} sessions for {project_name}")

    except Exception as e:
        result.add_error(f"Failed to migrate sessions: {e}")

    return count


async def migrate_budget(
    project_name: str,
    budget_file: Path,
    dry_run: bool,
    result: MigrationResult,
) -> int:
    """Migrate budget data to SurrealDB.

    Args:
        project_name: Project name
        budget_file: Path to budget.json
        dry_run: If True, only validate
        result: MigrationResult to update

    Returns:
        Number of budget records migrated
    """
    count = 0

    try:
        budget_data = json.loads(budget_file.read_text())
        records = budget_data.get("records", [])

        if not dry_run and records:
            repo = get_budget_repository(project_name)

            for record in records:
                try:
                    await repo.record_spend(
                        agent=record.get("agent", "unknown"),
                        cost_usd=record.get("amount_usd", 0.0),
                        task_id=record.get("task_id"),
                        tokens_input=record.get("prompt_tokens"),
                        tokens_output=record.get("completion_tokens"),
                        model=record.get("model"),
                    )
                    count += 1
                except Exception as e:
                    result.add_warning(f"Failed to migrate budget record: {e}")

        logger.info(f"Migrated {count} budget records for {project_name}")

    except json.JSONDecodeError:
        result.add_warning("Invalid JSON in budget file")
    except Exception as e:
        result.add_error(f"Failed to migrate budget: {e}")

    return count


async def migrate_all_projects(
    projects_dir: Path,
    dry_run: bool = False,
) -> dict[str, MigrationResult]:
    """Migrate all projects in the projects directory.

    Args:
        projects_dir: Path to projects/ directory
        dry_run: If True, only validate

    Returns:
        Dictionary mapping project name to MigrationResult
    """
    results = {}

    if not projects_dir.exists():
        logger.warning(f"Projects directory not found: {projects_dir}")
        return results

    for project_path in projects_dir.iterdir():
        if not project_path.is_dir():
            continue
        if project_path.name.startswith("."):
            continue

        project_name = project_path.name
        logger.info(f"Migrating project: {project_name}")

        result = await migrate_project(project_name, project_path, dry_run)
        results[project_name] = result

        if not result.success:
            logger.error(f"Migration failed for {project_name}")
        else:
            logger.info(f"Migration completed for {project_name}")

    return results


def run_migration(
    project_name: Optional[str] = None,
    project_dir: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    """Run migration from command line.

    Args:
        project_name: Single project to migrate
        project_dir: Project directory (if not in projects/)
        projects_dir: Projects directory for bulk migration
        dry_run: If True, only validate
    """

    async def _run():
        if project_name and project_dir:
            result = await migrate_project(project_name, project_dir, dry_run)
            print(result.summary())
        elif projects_dir:
            results = await migrate_all_projects(projects_dir, dry_run)
            for name, result in results.items():
                print(f"\n{'='*50}")
                print(f"Project: {name}")
                print(result.summary())
        else:
            print("Usage: Provide either project_name+project_dir or projects_dir")

    asyncio.run(_run())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate from JSON to SurrealDB")
    parser.add_argument("--project", "-p", help="Project name")
    parser.add_argument("--project-dir", "-d", type=Path, help="Project directory")
    parser.add_argument("--projects-dir", type=Path, help="Projects directory for bulk migration")
    parser.add_argument("--dry-run", action="store_true", help="Validate only")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    run_migration(
        project_name=args.project,
        project_dir=args.project_dir,
        projects_dir=args.projects_dir,
        dry_run=args.dry_run,
    )
