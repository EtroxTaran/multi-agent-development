"""Context Injector for Agent Prompts.

Injects relevant guardrails, rules, and skills into agent prompts
based on project configuration and task context.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class InjectionContext:
    """Context to be injected into an agent prompt."""

    guardrails: list[str]
    rules: list[str]
    skills: list[str]
    total_items: int

    def to_markdown(self) -> str:
        """Format context as markdown for prompt injection.

        Returns:
            Formatted markdown string
        """
        sections = []

        if self.guardrails:
            sections.append("## Guardrails\n\n" + "\n\n---\n\n".join(self.guardrails))

        if self.rules:
            sections.append("## Coding Rules\n\n" + "\n\n---\n\n".join(self.rules))

        if self.skills:
            sections.append("## Skills\n\n" + "\n\n---\n\n".join(self.skills))

        if not sections:
            return ""

        return "# Project Context\n\n" + "\n\n".join(sections)


class ContextInjector:
    """Injects context from guardrails into agent prompts.

    Reads from project_guardrails table to find enabled items,
    then loads their content for injection.
    """

    def __init__(self, project_path: Optional[Path] = None):
        """Initialize context injector.

        Args:
            project_path: Optional project path for context
        """
        self.project_path = Path(project_path) if project_path else None

    async def get_injection_context(
        self,
        project_id: str,
        task_type: Optional[str] = None,
        agent_type: Optional[str] = None,
        delivery_method: str = "prompt",
    ) -> InjectionContext:
        """Build context to inject into agent prompt.

        Args:
            project_id: Project identifier
            task_type: Optional task type filter (implementation, testing, etc.)
            agent_type: Optional agent type filter (claude, gemini, cursor)
            delivery_method: Filter by delivery method ('prompt', 'both')

        Returns:
            InjectionContext with categorized content
        """
        guardrails = []
        rules = []
        skills = []

        try:
            async with get_connection(project_id) as conn:
                # Query enabled guardrails for this project
                query = """
                    SELECT * FROM project_guardrails
                    WHERE project_id = $project_id
                    AND enabled = true
                    AND (delivery_method = $method OR delivery_method = 'both')
                """
                params = {
                    "project_id": project_id,
                    "method": delivery_method,
                }

                results = await conn.query(query, params)

                if not results:
                    logger.debug(f"No enabled guardrails for project {project_id}")
                    return InjectionContext([], [], [], 0)

                # Load content for each item
                for record in results:
                    item_id = record.get("item_id")
                    item_type = record.get("item_type", "")
                    file_path = record.get("file_path")

                    # Try to load content from file
                    content = await self._load_item_content(file_path)
                    if not content:
                        # Fallback: try to load from collection
                        content = await self._load_from_collection(item_id)

                    if content:
                        # Categorize by type
                        if "guardrail" in item_type.lower():
                            guardrails.append(content)
                        elif "skill" in item_type.lower():
                            skills.append(content)
                        else:
                            rules.append(content)

        except Exception as e:
            logger.error(f"Failed to get injection context for {project_id}: {e}")

        total = len(guardrails) + len(rules) + len(skills)
        logger.debug(
            f"Loaded injection context: {len(guardrails)} guardrails, "
            f"{len(rules)} rules, {len(skills)} skills"
        )

        return InjectionContext(
            guardrails=guardrails,
            rules=rules,
            skills=skills,
            total_items=total,
        )

    async def build_agent_prompt(
        self,
        base_prompt: str,
        project_id: str,
        task_type: Optional[str] = None,
        agent_type: Optional[str] = None,
        inject_at_start: bool = True,
    ) -> str:
        """Build complete agent prompt with injected guardrails.

        Args:
            base_prompt: The original prompt to enhance
            project_id: Project identifier
            task_type: Optional task type for filtering
            agent_type: Optional agent type for filtering
            inject_at_start: If True, inject at start; else at end

        Returns:
            Enhanced prompt with injected context
        """
        context = await self.get_injection_context(
            project_id=project_id,
            task_type=task_type,
            agent_type=agent_type,
        )

        if context.total_items == 0:
            return base_prompt

        context_markdown = context.to_markdown()

        if inject_at_start:
            return f"{context_markdown}\n\n---\n\n{base_prompt}"
        else:
            return f"{base_prompt}\n\n---\n\n{context_markdown}"

    async def get_project_guardrails_summary(
        self,
        project_id: str,
    ) -> dict:
        """Get summary of guardrails applied to a project.

        Args:
            project_id: Project identifier

        Returns:
            Summary dict with counts and status
        """
        try:
            async with get_connection(project_id) as conn:
                # Count by type and status
                query = """
                    SELECT
                        item_type,
                        enabled,
                        count() as count
                    FROM project_guardrails
                    WHERE project_id = $project_id
                    GROUP BY item_type, enabled
                """
                results = await conn.query(query, {"project_id": project_id})

                summary = {
                    "project_id": project_id,
                    "total": 0,
                    "enabled": 0,
                    "disabled": 0,
                    "by_type": {},
                }

                for record in results:
                    item_type = record.get("item_type", "unknown")
                    enabled = record.get("enabled", False)
                    count = record.get("count", 0)

                    summary["total"] += count
                    if enabled:
                        summary["enabled"] += count
                    else:
                        summary["disabled"] += count

                    if item_type not in summary["by_type"]:
                        summary["by_type"][item_type] = {"enabled": 0, "disabled": 0}

                    if enabled:
                        summary["by_type"][item_type]["enabled"] += count
                    else:
                        summary["by_type"][item_type]["disabled"] += count

                return summary

        except Exception as e:
            logger.error(f"Failed to get guardrails summary: {e}")
            return {"project_id": project_id, "error": str(e)}

    async def _load_item_content(self, file_path: Optional[str]) -> Optional[str]:
        """Load content from a file path.

        Args:
            file_path: Path to the file

        Returns:
            File content or None
        """
        if not file_path:
            return None

        path = Path(file_path)
        if not path.exists():
            logger.debug(f"File not found: {file_path}")
            return None

        try:
            content = path.read_text(encoding="utf-8")
            # Remove YAML frontmatter if present
            if content.startswith("---"):
                end_idx = content.find("---", 3)
                if end_idx != -1:
                    content = content[end_idx + 3 :].strip()
            return content
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None

    async def _load_from_collection(self, item_id: str) -> Optional[str]:
        """Load content from collection service.

        Args:
            item_id: Collection item ID

        Returns:
            Item content or None
        """
        try:
            from .collection.service import CollectionService

            service = CollectionService()
            item = await service.get_item(item_id, include_content=True)
            return item.content if item else None
        except Exception as e:
            logger.debug(f"Failed to load from collection: {e}")
            return None


# Convenience functions


async def inject_context_into_prompt(
    prompt: str,
    project_id: str,
    task_type: Optional[str] = None,
) -> str:
    """Inject guardrails context into an agent prompt.

    Args:
        prompt: Original prompt
        project_id: Project identifier
        task_type: Optional task type

    Returns:
        Enhanced prompt
    """
    injector = ContextInjector()
    return await injector.build_agent_prompt(
        base_prompt=prompt,
        project_id=project_id,
        task_type=task_type,
    )
