#!/usr/bin/env python3
"""Bootstrap initial prompt versions into the database.

This script reads prompt templates from the orchestrator/agents/prompts/
directory and saves them as production prompt versions in SurrealDB.

Usage:
    python scripts/bootstrap_prompts.py --project <project-name>
    python scripts/bootstrap_prompts.py --project <project-name> --force

The --force flag will overwrite existing production versions.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Prompt template mappings: filename -> (agent, template_name)
PROMPT_MAPPINGS = {
    "claude_planning.md": ("claude", "planning"),
    "claude_implementation.md": ("claude", "implementation"),
    "claude_task.md": ("claude", "task"),
    "claude_tech_stack_research.md": ("claude", "tech_stack_research"),
    "claude_codebase_patterns_research.md": ("claude", "codebase_patterns_research"),
    "cursor_validation.md": ("cursor", "validation"),
    "cursor_code_review.md": ("cursor", "code_review"),
    "gemini_validation.md": ("gemini", "validation"),
    "gemini_architecture_review.md": ("gemini", "architecture_review"),
}

# Directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent.parent / "orchestrator" / "agents" / "prompts"


async def bootstrap_prompts(project_name: str, force: bool = False) -> dict:
    """Bootstrap initial prompt versions from template files.

    Reads prompt templates from orchestrator/agents/prompts/ and saves
    them as production versions in SurrealDB.

    Args:
        project_name: Project name for DB namespace
        force: If True, overwrite existing production versions

    Returns:
        Dict with counts: {"created": N, "skipped": N, "errors": N}
    """
    from orchestrator.db.repositories import (
        OptimizationMethod,
        PromptStatus,
        get_prompt_version_repository,
    )

    repo = get_prompt_version_repository(project_name)

    results = {"created": 0, "skipped": 0, "errors": 0}

    for filename, (agent, template_name) in PROMPT_MAPPINGS.items():
        filepath = PROMPTS_DIR / filename

        if not filepath.exists():
            logger.warning(f"Prompt file not found: {filepath}")
            results["errors"] += 1
            continue

        try:
            # Check if production version already exists
            existing = await repo.get_production_version(agent, template_name)

            if existing and not force:
                logger.info(f"Skipping {agent}/{template_name} - production version exists")
                results["skipped"] += 1
                continue

            # Read content from file
            content = filepath.read_text()

            # Determine version number
            if existing:
                version = existing.get("version", 0) + 1
            else:
                version = 1

            # Save as production version
            await repo.save_version(
                agent=agent,
                template_name=template_name,
                content=content,
                version=version,
                optimization_method=OptimizationMethod.MANUAL,
                status=PromptStatus.PRODUCTION,
                metrics={
                    "source": "bootstrap",
                    "file": filename,
                    "bootstrapped_at": asyncio.get_event_loop().time(),
                },
            )

            logger.info(f"Created {agent}/{template_name} v{version}")
            results["created"] += 1

        except Exception as e:
            logger.error(f"Failed to bootstrap {agent}/{template_name}: {e}")
            results["errors"] += 1

    return results


async def verify_bootstrap(project_name: str) -> bool:
    """Verify that bootstrap was successful.

    Args:
        project_name: Project name

    Returns:
        True if all required prompts exist
    """
    from orchestrator.db.repositories import get_prompt_version_repository

    repo = get_prompt_version_repository(project_name)

    required_prompts = [
        ("claude", "planning"),
        ("claude", "implementation"),
        ("cursor", "validation"),
        ("gemini", "validation"),
    ]

    for agent, template_name in required_prompts:
        version = await repo.get_production_version(agent, template_name)
        if not version:
            logger.error(f"Missing required prompt: {agent}/{template_name}")
            return False

    return True


async def list_versions(project_name: str) -> None:
    """List all prompt versions in the database.

    Args:
        project_name: Project name
    """
    from orchestrator.db.repositories import get_prompt_version_repository

    repo = get_prompt_version_repository(project_name)

    print(f"\nPrompt versions for project: {project_name}")
    print("-" * 60)

    for filename, (agent, template_name) in PROMPT_MAPPINGS.items():
        try:
            versions = await repo.get_by_template(agent, template_name)
            if versions:
                for v in versions:
                    status = v.get("status", "unknown")
                    version_num = v.get("version", 0)
                    method = v.get("optimization_method", "unknown")
                    print(f"  {agent}/{template_name} v{version_num} [{status}] ({method})")
            else:
                print(f"  {agent}/{template_name} - No versions")
        except Exception as e:
            print(f"  {agent}/{template_name} - Error: {e}")

    print("-" * 60)


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Bootstrap prompt versions into SurrealDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Bootstrap prompts for a project
    python scripts/bootstrap_prompts.py --project my-app

    # Overwrite existing production versions
    python scripts/bootstrap_prompts.py --project my-app --force

    # List all prompt versions
    python scripts/bootstrap_prompts.py --project my-app --list

    # Verify bootstrap was successful
    python scripts/bootstrap_prompts.py --project my-app --verify
        """,
    )
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing versions")
    parser.add_argument("--list", action="store_true", help="List all versions")
    parser.add_argument("--verify", action="store_true", help="Verify bootstrap")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.list:
        await list_versions(args.project)
        return

    if args.verify:
        success = await verify_bootstrap(args.project)
        if success:
            print("Bootstrap verification: PASSED")
            sys.exit(0)
        else:
            print("Bootstrap verification: FAILED")
            sys.exit(1)

    # Run bootstrap
    print(f"Bootstrapping prompts for project: {args.project}")
    results = await bootstrap_prompts(args.project, args.force)

    print("\nBootstrap complete:")
    print(f"  Created: {results['created']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Errors:  {results['errors']}")

    if results["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
