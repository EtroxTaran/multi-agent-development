"""CLI for database migrations.

Usage:
    python -m orchestrator.db.migrations migrate --project my-app
    python -m orchestrator.db.migrations migrate --project my-app --dry-run
    python -m orchestrator.db.migrations rollback --project my-app --steps 1
    python -m orchestrator.db.migrations status --project my-app
    python -m orchestrator.db.migrations create add_new_feature
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from ..config import is_surrealdb_enabled, require_db
from .base import MigrationStatus
from .registry import get_registry
from .runner import MigrationRunner

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def cmd_migrate(args: argparse.Namespace) -> int:
    """Apply pending migrations."""
    runner = MigrationRunner(args.project)

    # Show pending first
    pending = await runner.get_pending_migrations()
    if not pending:
        print("No pending migrations")
        return 0

    print(f"Pending migrations: {len(pending)}")
    for m in pending:
        print(f"  - {m.full_name}")
    print()

    if args.dry_run:
        print("[DRY-RUN] Simulating migration...")
        print()

    result = await runner.apply(
        target_version=args.target,
        dry_run=args.dry_run,
    )

    if result.applied:
        prefix = "[DRY-RUN] Would apply" if args.dry_run else "Applied"
        print(f"{prefix} {len(result.applied)} migration(s):")
        for record in result.applied:
            time_str = f" ({record.execution_time_ms}ms)" if record.execution_time_ms else ""
            print(f"  + {record.version}_{record.name}{time_str}")

    if result.failed:
        print(f"\nFailed: {result.failed.version}_{result.failed.name}")
        print(f"  Error: {result.failed.error}")
        return 1

    return 0


async def cmd_rollback(args: argparse.Namespace) -> int:
    """Rollback applied migrations."""
    runner = MigrationRunner(args.project)

    if args.dry_run:
        print(f"[DRY-RUN] Simulating rollback of {args.steps} migration(s)...")
        print()

    result = await runner.rollback(
        steps=args.steps,
        dry_run=args.dry_run,
    )

    if result.applied:
        prefix = "[DRY-RUN] Would rollback" if args.dry_run else "Rolled back"
        print(f"{prefix} {len(result.applied)} migration(s):")
        for record in result.applied:
            time_str = f" ({record.execution_time_ms}ms)" if record.execution_time_ms else ""
            print(f"  - {record.version}_{record.name}{time_str}")

    if result.failed:
        print(f"\nFailed: {result.failed.version}_{result.failed.name}")
        print(f"  Error: {result.failed.error}")
        return 1

    if not result.applied and not result.failed:
        print("No migrations to rollback")

    return 0


async def cmd_status(args: argparse.Namespace) -> int:
    """Show migration status."""
    runner = MigrationRunner(args.project)
    records = await runner.get_status()

    if not records:
        print("No migrations found")
        return 0

    print(f"Migration status for project: {args.project}")
    print("-" * 60)

    for record in records:
        status_icon = {
            MigrationStatus.PENDING: "[ ]",
            MigrationStatus.APPLIED: "[x]",
            MigrationStatus.ROLLED_BACK: "[-]",
            MigrationStatus.FAILED: "[!]",
        }.get(record.status, "[?]")

        line = f"{status_icon} {record.version}_{record.name}"

        if record.status == MigrationStatus.APPLIED and record.applied_at:
            line += f" (applied: {record.applied_at.strftime('%Y-%m-%d %H:%M')})"
        elif record.status == MigrationStatus.ROLLED_BACK and record.rolled_back_at:
            line += f" (rolled back: {record.rolled_back_at.strftime('%Y-%m-%d %H:%M')})"
        elif record.status == MigrationStatus.FAILED and record.error:
            line += f" (error: {record.error[:50]}...)"

        print(line)

    print("-" * 60)

    # Summary
    applied = sum(1 for r in records if r.status == MigrationStatus.APPLIED)
    pending = sum(1 for r in records if r.status == MigrationStatus.PENDING)
    print(f"Total: {len(records)} | Applied: {applied} | Pending: {pending}")

    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new migration file."""
    registry = get_registry()
    versions = registry.get_versions()

    # Calculate next version
    if versions:
        last_version = max(int(v) for v in versions)
        next_version = str(last_version + 1).zfill(4)
    else:
        next_version = "0001"

    # Normalize name
    name = args.name.lower().replace("-", "_").replace(" ", "_")
    filename = f"m_{next_version}_{name}.py"

    # Get versions directory
    versions_dir = Path(__file__).parent / "versions"
    versions_dir.mkdir(exist_ok=True)

    filepath = versions_dir / filename

    if filepath.exists():
        print(f"Error: Migration file already exists: {filepath}")
        return 1

    # Generate template
    class_name = "".join(word.capitalize() for word in name.split("_"))
    template = dedent(f'''
        """Migration {next_version}: {name.replace("_", " ").title()}.

        TODO: Describe what this migration does.
        """

        from ..base import BaseMigration, MigrationContext


        class Migration{class_name}(BaseMigration):
            """TODO: Add description."""

            version = "{next_version}"
            name = "{name}"
            dependencies = ["{versions[-1] if versions else ""}"]  # Previous migration

            async def up(self, ctx: MigrationContext) -> None:
                """Apply the migration."""
                # TODO: Add migration logic
                # Example:
                # await ctx.execute("""
                #     DEFINE TABLE IF NOT EXISTS new_table SCHEMAFULL;
                #     DEFINE FIELD IF NOT EXISTS name ON TABLE new_table TYPE string;
                # """)
                pass

            async def down(self, ctx: MigrationContext) -> None:
                """Rollback the migration."""
                # TODO: Add rollback logic (or raise NotImplementedError)
                # Example:
                # await ctx.execute("REMOVE TABLE new_table")
                raise NotImplementedError("Rollback not implemented")
    ''').strip()

    filepath.write_text(template + "\n")
    print(f"Created migration: {filepath}")
    print(f"  Version: {next_version}")
    print(f"  Name: {name}")
    print()
    print("Edit the file to add your migration logic.")

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="SurrealDB migration management for Conductor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""
            Examples:
              # Apply all pending migrations
              python -m orchestrator.db.migrations migrate --project my-app

              # Dry run (preview changes)
              python -m orchestrator.db.migrations migrate --project my-app --dry-run

              # Rollback last migration
              python -m orchestrator.db.migrations rollback --project my-app

              # Rollback 3 migrations
              python -m orchestrator.db.migrations rollback --project my-app --steps 3

              # Check status
              python -m orchestrator.db.migrations status --project my-app

              # Create new migration
              python -m orchestrator.db.migrations create add_user_preferences
        """),
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply pending migrations",
    )
    migrate_parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project name",
    )
    migrate_parser.add_argument(
        "--target",
        help="Target version to migrate to",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )

    # rollback command
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Rollback applied migrations",
    )
    rollback_parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project name",
    )
    rollback_parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of migrations to rollback (default: 1)",
    )
    rollback_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show migration status",
    )
    status_parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project name",
    )

    # create command
    create_parser_cmd = subparsers.add_parser(
        "create",
        help="Create a new migration file",
    )
    create_parser_cmd.add_argument(
        "name",
        help="Migration name (e.g., add_user_preferences)",
    )

    return parser


async def async_main(args: argparse.Namespace) -> int:
    """Async main entry point."""
    # Check SurrealDB is configured (except for create command)
    if args.command != "create":
        if not is_surrealdb_enabled():
            print("Error: SurrealDB is not configured")
            print("Set SURREAL_URL environment variable")
            return 1

        try:
            require_db()
        except Exception as e:
            print(f"Error: {e}")
            return 1

    # Dispatch command
    if args.command == "migrate":
        return await cmd_migrate(args)
    elif args.command == "rollback":
        return await cmd_rollback(args)
    elif args.command == "status":
        return await cmd_status(args)
    elif args.command == "create":
        return cmd_create(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


def main() -> None:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
