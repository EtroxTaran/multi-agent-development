"""Context builder for agent consumption.

Transforms discovered documentation into structured context that agents can use.
Generates hierarchical indexes and ensures no information is lost.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Structured context for agent consumption.

    Provides categorized access to all documentation content
    with summaries and indexes for navigation.
    """

    # Quick reference
    summary: str = ""  # Executive summary
    index: str = ""  # Document index with categories

    # Categorized full content
    product_vision: str = ""
    architecture: str = ""
    requirements: str = ""
    user_stories: str = ""
    guides: str = ""
    api_reference: str = ""
    other_docs: str = ""

    # Extracted items
    acceptance_criteria: list[str] = field(default_factory=list)
    technical_decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    # Metadata
    document_count: int = 0
    total_content_size: int = 0
    categories_found: list[str] = field(default_factory=list)

    def for_planning(self) -> str:
        """Format context for planning agent.

        Returns full context with index for comprehensive planning.
        """
        sections = [
            "# PROJECT DOCUMENTATION CONTEXT",
            "",
            "## Document Index",
            self.index,
            "",
        ]

        if self.summary:
            sections.extend(
                [
                    "## Executive Summary",
                    self.summary,
                    "",
                ]
            )

        if self.product_vision:
            sections.extend(
                [
                    "## Product Vision",
                    self.product_vision,
                    "",
                ]
            )

        if self.architecture:
            sections.extend(
                [
                    "## Architecture",
                    self.architecture,
                    "",
                ]
            )

        if self.requirements:
            sections.extend(
                [
                    "## Requirements",
                    self.requirements,
                    "",
                ]
            )

        if self.user_stories:
            sections.extend(
                [
                    "## User Stories",
                    self.user_stories,
                    "",
                ]
            )

        if self.acceptance_criteria:
            sections.extend(
                [
                    "## Acceptance Criteria",
                    "",
                ]
            )
            for i, criterion in enumerate(self.acceptance_criteria, 1):
                sections.append(f"{i}. {criterion}")
            sections.append("")

        if self.constraints:
            sections.extend(
                [
                    "## Technical Constraints",
                    "",
                ]
            )
            for constraint in self.constraints:
                sections.append(f"- {constraint}")
            sections.append("")

        if self.guides:
            sections.extend(
                [
                    "## Development Guides",
                    self.guides,
                    "",
                ]
            )

        if self.other_docs:
            sections.extend(
                [
                    "## Other Documentation",
                    self.other_docs,
                    "",
                ]
            )

        return "\n".join(sections)

    def for_implementation(self, task_description: str = "") -> str:
        """Format context for implementation agent.

        Returns focused context relevant to a specific task.
        """
        sections = [
            "# IMPLEMENTATION CONTEXT",
            "",
        ]

        # Always include architecture for implementation
        if self.architecture:
            sections.extend(
                [
                    "## Architecture Reference",
                    self.architecture[:5000]
                    if len(self.architecture) > 5000
                    else self.architecture,
                    "",
                ]
            )

        # Include relevant constraints
        if self.constraints:
            sections.extend(
                [
                    "## Technical Constraints",
                    "",
                ]
            )
            for constraint in self.constraints:
                sections.append(f"- {constraint}")
            sections.append("")

        # Include guides
        if self.guides:
            sections.extend(
                [
                    "## Development Guides",
                    self.guides[:3000] if len(self.guides) > 3000 else self.guides,
                    "",
                ]
            )

        return "\n".join(sections)

    def for_task_context(self, task_keywords: list[str]) -> str:
        """Format context for a specific task based on keywords.

        Args:
            task_keywords: Keywords to filter relevant content

        Returns:
            Focused context string
        """
        # Build relevant context based on keywords
        relevant_parts = []

        keywords_lower = [k.lower() for k in task_keywords]

        # Check each content section
        if self.product_vision and any(k in self.product_vision.lower() for k in keywords_lower):
            relevant_parts.append(f"## Relevant Product Context\n{self.product_vision[:2000]}")

        if self.requirements and any(k in self.requirements.lower() for k in keywords_lower):
            relevant_parts.append(f"## Relevant Requirements\n{self.requirements[:2000]}")

        if self.architecture and any(k in self.architecture.lower() for k in keywords_lower):
            relevant_parts.append(f"## Relevant Architecture\n{self.architecture[:2000]}")

        # Always include relevant constraints
        if self.constraints:
            relevant_parts.append(
                "## Technical Constraints\n" + "\n".join(f"- {c}" for c in self.constraints)
            )

        # Filter relevant acceptance criteria
        relevant_criteria = [
            ac for ac in self.acceptance_criteria if any(k in ac.lower() for k in keywords_lower)
        ]
        if relevant_criteria:
            relevant_parts.append(
                "## Related Acceptance Criteria\n" + "\n".join(f"- {c}" for c in relevant_criteria)
            )

        return (
            "\n\n".join(relevant_parts)
            if relevant_parts
            else "No specific context found for keywords."
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "summary": self.summary,
            "index": self.index,
            "product_vision": self.product_vision,
            "architecture": self.architecture,
            "requirements": self.requirements,
            "user_stories": self.user_stories,
            "guides": self.guides,
            "api_reference": self.api_reference,
            "other_docs": self.other_docs,
            "acceptance_criteria": self.acceptance_criteria,
            "technical_decisions": self.technical_decisions,
            "constraints": self.constraints,
            "document_count": self.document_count,
            "total_content_size": self.total_content_size,
            "categories_found": self.categories_found,
        }


