"""Project Guardrails Setup Service.

Applies guardrails from the central collection to project folders.
Handles copying files, generating cursor rules, and updating agent context files.
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import CollectionItem, ItemType
from .service import CollectionService

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of applying guardrails to a project."""

    project_path: str
    items_applied: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    cursor_rules_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ProjectGuardrailsSetup:
    """Applies guardrails from collection to project folders.

    Creates:
    - .conductor/guardrails/ - Applied guardrail rules
    - .conductor/rules/ - Applied coding rules
    - .conductor/skills/ - Applied skills
    - .cursor/rules/ - Generated Cursor rules (.mdc files)
    - manifest.json - Tracks applied items and versions
    """

    def __init__(
        self,
        collection_service: Optional[CollectionService] = None,
    ):
        """Initialize project guardrails setup.

        Args:
            collection_service: Optional service instance
        """
        self.collection_service = collection_service or CollectionService()

    async def apply_guardrails(
        self,
        project_path: Path,
        items: list[CollectionItem],
        project_id: Optional[str] = None,
    ) -> ApplyResult:
        """Copy collection items to project .conductor/ folder.

        Args:
            project_path: Path to the project directory
            items: Collection items to apply
            project_id: Optional project identifier for DB tracking

        Returns:
            ApplyResult with details of what was created
        """
        project_path = Path(project_path)
        result = ApplyResult(project_path=str(project_path))

        # Create directory structure
        conductor_dir = project_path / ".conductor"
        directories = {
            "guardrails": conductor_dir / "guardrails",
            "rules": conductor_dir / "rules",
            "skills": conductor_dir / "skills",
        }

        for dir_path in directories.values():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Process each item
        rules_for_cursor = []

        for item in items:
            try:
                # Determine destination based on item type
                if item.item_type == ItemType.RULE:
                    # Rules go to rules/ or guardrails/ based on category
                    if item.category and "guardrail" in item.category.lower():
                        dest_dir = directories["guardrails"]
                    else:
                        dest_dir = directories["rules"]

                    # Copy file
                    dest_file = self._copy_item_file(item, dest_dir)
                    if dest_file:
                        result.files_created.append(str(dest_file))
                        result.items_applied.append(item.id)

                        # Track for cursor rule generation
                        rules_for_cursor.append(item)

                elif item.item_type == ItemType.SKILL:
                    # Skills go to skills/<skill-name>/
                    skill_dir = directories["skills"] / item.id
                    skill_dir.mkdir(parents=True, exist_ok=True)

                    # Copy skill file
                    dest_file = self._copy_item_file(item, skill_dir, "SKILL.md")
                    if dest_file:
                        result.files_created.append(str(dest_file))
                        result.items_applied.append(item.id)

                elif item.item_type == ItemType.TEMPLATE:
                    # Templates are for CLAUDE.md/GEMINI.md - handled separately
                    pass

            except Exception as e:
                error_msg = f"Failed to apply {item.name}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Generate cursor rules
        if rules_for_cursor:
            cursor_result = await self.generate_cursor_rules(project_path, rules_for_cursor)
            result.cursor_rules_created.extend(cursor_result)

        # Write manifest
        await self._write_manifest(project_path, items, result)

        logger.info(
            f"Applied {len(result.items_applied)} guardrails to {project_path}: "
            f"{len(result.files_created)} files, {len(result.cursor_rules_created)} cursor rules"
        )

        return result

    async def generate_cursor_rules(
        self,
        project_path: Path,
        rules: list[CollectionItem],
    ) -> list[str]:
        """Generate .cursor/rules/*.mdc files from collection rules.

        Args:
            project_path: Path to the project directory
            rules: Collection items of type RULE to convert

        Returns:
            List of created file paths
        """
        project_path = Path(project_path)
        cursor_rules_dir = project_path / ".cursor" / "rules"
        cursor_rules_dir.mkdir(parents=True, exist_ok=True)

        created_files = []

        for rule in rules:
            if rule.item_type != ItemType.RULE:
                continue

            try:
                # Generate .mdc filename
                mdc_filename = f"{rule.id}.mdc"
                mdc_path = cursor_rules_dir / mdc_filename

                # Format content as Cursor rule
                content = self._format_as_cursor_rule(rule)

                # Write file
                mdc_path.write_text(content, encoding="utf-8")
                created_files.append(str(mdc_path))

                logger.debug(f"Created cursor rule: {mdc_path}")

            except Exception as e:
                logger.error(f"Failed to create cursor rule for {rule.name}: {e}")

        return created_files

    async def update_agent_files(
        self,
        project_path: Path,
        template_items: Optional[list[CollectionItem]] = None,
    ) -> dict[str, str]:
        """Update CLAUDE.md/GEMINI.md with minimal template + pointers.

        If template items are provided, uses them as base.
        Otherwise, creates minimal pointer files.

        Args:
            project_path: Path to the project directory
            template_items: Optional template items to use

        Returns:
            Dict of created/updated files and their paths
        """
        project_path = Path(project_path)
        updated_files = {}

        agent_files = {
            "CLAUDE.md": "claude",
            "GEMINI.md": "gemini",
        }

        for filename, agent_type in agent_files.items():
            file_path = project_path / filename

            # Find matching template if provided
            template_content = None
            if template_items:
                for item in template_items:
                    if agent_type in item.name.lower():
                        template_content = item.content
                        break

            # Generate content
            if template_content:
                content = template_content
            else:
                content = self._generate_minimal_agent_file(agent_type, project_path)

            # Write file
            file_path.write_text(content, encoding="utf-8")
            updated_files[filename] = str(file_path)

            logger.debug(f"Updated agent file: {file_path}")

        return updated_files

    def _copy_item_file(
        self,
        item: CollectionItem,
        dest_dir: Path,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """Copy an item's file to destination directory.

        Args:
            item: Collection item to copy
            dest_dir: Destination directory
            filename: Optional custom filename

        Returns:
            Path to created file, or None if failed
        """
        if not item.file_path:
            logger.warning(f"No file path for item {item.id}")
            return None

        source_path = Path(item.file_path)
        if not source_path.exists():
            logger.warning(f"Source file not found: {source_path}")
            return None

        # Determine destination filename
        if filename:
            dest_filename = filename
        else:
            dest_filename = source_path.name

        dest_path = dest_dir / dest_filename

        try:
            shutil.copy2(source_path, dest_path)
            return dest_path
        except Exception as e:
            logger.error(f"Failed to copy {source_path} to {dest_path}: {e}")
            return None

    def _format_as_cursor_rule(self, rule: CollectionItem) -> str:
        """Format a rule as Cursor .mdc format.

        Args:
            rule: Collection rule item

        Returns:
            Formatted .mdc content
        """
        # Extract content, removing frontmatter if present
        content = rule.content or ""

        # Remove YAML frontmatter if present
        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx != -1:
                content = content[end_idx + 3 :].strip()

        # Build Cursor rule format
        mdc_content = f"""---
description: {rule.summary or rule.name}
globs:
alwaysApply: true
---

# {rule.name}

{content}
"""
        return mdc_content

    def _generate_minimal_agent_file(
        self,
        agent_type: str,
        project_path: Path,
    ) -> str:
        """Generate minimal agent context file with pointer to .conductor/.

        Args:
            agent_type: 'claude' or 'gemini'
            project_path: Project directory path

        Returns:
            Minimal agent file content
        """
        project_name = project_path.name

        if agent_type == "claude":
            return f"""# Claude Agent Context

You are working on the **{project_name}** project.

## Context Files

For detailed rules, guardrails, and skills, see:
- `.conductor/guardrails/` - Security and safety guidelines
- `.conductor/rules/` - Coding standards and conventions
- `.conductor/skills/` - Task-specific guidance

## Quick Reference

Read the files in `.conductor/` for this project's specific guidelines.
"""
        else:  # gemini
            return f"""# Gemini Agent Context

You are the **Architecture and Design Reviewer** for the **{project_name}** project.

## Context Files

For detailed rules, guardrails, and skills, see:
- `.conductor/guardrails/` - Security and safety guidelines
- `.conductor/rules/` - Coding standards and conventions
- `.conductor/skills/` - Task-specific guidance

## Quick Reference

Read the files in `.conductor/` for this project's specific guidelines.
"""

    async def _write_manifest(
        self,
        project_path: Path,
        items: list[CollectionItem],
        result: ApplyResult,
    ) -> None:
        """Write manifest.json tracking applied guardrails.

        Args:
            project_path: Project directory
            items: Items that were applied
            result: Apply result
        """
        manifest_path = project_path / ".conductor" / "manifest.json"

        manifest = {
            "version": "1.0.0",
            "applied_at": datetime.now().isoformat(),
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "type": item.item_type.value
                    if isinstance(item.item_type, ItemType)
                    else item.item_type,
                    "version": item.version,
                    "category": item.category,
                }
                for item in items
                if item.id in result.items_applied
            ],
            "files_created": result.files_created,
            "cursor_rules_created": result.cursor_rules_created,
        }

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.debug(f"Wrote manifest: {manifest_path}")


async def apply_guardrails_to_project(
    project_path: Path,
    items: list[CollectionItem],
) -> ApplyResult:
    """Convenience function to apply guardrails to a project.

    Args:
        project_path: Path to project directory
        items: Collection items to apply

    Returns:
        ApplyResult
    """
    setup = ProjectGuardrailsSetup()
    return await setup.apply_guardrails(project_path, items)
