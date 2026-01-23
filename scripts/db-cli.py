#!/usr/bin/env python3
"""SurrealDB CLI for Conductor.

Provides command-line operations for database management.

Usage:
    python scripts/db-cli.py status
    python scripts/db-cli.py migrate --project my-project --project-dir ./projects/my-project
    python scripts/db-cli.py migrate-all --projects-dir ./projects
    python scripts/db-cli.py query --project my-project "SELECT * FROM tasks"
    python scripts/db-cli.py stats --project my-project
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.db import (
    ensure_schema,
    get_audit_repository,
    get_budget_repository,
    get_config,
    get_connection,
    get_task_repository,
    get_workflow_repository,
    is_surrealdb_enabled,
)
from orchestrator.db.migrate import (
    MigrationResult,
    migrate_all_projects,
    migrate_budget,
    migrate_project,
    migrate_sessions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def cmd_status(args):
    """Show SurrealDB connection status."""
    print("\n=== SurrealDB Status ===\n")

    if not is_surrealdb_enabled():
        print("❌ SurrealDB is NOT enabled")
        print("   Set SURREAL_URL environment variable to enable")
        return 1

    config = get_config()
    print("✅ SurrealDB is enabled")
    print(f"   URL: {config.url}")
    print(f"   Namespace: {config.namespace}")
    print(f"   Default Database: {config.default_database}")
    print(f"   Environment: {config.environment.value}")
    print(f"   Secure: {config.is_secure}")
    print(f"   Pool Size: {config.pool_size}")
    print(f"   Live Queries: {config.enable_live_queries}")

    # Validate config
    errors = config.validate()
    if errors:
        print("\n⚠️  Configuration Warnings:")
        for error in errors:
            print(f"   - {error}")

    # Test connection
    print("\n📡 Testing connection...")
    try:
        async with get_connection() as conn:
            result = await conn.query("SELECT * FROM schema_version LIMIT 1")
            if result:
                version = result[0].get("version", "unknown")
                print(f"✅ Connected successfully (schema v{version})")
            else:
                print("✅ Connected successfully (no schema applied)")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    return 0


async def cmd_migrate(args):
    """Migrate a project from JSON to SurrealDB."""
    print(f"\n=== Migrating Project: {args.project} ===\n")

    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    project_dir = Path(args.project_dir) if args.project_dir else Path(f"./projects/{args.project}")

    if not project_dir.exists():
        print(f"❌ Project directory not found: {project_dir}")
        return 1

    print(f"Project: {args.project}")
    print(f"Directory: {project_dir}")
    print(f"Dry Run: {args.dry_run}")
    print()

    result = await migrate_project(args.project, project_dir, args.dry_run)
    print(result.summary())

    return 0 if result.success else 1


async def cmd_migrate_all(args):
    """Migrate all projects from JSON to SurrealDB."""
    print("\n=== Migrating All Projects ===\n")

    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    projects_dir = Path(args.projects_dir) if args.projects_dir else Path("./projects")

    if not projects_dir.exists():
        print(f"❌ Projects directory not found: {projects_dir}")
        return 1

    print(f"Projects Directory: {projects_dir}")
    print(f"Dry Run: {args.dry_run}")
    print()

    results = await migrate_all_projects(projects_dir, args.dry_run)

    success = True
    for name, result in results.items():
        print(f"\n{'='*50}")
        print(f"Project: {name}")
        print(result.summary())
        if not result.success:
            success = False

    return 0 if success else 1


async def cmd_query(args):
    """Execute a SurrealQL query."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Query: {args.project} ===\n")
    print(f"Query: {args.query}")
    print()

    try:
        # Ensure schema exists
        await ensure_schema(args.project)

        async with get_connection(args.project) as conn:
            results = await conn.query(args.query)
            print("Results:")
            print(json.dumps(results, indent=2, default=str))
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return 1

    return 0


