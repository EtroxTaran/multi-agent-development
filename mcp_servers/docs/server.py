"""MCP Server for documentation operations.

Provides access to project specifications, documentation, and
shared rules for AI agents working on the project.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

logger = logging.getLogger(__name__)

# Get paths from environment or defaults
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "projects"))
META_ROOT = Path(os.environ.get("META_ROOT", "."))


def create_server() -> Server:
    """Create and configure the MCP docs server.

    Returns:
        Configured MCP Server instance
    """
    server = Server("mcp-docs")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_spec",
                description=(
                    "Get the product specification (PRODUCT.md) for a project. "
                    "This contains the feature requirements and acceptance criteria."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="get_context",
                description=(
                    "Get agent-specific context file (CLAUDE.md, GEMINI.md, etc.). "
                    "Contains instructions and rules for the specific agent."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "agent": {
                            "type": "string",
                            "enum": ["claude", "gemini", "cursor", "agents"],
                            "description": "Agent name or 'agents' for AGENTS.md",
                        },
                    },
                    "required": ["project", "agent"],
                },
            ),
            Tool(
                name="get_rules",
                description=(
                    "Get shared rules that apply to all agents. "
                    "Includes coding standards, guardrails, and workflow rules."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["core", "coding", "guardrails", "cli", "lessons", "all"],
                            "description": "Rules category",
                            "default": "all",
                        },
                    },
                },
            ),
            Tool(
                name="search_docs",
                description=(
                    "Search documentation for a keyword or phrase. "
                    "Searches across all markdown files in a project."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name (optional, searches all if not provided)",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_readme",
                description="Get the README.md for a project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="list_docs",
                description=(
                    "List all documentation files in a project. "
                    "Returns paths and brief descriptions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                    },
                    "required": ["project"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "get_spec":
                result = await get_spec(arguments["project"])
            elif name == "get_context":
                result = await get_context(
                    project=arguments["project"],
                    agent=arguments["agent"],
                )
            elif name == "get_rules":
                result = await get_rules(
                    category=arguments.get("category", "all"),
                )
            elif name == "search_docs":
                result = await search_docs(
                    query=arguments["query"],
                    project=arguments.get("project"),
                    max_results=arguments.get("max_results", 10),
                )
            elif name == "get_readme":
                result = await get_readme(arguments["project"])
            elif name == "list_docs":
                result = await list_docs(arguments["project"])
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        resources = []

        # Add shared rules as resources
        shared_rules = META_ROOT / "shared-rules"
        if shared_rules.exists():
            resources.append(
                Resource(
                    uri="docs://shared-rules",
                    name="Shared Rules",
                    description="Rules that apply to all agents",
                    mimeType="text/markdown",
                )
            )

        # Add project docs as resources
        if PROJECTS_ROOT.exists():
            for project_dir in PROJECTS_ROOT.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    product_md = project_dir / "PRODUCT.md"
                    if product_md.exists():
                        resources.append(
                            Resource(
                                uri=f"docs://{project_dir.name}/spec",
                                name=f"Spec: {project_dir.name}",
                                description=f"Product specification for {project_dir.name}",
                                mimeType="text/markdown",
                            )
                        )

        return resources

    return server


async def get_spec(project: str) -> dict:
    """Get product specification for a project.

    Args:
        project: Project name

    Returns:
        Specification content and metadata
    """
    spec_file = PROJECTS_ROOT / project / "PRODUCT.md"

    if not spec_file.exists():
        return {"error": f"PRODUCT.md not found for project: {project}"}

    content = spec_file.read_text()

    # Extract title and summary from content
    title = None
    summary = None

    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif title and line.strip() and not line.startswith("#"):
            summary = line.strip()
            break

    return {
        "project": project,
        "title": title,
        "summary": summary,
        "content": content,
        "lines": len(lines),
    }


async def get_context(project: str, agent: str) -> dict:
    """Get agent-specific context file.

    Args:
        project: Project name
        agent: Agent name (claude, gemini, cursor, agents)

    Returns:
        Context content and metadata
    """
    file_map = {
        "claude": "CLAUDE.md",
        "gemini": "GEMINI.md",
        "cursor": ".cursor/rules",
        "agents": "AGENTS.md",
    }

    if agent not in file_map:
        return {"error": f"Unknown agent: {agent}"}

    context_file = PROJECTS_ROOT / project / file_map[agent]

    if not context_file.exists():
        return {"error": f"Context file not found: {file_map[agent]}"}

    content = context_file.read_text()

    return {
        "project": project,
        "agent": agent,
        "file": file_map[agent],
        "content": content,
        "lines": len(content.split("\n")),
    }


async def get_rules(category: str = "all") -> dict:
    """Get shared rules.

    Args:
        category: Rules category (core, coding, guardrails, cli, lessons, all)

    Returns:
        Rules content
    """
    rules_dir = META_ROOT / "shared-rules"

    if not rules_dir.exists():
        return {"error": "shared-rules directory not found"}

    file_map = {
        "core": "01-core-rules.md",
        "coding": "02-coding-standards.md",
        "guardrails": "03-guardrails.md",
        "cli": "04-cli-reference.md",
        "lessons": "99-lessons-learned.md",
    }

    if category == "all":
        rules = {}
        for cat, filename in file_map.items():
            file_path = rules_dir / filename
            if file_path.exists():
                rules[cat] = {
                    "file": filename,
                    "content": file_path.read_text(),
                }
        return {"rules": rules}

    if category not in file_map:
        return {"error": f"Unknown category: {category}"}

    rules_file = rules_dir / file_map[category]
    if not rules_file.exists():
        return {"error": f"Rules file not found: {file_map[category]}"}

    return {
        "category": category,
        "file": file_map[category],
        "content": rules_file.read_text(),
    }


async def search_docs(
    query: str,
    project: Optional[str] = None,
    max_results: int = 10,
) -> dict:
    """Search documentation files.

    Args:
        query: Search query
        project: Optional project to search in
        max_results: Maximum results

    Returns:
        Search results with file paths and matching lines
    """
    search_paths = []

    if project:
        project_dir = PROJECTS_ROOT / project
        if project_dir.exists():
            search_paths.append(project_dir)
    else:
        # Search all projects
        if PROJECTS_ROOT.exists():
            for p in PROJECTS_ROOT.iterdir():
                if p.is_dir() and not p.name.startswith("."):
                    search_paths.append(p)

        # Also search shared rules
        shared_rules = META_ROOT / "shared-rules"
        if shared_rules.exists():
            search_paths.append(shared_rules)

    results = []
    pattern = re.compile(query, re.IGNORECASE)

    for search_path in search_paths:
        for md_file in search_path.rglob("*.md"):
            if len(results) >= max_results:
                break

            try:
                content = md_file.read_text()
                matches = []

                for i, line in enumerate(content.split("\n"), 1):
                    if pattern.search(line):
                        matches.append(
                            {
                                "line": i,
                                "text": line.strip()[:200],
                            }
                        )

                if matches:
                    results.append(
                        {
                            "file": str(md_file.relative_to(META_ROOT)),
                            "matches": matches[:5],  # Limit matches per file
                        }
                    )

            except Exception as e:
                logger.warning(f"Error reading {md_file}: {e}")

    return {
        "query": query,
        "project": project,
        "total_files": len(results),
        "results": results[:max_results],
    }


async def get_readme(project: str) -> dict:
    """Get README for a project.

    Args:
        project: Project name

    Returns:
        README content
    """
    readme_file = PROJECTS_ROOT / project / "README.md"

    if not readme_file.exists():
        return {"error": f"README.md not found for project: {project}"}

    content = readme_file.read_text()

    return {
        "project": project,
        "content": content,
    }


async def list_docs(project: str) -> dict:
    """List documentation files in a project.

    Args:
        project: Project name

    Returns:
        List of documentation files
    """
    project_dir = PROJECTS_ROOT / project

    if not project_dir.exists():
        return {"error": f"Project not found: {project}"}

    docs = []

    for md_file in project_dir.rglob("*.md"):
        # Skip node_modules and similar
        if any(p in str(md_file) for p in ["node_modules", ".venv", "__pycache__"]):
            continue

        # Get first heading as description
        description = None
        try:
            content = md_file.read_text()
            for line in content.split("\n"):
                if line.startswith("# "):
                    description = line[2:].strip()
                    break
        except Exception:
            pass

        docs.append(
            {
                "path": str(md_file.relative_to(project_dir)),
                "description": description,
                "size": md_file.stat().st_size,
            }
        )

    return {
        "project": project,
        "total": len(docs),
        "files": docs,
    }


async def run_server():
    """Run the MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
