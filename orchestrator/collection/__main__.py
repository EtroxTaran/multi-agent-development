"""Collection CLI commands.

Provides command-line interface for managing the collection:
- Sync filesystem to database
- List items
- Run gap analysis
- Copy items to projects
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .gap_analysis import GapAnalysisEngine
from .service import CollectionService


def main():
    """Main entry point for collection CLI."""
    parser = argparse.ArgumentParser(description="Manage the rules & skills collection")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync filesystem to database")
    sync_parser.add_argument(
        "--dir",
        type=Path,
        help="Collection directory (default: conductor/collection)",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List collection items")
    list_parser.add_argument("--type", choices=["rule", "skill", "template"])
    list_parser.add_argument("--tech", help="Filter by technology tag")
    list_parser.add_argument("--feature", help="Filter by feature tag")
    list_parser.add_argument("--priority", choices=["critical", "high", "medium", "low"])
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Gap analysis command
    gap_parser = subparsers.add_parser("gap-analysis", help="Run gap analysis for a project")
    gap_parser.add_argument("project", help="Project name or path")
    gap_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Copy command
    copy_parser = subparsers.add_parser("copy", help="Copy items to project")
    copy_parser.add_argument("project", help="Project name")
    copy_parser.add_argument("items", nargs="+", help="Item IDs to copy")

    # Tags command
    subparsers.add_parser("tags", help="List available tags")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the appropriate command
    if args.command == "sync":
        asyncio.run(cmd_sync(args))
    elif args.command == "list":
        asyncio.run(cmd_list(args))
    elif args.command == "gap-analysis":
        asyncio.run(cmd_gap_analysis(args))
    elif args.command == "copy":
        asyncio.run(cmd_copy(args))
    elif args.command == "tags":
        asyncio.run(cmd_tags())


async def cmd_sync(args):
    """Sync filesystem to database."""
    collection_dir = args.dir if hasattr(args, "dir") and args.dir else None
    service = CollectionService(collection_dir)

    print("Syncing collection to database...")
    result = await service.sync_from_filesystem()

    print(f"✓ Added: {result.items_added}")
    print(f"✓ Updated: {result.items_updated}")
    print(f"✓ Removed: {result.items_removed}")

    if result.errors:
        print("\n⚠ Errors:")
        for error in result.errors:
            print(f"  - {error}")


async def cmd_list(args):
    """List collection items."""
    service = CollectionService()

    technologies = [args.tech] if args.tech else None
    features = [args.feature] if args.feature else None

    items = await service.list_items(
        item_type=args.type,
        technologies=technologies,
        features=features,
        priority=args.priority,
    )

    if getattr(args, "json", False):
        print(json.dumps([item.to_dict() for item in items], indent=2))
    else:
        if not items:
            print("No items found.")
            return

        print(f"\n{'ID':<30} {'Type':<10} {'Priority':<10} {'Tags'}")
        print("-" * 80)
        for item in items:
            techs = ", ".join(item.tags.technology[:3])
            features = ", ".join(item.tags.feature[:3])
            print(f"{item.id:<30} {item.item_type.value:<10} {item.tags.priority:<10} {techs}")

        print(f"\nTotal: {len(items)} items")


async def cmd_gap_analysis(args):
    """Run gap analysis for a project."""
    # Determine project path
    project_path = Path(args.project)
    if not project_path.is_absolute():
        # Try to find in projects directory
        from ..project_manager import ProjectManager

        pm = ProjectManager(Path(__file__).parent.parent.parent)
        project_dir = pm.get_project(args.project)
        if project_dir:
            project_path = project_dir
        else:
            project_path = Path.cwd() / args.project

    if not project_path.exists():
        print(f"Error: Project path not found: {project_path}")
        sys.exit(1)

    service = CollectionService()
    engine = GapAnalysisEngine(service)

    print(f"Analyzing project: {project_path.name}")
    result = await engine.analyze_project(project_path)

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print("\n📋 Requirements Detected:")
        print(f"   Technologies: {', '.join(result.requirements.technologies) or 'None'}")
        print(f"   Features: {', '.join(result.requirements.features) or 'None'}")

        print(f"\n✓ Matching Collection Items ({len(result.matching_items)}):")
        for item in result.matching_items[:10]:
            print(f"   - {item.id}: {item.name} [{item.item_type.value}]")

        if result.gaps:
            print(f"\n⚠ Gaps Identified ({len(result.gaps)}):")
            for gap in result.gaps:
                print(f"   - [{gap.gap_type}] {gap.value}")
                print(f"     Research: {gap.recommended_research}")
        else:
            print("\n✓ No gaps found - full coverage!")


async def cmd_copy(args):
    """Copy items to project."""
    from ..project_manager import ProjectManager

    pm = ProjectManager(Path(__file__).parent.parent.parent)
    result = await pm.copy_collection_items_to_project(args.project, args.items)

    if result.get("success"):
        print(f"✓ Copied {len(result['items_copied'])} items to {args.project}")
        for file in result["files_created"]:
            print(f"   - {file}")
    else:
        print("⚠ Errors:")
        for error in result.get("errors", []):
            print(f"   - {error}")


async def cmd_tags():
    """List available tags."""
    service = CollectionService()
    tags = await service.get_available_tags()

    print("\n📌 Available Tags:\n")

    print("Technologies:")
    for tech in tags.get("technology", []):
        print(f"   - {tech}")

    print("\nFeatures:")
    for feature in tags.get("feature", []):
        print(f"   - {feature}")

    print("\nPriorities:")
    for priority in tags.get("priority", []):
        print(f"   - {priority}")


if __name__ == "__main__":
    main()