async def cmd_stats(args):
    """Show project statistics from SurrealDB."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Statistics: {args.project} ===\n")

    try:
        # Workflow state
        workflow_repo = get_workflow_repository(args.project)
        summary = await workflow_repo.get_summary()
        print("Workflow State:")
        print(f"  Current Phase: {summary.get('current_phase', 'N/A')}")
        print(f"  Completed Phases: {summary.get('completed_phases', 0)}/5")
        print(f"  Iterations: {summary.get('iteration_count', 0)}")
        print(f"  Execution Mode: {summary.get('execution_mode', 'N/A')}")
        print()

        # Tasks
        task_repo = get_task_repository(args.project)
        progress = await task_repo.get_progress()
        print("Tasks:")
        print(f"  Total: {progress.get('total', 0)}")
        print(f"  Completed: {progress.get('completed', 0)}")
        print(f"  Pending: {progress.get('pending', 0)}")
        print(f"  Failed: {progress.get('failed', 0)}")
        print(f"  Completion Rate: {progress.get('completion_rate', 0):.1%}")
        print()

        # Audit
        audit_repo = get_audit_repository(args.project)
        audit_stats = await audit_repo.get_statistics()
        print("Audit Trail:")
        print(f"  Total Invocations: {audit_stats.total}")
        print(f"  Success Rate: {audit_stats.success_rate:.1%}")
        print(f"  Total Duration: {audit_stats.total_duration_seconds:.1f}s")
        print(f"  By Agent: {audit_stats.by_agent}")
        print()

        # Budget
        budget_repo = get_budget_repository(args.project)
        budget_summary = await budget_repo.get_summary()
        print("Budget:")
        print(f"  Total Cost: ${budget_summary.total_cost_usd:.4f}")
        print(
            f"  Total Tokens: {budget_summary.total_tokens_input + budget_summary.total_tokens_output:,}"
        )
        print(f"  By Agent: {budget_summary.by_agent}")

    except Exception as e:
        print(f"❌ Failed to get statistics: {e}")
        return 1

    return 0


async def cmd_init_schema(args):
    """Initialize schema for a project database."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Initializing Schema: {args.project} ===\n")

    try:
        success = await ensure_schema(args.project)
        if success:
            print(f"✅ Schema initialized for {args.project}")
        else:
            print("❌ Schema initialization failed")
            return 1
    except Exception as e:
        print(f"❌ Failed to initialize schema: {e}")
        return 1

    return 0


async def cmd_migrate_sessions(args):
    """Migrate session files to SurrealDB."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Migrating Sessions: {args.project} ===\n")

    project_dir = Path(args.project_dir) if args.project_dir else Path(f"./projects/{args.project}")
    sessions_dir = project_dir / ".workflow" / "sessions"

    if not sessions_dir.exists():
        print(f"❌ Sessions directory not found: {sessions_dir}")
        return 1

    result = MigrationResult()

    try:
        await ensure_schema(args.project)
        count = await migrate_sessions(args.project, sessions_dir, args.dry_run, result)
        print(f"✅ Migrated {count} sessions")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")
            return 1

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return 1

    return 0


async def cmd_migrate_budget(args):
    """Migrate budget data to SurrealDB."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Migrating Budget: {args.project} ===\n")

    project_dir = Path(args.project_dir) if args.project_dir else Path(f"./projects/{args.project}")
    budget_file = project_dir / ".workflow" / "budget.json"

    if not budget_file.exists():
        print(f"❌ Budget file not found: {budget_file}")
        return 1

    result = MigrationResult()

    try:
        await ensure_schema(args.project)
        count = await migrate_budget(args.project, budget_file, args.dry_run, result)
        print(f"✅ Migrated {count} budget records")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")
            return 1

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return 1

    return 0


