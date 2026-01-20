#!/usr/bin/env python3
"""Sync templates to projects.

This script updates project context files (CLAUDE.md, GEMINI.md, .cursor/rules)
from their templates, merging with any project-specific overrides.

Usage:
    python scripts/sync-project-templates.py --all
    python scripts/sync-project-templates.py --project my-auth-service
    python scripts/sync-project-templates.py --status
    python scripts/sync-project-templates.py --all --dry-run
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_root_dir() -> Path:
    """Get the meta-architect root directory."""
    script_dir = Path(__file__).parent
    return script_dir.parent.resolve()


def load_project_config(project_dir: Path) -> Optional[dict]:
    """Load project configuration.

    Args:
        project_dir: Path to project directory

    Returns:
        Config dict or None if not found
    """
    config_path = project_dir / ".project-config.json"
    if not config_path.exists():
        return None

    with open(config_path) as f:
        return json.load(f)


def save_project_config(project_dir: Path, config: dict) -> None:
    """Save project configuration.

    Args:
        project_dir: Path to project directory
        config: Config dict to save
    """
    config_path = project_dir / ".project-config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def load_template(template_dir: Path, agent: str) -> Optional[str]:
    """Load template content for an agent.

    Args:
        template_dir: Path to template directory
        agent: Agent name (claude, gemini, cursor)

    Returns:
        Template content or None if not found
    """
    if agent == "cursor":
        template_path = template_dir / ".cursor" / "rules.template"
    else:
        template_path = template_dir / f"{agent.upper()}.md.template"

    if not template_path.exists():
        return None

    return template_path.read_text()


def load_override(project_dir: Path, agent: str) -> str:
    """Load project-specific override for an agent.

    Args:
        project_dir: Path to project directory
        agent: Agent name (claude, gemini, cursor)

    Returns:
        Override content (empty string if not found)
    """
    override_path = project_dir / "project-overrides" / f"{agent}.md"
    if not override_path.exists():
        return ""

    content = override_path.read_text().strip()

    # Skip if it's just the default placeholder
    if content == f"# Project-Specific Rules for {agent.title()}\n\n<!-- Add project-specific rules here -->":
        return ""

    return content


def merge_template_with_override(template: str, override: str, project_name: str) -> str:
    """Merge template content with project override.

    Args:
        template: Template content
        override: Override content
        project_name: Project name for substitution

    Returns:
        Merged content
    """
    sync_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Perform substitutions
    content = template
    content = content.replace("{{PROJECT_NAME}}", project_name)
    content = content.replace("{{SYNC_DATE}}", sync_date)
    content = content.replace("{{CREATION_DATE}}", sync_date)

    # Add project overrides section
    if override:
        override_section = f"\n---\n\n# Project-Specific Rules\n\n{override}\n"
        content = content.replace("{{PROJECT_OVERRIDES}}", override_section)
    else:
        content = content.replace("{{PROJECT_OVERRIDES}}", "")

    return content


def get_agent_output_path(project_dir: Path, agent: str) -> Path:
    """Get output path for agent context file.

    Args:
        project_dir: Path to project directory
        agent: Agent name (claude, gemini, cursor)

    Returns:
        Path to output file
    """
    if agent == "cursor":
        return project_dir / ".cursor" / "rules"
    else:
        return project_dir / f"{agent.upper()}.md"


def sync_project(project_dir: Path, dry_run: bool = False) -> dict:
    """Sync templates to a single project.

    Args:
        project_dir: Path to project directory
        dry_run: If True, don't actually write files

    Returns:
        Dict with sync results
    """
    root_dir = get_root_dir()
    templates_dir = root_dir / "project-templates"

    # Load project config
    config = load_project_config(project_dir)
    if not config:
        return {
            "success": False,
            "error": f"No .project-config.json found in {project_dir}"
        }

    project_name = config.get("project_name", project_dir.name)
    template_name = config.get("template", "base")
    template_dir = templates_dir / template_name

    if not template_dir.exists():
        return {
            "success": False,
            "error": f"Template '{template_name}' not found"
        }

    results = {
        "project": project_name,
        "template": template_name,
        "files_updated": [],
        "files_unchanged": [],
        "errors": []
    }

    # Sync each agent's context file
    for agent in ["claude", "gemini", "cursor"]:
        template_content = load_template(template_dir, agent)
        if not template_content:
            results["errors"].append(f"No template found for {agent}")
            continue

        override_content = load_override(project_dir, agent)
        merged_content = merge_template_with_override(template_content, override_content, project_name)

        output_path = get_agent_output_path(project_dir, agent)

        # Check if content changed
        if output_path.exists():
            current_content = output_path.read_text()
            # Compare ignoring sync date (lines 4-5)
            current_lines = current_content.split('\n')
            merged_lines = merged_content.split('\n')

            # Remove sync date lines for comparison
            current_compare = [l for i, l in enumerate(current_lines) if not l.startswith("<!-- Last synced:")]
            merged_compare = [l for i, l in enumerate(merged_lines) if not l.startswith("<!-- Last synced:")]

            if current_compare == merged_compare:
                results["files_unchanged"].append(str(output_path.relative_to(project_dir)))
                continue

        if not dry_run:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(merged_content)

        results["files_updated"].append(str(output_path.relative_to(project_dir)))

    # Update config with sync timestamp
    if not dry_run and results["files_updated"]:
        config["last_synced"] = datetime.now().isoformat()
        save_project_config(project_dir, config)

    results["success"] = len(results["errors"]) == 0
    return results


def sync_all_projects(dry_run: bool = False) -> list:
    """Sync templates to all projects.

    Args:
        dry_run: If True, don't actually write files

    Returns:
        List of sync results for each project
    """
    root_dir = get_root_dir()
    projects_dir = root_dir / "projects"

    if not projects_dir.exists():
        print("No projects directory found.")
        return []

    projects = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]

    if not projects:
        print("No projects found.")
        return []

    results = []
    for project_dir in sorted(projects):
        result = sync_project(project_dir, dry_run)
        results.append(result)

    return results


def show_status() -> None:
    """Show sync status for all projects."""
    root_dir = get_root_dir()
    projects_dir = root_dir / "projects"

    if not projects_dir.exists():
        print("No projects directory found.")
        return

    projects = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]

    if not projects:
        print("No projects found.")
        return

    print("Project Sync Status:")
    print("-" * 60)

    for project_dir in sorted(projects):
        config = load_project_config(project_dir)
        if not config:
            print(f"  {project_dir.name}: No config file")
            continue

        project_name = config.get("project_name", project_dir.name)
        template = config.get("template", "unknown")
        last_synced = config.get("last_synced", "never")

        if last_synced != "never":
            last_synced = last_synced[:19].replace("T", " ")

        # Check for overrides
        overrides = []
        for agent in ["claude", "gemini", "cursor"]:
            override_content = load_override(project_dir, agent)
            if override_content:
                overrides.append(agent)

        override_str = f" (overrides: {', '.join(overrides)})" if overrides else ""

        print(f"  {project_name}:")
        print(f"    Template: {template}")
        print(f"    Last synced: {last_synced}")
        if override_str:
            print(f"    Overrides: {', '.join(overrides)}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Sync templates to projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/sync-project-templates.py --all
  python scripts/sync-project-templates.py --project my-auth-service
  python scripts/sync-project-templates.py --all --dry-run
  python scripts/sync-project-templates.py --status
        """
    )

    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Sync all projects"
    )
    parser.add_argument(
        "--project", "-p",
        help="Sync specific project"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show sync status for all projects"
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if not args.all and not args.project:
        parser.print_help()
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN - No changes will be made\n")

    if args.all:
        results = sync_all_projects(args.dry_run)
    else:
        root_dir = get_root_dir()
        project_dir = root_dir / "projects" / args.project
        if not project_dir.exists():
            print(f"Error: Project '{args.project}' not found")
            sys.exit(1)
        results = [sync_project(project_dir, args.dry_run)]

    # Print results
    success_count = 0
    for result in results:
        project = result.get("project", "unknown")
        if result.get("success"):
            success_count += 1
            updated = result.get("files_updated", [])
            unchanged = result.get("files_unchanged", [])

            if updated:
                print(f"[OK] {project}: {len(updated)} file(s) updated")
                for f in updated:
                    print(f"     - {f}")
            else:
                print(f"[OK] {project}: Already up to date")
        else:
            print(f"[ERR] {project}: {result.get('error', 'Unknown error')}")
            for err in result.get("errors", []):
                print(f"      - {err}")

    print()
    print(f"Summary: {success_count}/{len(results)} projects synced successfully")

    sys.exit(0 if success_count == len(results) else 1)


if __name__ == "__main__":
    main()