def build_agent_context(project_dir: Path, project_name: str = "") -> AgentContext:
    """Build structured agent context from discovered documentation.

    Args:
        project_dir: Project directory path
        project_name: Project name for logging

    Returns:
        AgentContext with all categorized content
    """
    from .doc_context import load_documentation_context

    project_dir = Path(project_dir)
    context = AgentContext()

    # Load discovered documentation
    doc_result = load_documentation_context(project_dir, project_name)

    if doc_result["source"] in ("none", "error"):
        logger.warning(f"No documentation found for {project_name or project_dir}")
        return context

    # Build document index
    index_lines = ["| Category | Document | Path |", "|----------|----------|------|"]
    categories_content: dict[str, list[str]] = {
        "product_vision": [],
        "architecture": [],
        "requirements": [],
        "user_stories": [],
        "guides": [],
        "api_reference": [],
        "other": [],
    }

    categories_found = set()

    for doc in doc_result.get("documents", []):
        category = doc.get("category", "other")
        title = doc.get("title", doc.get("path", "Unknown"))
        path = doc.get("path", "")
        content = doc.get("content", "")

        # Add to index
        index_lines.append(f"| {category} | {title} | {path} |")
        categories_found.add(category)

        # Categorize content
        if category in categories_content:
            categories_content[category].append(f"### {title}\n\n{content}")
        else:
            categories_content["other"].append(f"### {title}\n\n{content}")

        context.document_count += 1
        context.total_content_size += len(content)

    # Build context sections
    context.index = "\n".join(index_lines)
    context.categories_found = list(categories_found)

    context.product_vision = "\n\n---\n\n".join(categories_content["product_vision"])
    context.architecture = "\n\n---\n\n".join(categories_content["architecture"])
    context.requirements = "\n\n---\n\n".join(categories_content["requirements"])
    context.user_stories = "\n\n---\n\n".join(categories_content["user_stories"])
    context.guides = "\n\n---\n\n".join(categories_content["guides"])
    context.api_reference = "\n\n---\n\n".join(categories_content["api_reference"])
    context.other_docs = "\n\n---\n\n".join(categories_content["other"])

    # Get extracted items from discovery
    context.acceptance_criteria = doc_result.get("acceptance_criteria", [])

    # Generate executive summary
    context.summary = _generate_summary(doc_result, context)

    # Extract constraints from content
    context.constraints = _extract_constraints(context)

    logger.info(
        f"Built agent context: {context.document_count} docs, "
        f"{context.total_content_size} chars, {len(context.categories_found)} categories"
    )

    return context