async def cmd_validate(args):
    """Validate consistency between file and database storage."""
    if not is_surrealdb_enabled():
        print("❌ SurrealDB is not enabled")
        return 1

    print(f"\n=== Validating: {args.project} ===\n")

    project_dir = Path(args.project_dir) if args.project_dir else Path(f"./projects/{args.project}")
    workflow_dir = project_dir / ".workflow"

    if not workflow_dir.exists():
        print(f"❌ Workflow directory not found: {workflow_dir}")
        return 1

    errors = []
    warnings = []

    try:
        # Validate workflow state
        state_file = workflow_dir / "state.json"
        if state_file.exists():
            workflow_repo = get_workflow_repository(args.project)
            db_state = await workflow_repo.get_state()

            import json

            file_state = json.loads(state_file.read_text())

            if db_state:
                if db_state.current_phase != file_state.get("current_phase"):
                    warnings.append(
                        f"Phase mismatch: DB={db_state.current_phase}, File={file_state.get('current_phase')}"
                    )
                if db_state.iteration_count != file_state.get("iteration_count"):
                    warnings.append(
                        f"Iteration count mismatch: DB={db_state.iteration_count}, File={file_state.get('iteration_count')}"
                    )
                print("✅ Workflow state exists in both file and DB")
            else:
                warnings.append("Workflow state exists in file but not in DB")

        # Validate tasks
        if state_file.exists():
            task_repo = get_task_repository(args.project)
            db_tasks = await task_repo.get_all()

            file_tasks = json.loads(state_file.read_text()).get("tasks", [])

            if len(db_tasks) != len(file_tasks):
                warnings.append(f"Task count mismatch: DB={len(db_tasks)}, File={len(file_tasks)}")
            else:
                print(f"✅ Task count matches: {len(file_tasks)}")

        # Validate audit entries
        audit_file = workflow_dir / "audit" / "invocations.jsonl"
        if audit_file.exists():
            audit_repo = get_audit_repository(args.project)
            db_stats = await audit_repo.get_statistics()

            file_count = 0
            with open(audit_file) as f:
                for line in f:
                    if line.strip():
                        file_count += 1

            if db_stats.total != file_count:
                warnings.append(f"Audit count mismatch: DB={db_stats.total}, File={file_count}")
            else:
                print(f"✅ Audit entry count matches: {file_count}")

        # Validate budget
        budget_file = workflow_dir / "budget.json"
        if budget_file.exists():
            budget_repo = get_budget_repository(args.project)
            db_summary = await budget_repo.get_summary()

            file_budget = json.loads(budget_file.read_text())
            file_total = file_budget.get("total_spent_usd", 0.0)

            # Allow small floating point differences
            if abs(db_summary.total_cost_usd - file_total) > 0.001:
                warnings.append(
                    f"Budget total mismatch: DB=${db_summary.total_cost_usd:.4f}, File=${file_total:.4f}"
                )
            else:
                print(f"✅ Budget total matches: ${file_total:.4f}")

        # Print summary
        print()
        if errors:
            print("❌ Validation Errors:")
            for e in errors:
                print(f"  - {e}")
            return 1

        if warnings:
            print("⚠️  Validation Warnings:")
            for w in warnings:
                print(f"  - {w}")
        else:
            print("✅ All validations passed!")

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="SurrealDB CLI for Conductor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    status_parser = subparsers.add_parser("status", help="Show connection status")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Migrate a project")
    migrate_parser.add_argument("--project", "-p", required=True, help="Project name")
    migrate_parser.add_argument("--project-dir", "-d", help="Project directory")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Validate only")

    # migrate-all
    migrate_all_parser = subparsers.add_parser("migrate-all", help="Migrate all projects")
    migrate_all_parser.add_argument("--projects-dir", help="Projects directory")
    migrate_all_parser.add_argument("--dry-run", action="store_true", help="Validate only")

    # query
    query_parser = subparsers.add_parser("query", help="Execute a query")
    query_parser.add_argument("--project", "-p", required=True, help="Project name")
    query_parser.add_argument("query", help="SurrealQL query")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show project statistics")
    stats_parser.add_argument("--project", "-p", required=True, help="Project name")

    # init-schema
    init_parser = subparsers.add_parser("init-schema", help="Initialize database schema")
    init_parser.add_argument("--project", "-p", required=True, help="Project name")

    # migrate-sessions
    migrate_sessions_parser = subparsers.add_parser(
        "migrate-sessions", help="Migrate session files"
    )
    migrate_sessions_parser.add_argument("--project", "-p", required=True, help="Project name")
    migrate_sessions_parser.add_argument("--project-dir", "-d", help="Project directory")
    migrate_sessions_parser.add_argument("--dry-run", action="store_true", help="Validate only")

    # migrate-budget
    migrate_budget_parser = subparsers.add_parser("migrate-budget", help="Migrate budget data")
    migrate_budget_parser.add_argument("--project", "-p", required=True, help="Project name")
    migrate_budget_parser.add_argument("--project-dir", "-d", help="Project directory")
    migrate_budget_parser.add_argument("--dry-run", action="store_true", help="Validate only")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate file vs DB consistency")
    validate_parser.add_argument("--project", "-p", required=True, help="Project name")
    validate_parser.add_argument("--project-dir", "-d", help="Project directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run the appropriate command
    commands = {
        "status": cmd_status,
        "migrate": cmd_migrate,
        "migrate-all": cmd_migrate_all,
        "migrate-sessions": cmd_migrate_sessions,
        "migrate-budget": cmd_migrate_budget,
        "validate": cmd_validate,
        "query": cmd_query,
        "stats": cmd_stats,
        "init-schema": cmd_init_schema,
    }

    return asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
