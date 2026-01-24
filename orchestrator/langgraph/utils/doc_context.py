"""Documentation context utilities.

Provides functions to load documentation context from the discovery system.
The docs/ folder is the ONLY source of documentation - there is no fallback.

If agents need a summary, this module can generate one from discovered docs.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Path where auto-generated context summary is saved
CONTEXT_SUMMARY_FILENAME = "context_summary.md"


def load_documentation_context(
    project_dir: Path,
    project_name: str = "",
) -> dict[str, Any]:
    """Load documentation context from docs/ folder.

    The docs/ folder is the ONLY source of documentation.
    There is NO fallback to PRODUCT.md or any other single file.

    Priority:
    1. File cache (.workflow/phases/0/discovered_context.json)
    2. Direct discovery (runs DocumentationScanner on docs/ folder)

    Args:
        project_dir: Path to project directory
        project_name: Project name (for logging)

    Returns:
        Dict with keys:
        - content: Combined documentation text for prompts
        - documents: List of discovered documents
        - source: Where the content came from
        - acceptance_criteria: Extracted acceptance criteria
        - product_vision: Product vision text if found
        - architecture_summary: Architecture summary if found
    """
    project_dir = Path(project_dir)
    result: dict[str, Any] = {
        "content": "",
        "documents": [],
        "source": None,
        "acceptance_criteria": [],
        "product_vision": None,
        "architecture_summary": None,
    }

    # Try 1: Load from discovery cache file
    discovery_file = project_dir / ".workflow" / "phases" / "0" / "discovered_context.json"
    if discovery_file.exists():
        try:
            context = json.loads(discovery_file.read_text())
            result = _parse_discovered_context(context)
            result["source"] = "discovery_cache"
            logger.debug(
                f"Loaded documentation from discovery cache: {len(result['documents'])} docs"
            )
            return result
        except Exception as e:
            logger.warning(f"Failed to load discovery cache: {e}")

    # Try 2: Run discovery directly on docs/ folder
    try:
        from ...validators.documentation_discovery import DocumentationScanner

        scanner = DocumentationScanner()
        discovery = scanner.discover(project_dir)

        if discovery.is_valid:
            result = _parse_discovered_context(discovery.to_dict())
            result["source"] = "direct_discovery"
            logger.debug(f"Ran direct documentation discovery: {len(result['documents'])} docs")
            return result
        else:
            # No valid documentation found
            logger.warning(
                f"No documentation found for project: {project_name or project_dir}. "
                "Please create a docs/ folder with your project documentation."
            )
            result["source"] = "none"
            return result
    except Exception as e:
        logger.error(f"Documentation discovery failed: {e}")
        result["source"] = "error"
        return result


def _parse_discovered_context(context: dict) -> dict[str, Any]:
    """Parse discovered context dict into usable format.

    Args:
        context: Raw discovered context from scanner or cache

    Returns:
        Parsed context with combined content
    """
    result: dict[str, Any] = {
        "content": "",
        "documents": context.get("documents", []),
        "source": None,
        "acceptance_criteria": context.get("acceptance_criteria", []),
        "product_vision": context.get("product_vision"),
        "architecture_summary": context.get("architecture_summary"),
    }

    # Combine document content for prompts
    content_parts = []

    # Add product vision first if available
    if result["product_vision"]:
        content_parts.append(f"## Product Vision\n\n{result['product_vision']}")

    # Add architecture summary if available
    if result["architecture_summary"]:
        content_parts.append(f"## Architecture\n\n{result['architecture_summary']}")

    # Add document contents by category priority
    category_order = [
        "product_vision",
        "requirements",
        "user_stories",
        "architecture",
        "guides",
        "api_reference",
        "other",
    ]

    docs_by_category: dict[str, list] = {}
    for doc in result["documents"]:
        category = doc.get("category", "other")
        if category not in docs_by_category:
            docs_by_category[category] = []
        docs_by_category[category].append(doc)

    for category in category_order:
        if category in docs_by_category:
            for doc in docs_by_category[category]:
                doc_content = doc.get("content", "")
                if doc_content:
                    title = doc.get("title", doc.get("path", "Document"))
                    content_parts.append(f"## {title}\n\n{doc_content}")

    result["content"] = "\n\n---\n\n".join(content_parts) if content_parts else ""

    return result


def _extract_acceptance_criteria(content: str) -> list[str]:
    """Extract acceptance criteria from markdown content.

    Args:
        content: Markdown document content

    Returns:
        List of acceptance criteria strings
    """
    import re

    criteria = []

    # Find acceptance criteria section
    ac_pattern = r"(?:##?\s*)?(?:Acceptance\s*Criteria|Requirements|Criteria)[:\s]*\n((?:[\s\S]*?)(?=\n##|\n\*\*[A-Z]|\Z))"
    ac_match = re.search(ac_pattern, content, re.IGNORECASE)

    if ac_match:
        section = ac_match.group(1)

        # Extract checklist items
        checklist = re.findall(r"[-*]\s*\[[x ]\]\s*(.+)", section, re.IGNORECASE)
        criteria.extend(checklist)

        # Extract numbered items
        numbered = re.findall(r"\d+\.\s*(.+)", section)
        criteria.extend(numbered)

        # Extract simple bullet points if no checklist items
        if not criteria:
            bullets = re.findall(r"[-*]\s+(?!\[)(.+)", section)
            criteria.extend(bullets)

    return [c.strip() for c in criteria if c.strip()]


def get_documentation_summary(project_dir: Path, project_name: str = "") -> str:
    """Get a brief summary of available documentation.

    Useful for status displays and logging.

    Args:
        project_dir: Path to project directory
        project_name: Project name

    Returns:
        Human-readable summary string
    """
    context = load_documentation_context(project_dir, project_name)

    if context["source"] in ("none", "error"):
        return "No documentation found - please create a docs/ folder"
    else:
        doc_count = len(context["documents"])
        return f"docs/ folder ({doc_count} documents)"


def generate_context_summary(project_dir: Path, project_name: str = "") -> Optional[Path]:
    """Generate a context summary file from discovered documentation.

    This creates a summary file that agents can use as an entry point.
    The file is auto-generated, not user-provided.

    Args:
        project_dir: Path to project directory
        project_name: Project name

    Returns:
        Path to generated summary file, or None if no docs found
    """
    context = load_documentation_context(project_dir, project_name)

    if context["source"] in ("none", "error"):
        logger.warning("Cannot generate context summary - no documentation found")
        return None

    # Build summary content
    summary_parts = [
        "# Project Context Summary",
        "",
        "> **Auto-generated from docs/ folder. Do not edit manually.**",
        "",
    ]

    # Add vision
    if context["product_vision"]:
        summary_parts.extend(
            [
                "## Product Vision",
                "",
                context["product_vision"],
                "",
            ]
        )

    # Add architecture
    if context["architecture_summary"]:
        summary_parts.extend(
            [
                "## Architecture Overview",
                "",
                context["architecture_summary"],
                "",
            ]
        )

    # Add acceptance criteria
    if context["acceptance_criteria"]:
        summary_parts.extend(
            [
                "## Acceptance Criteria",
                "",
            ]
        )
        for criterion in context["acceptance_criteria"]:
            summary_parts.append(f"- [ ] {criterion}")
        summary_parts.append("")

    # Add document index
    summary_parts.extend(
        [
            "## Documentation Index",
            "",
            "| Document | Category |",
            "|----------|----------|",
        ]
    )
    for doc in context["documents"]:
        path = doc.get("path", "")
        title = doc.get("title", path)
        category = doc.get("category", "other")
        summary_parts.append(f"| [{title}](docs/{path}) | {category} |")

    summary_parts.append("")

    # Write to .workflow directory
    workflow_dir = project_dir / ".workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    summary_file = workflow_dir / CONTEXT_SUMMARY_FILENAME

    summary_file.write_text("\n".join(summary_parts))
    logger.info(f"Generated context summary: {summary_file}")

    return summary_file