def _generate_summary(doc_result: dict, context: AgentContext) -> str:
    """Generate executive summary from documentation.

    Args:
        doc_result: Raw discovery result
        context: Partially built context

    Returns:
        Executive summary string
    """
    parts = []

    # Product vision summary
    if doc_result.get("product_vision"):
        vision = doc_result["product_vision"]
        # Take first paragraph or first 500 chars
        first_para = vision.split("\n\n")[0] if "\n\n" in vision else vision[:500]
        parts.append(f"**Product Vision:** {first_para}")

    # Architecture summary
    if doc_result.get("architecture_summary"):
        arch = doc_result["architecture_summary"]
        first_para = arch.split("\n\n")[0] if "\n\n" in arch else arch[:500]
        parts.append(f"**Architecture:** {first_para}")

    # Document coverage
    parts.append(
        f"**Documentation Coverage:** {context.document_count} documents across "
        f"{len(context.categories_found)} categories ({', '.join(context.categories_found)})"
    )

    # Acceptance criteria count
    if context.acceptance_criteria:
        parts.append(f"**Acceptance Criteria:** {len(context.acceptance_criteria)} items defined")

    return "\n\n".join(parts)


def _extract_constraints(context: AgentContext) -> list[str]:
    """Extract technical constraints from content.

    Args:
        context: Agent context with content

    Returns:
        List of constraint strings
    """
    import re

    constraints = []

    # Search in all content sections
    all_content = "\n".join(
        [
            context.product_vision,
            context.architecture,
            context.requirements,
            context.guides,
        ]
    )

    # Look for constraint patterns
    patterns = [
        r"(?:must|shall|should|required to)\s+(?:use|implement|follow|support)\s+(.+?)(?:\.|$)",
        r"constraint[s]?:\s*(.+?)(?:\n|$)",
        r"requirement[s]?:\s*(.+?)(?:\n|$)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, all_content, re.IGNORECASE | re.MULTILINE)
        constraints.extend(matches)

    # Also look for bullet points after "constraints" heading
    constraint_section = re.search(
        r"#+\s*(?:Technical\s+)?Constraints?\s*\n((?:[-*]\s*.+\n?)+)", all_content, re.IGNORECASE
    )
    if constraint_section:
        bullets = re.findall(r"[-*]\s*(.+)", constraint_section.group(1))
        constraints.extend(bullets)

    # Deduplicate and clean
    seen = set()
    unique_constraints = []
    for c in constraints:
        c_clean = c.strip()
        if c_clean and c_clean.lower() not in seen:
            seen.add(c_clean.lower())
            unique_constraints.append(c_clean)

    return unique_constraints[:20]  # Limit to 20 most important


def generate_context_index_file(project_dir: Path, project_name: str = "") -> Optional[Path]:
    """Generate context index file for agent navigation.

    Creates a persistent index file that agents can reference.

    Args:
        project_dir: Project directory path
        project_name: Project name

    Returns:
        Path to generated index file, or None if no docs
    """
    context = build_agent_context(project_dir, project_name)

    if context.document_count == 0:
        logger.warning("Cannot generate context index - no documentation found")
        return None

    # Build index content
    lines = [
        "# Project Documentation Index",
        "",
        f"> Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> **{context.document_count}** documents | **{context.total_content_size:,}** characters",
        "",
        "## Executive Summary",
        "",
        context.summary,
        "",
        "## Document Map",
        "",
        context.index,
        "",
    ]

    if context.acceptance_criteria:
        lines.extend(
            [
                "## Acceptance Criteria",
                "",
            ]
        )
        for i, criterion in enumerate(context.acceptance_criteria, 1):
            lines.append(f"{i}. [ ] {criterion}")
        lines.append("")

    if context.constraints:
        lines.extend(
            [
                "## Technical Constraints",
                "",
            ]
        )
        for constraint in context.constraints:
            lines.append(f"- {constraint}")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "*This file is auto-generated from the docs/ folder. Do not edit manually.*",
        ]
    )

    # Write to .workflow directory
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    index_file = workflow_dir / "context_index.md"

    index_file.write_text("\n".join(lines))
    logger.info(f"Generated context index: {index_file}")

    return index_file
