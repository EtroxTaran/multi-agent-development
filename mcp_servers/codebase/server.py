"""MCP Server for codebase operations.

Provides semantic code search, symbol lookup, and reference finding
for AI agents reviewing code.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
)

logger = logging.getLogger(__name__)

# Get projects root from environment or default
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "projects"))


def create_server() -> Server:
    """Create and configure the MCP codebase server.

    Returns:
        Configured MCP Server instance
    """
    server = Server("mcp-codebase")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="search_code",
                description=(
                    "Search for code patterns in a project using ripgrep. "
                    "Supports regex patterns and file type filtering."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search pattern (regex supported)",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name in projects/ directory",
                        },
                        "file_type": {
                            "type": "string",
                            "description": "File type filter (e.g., py, ts, js)",
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Lines of context around matches",
                            "default": 2,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 20,
                        },
                    },
                    "required": ["query", "project"],
                },
            ),
            Tool(
                name="get_symbols",
                description=(
                    "Get symbols (functions, classes, methods) from a file or project. "
                    "Returns symbol names, types, and locations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Specific file path (relative to project)",
                        },
                        "symbol_type": {
                            "type": "string",
                            "enum": ["function", "class", "method", "variable", "all"],
                            "description": "Type of symbols to find",
                            "default": "all",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="find_references",
                description=(
                    "Find all references to a symbol in the codebase. "
                    "Useful for understanding usage patterns."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Symbol name to find references for",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "include_definition": {
                            "type": "boolean",
                            "description": "Include the definition location",
                            "default": True,
                        },
                    },
                    "required": ["symbol", "project"],
                },
            ),
            Tool(
                name="get_file_structure",
                description=(
                    "Get the structure of a project or directory. "
                    "Returns a tree of files with basic metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "path": {
                            "type": "string",
                            "description": "Subdirectory path (relative to project)",
                            "default": "",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum depth to traverse",
                            "default": 3,
                        },
                        "include_hidden": {
                            "type": "boolean",
                            "description": "Include hidden files/directories",
                            "default": False,
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="get_file_summary",
                description=(
                    "Get a summary of a source file including imports, "
                    "exports, and main components without full content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project",
                        },
                    },
                    "required": ["project", "file_path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "search_code":
                result = await search_code(
                    query=arguments["query"],
                    project=arguments["project"],
                    file_type=arguments.get("file_type"),
                    context_lines=arguments.get("context_lines", 2),
                    max_results=arguments.get("max_results", 20),
                )
            elif name == "get_symbols":
                result = await get_symbols(
                    project=arguments["project"],
                    file_path=arguments.get("file_path"),
                    symbol_type=arguments.get("symbol_type", "all"),
                )
            elif name == "find_references":
                result = await find_references(
                    symbol=arguments["symbol"],
                    project=arguments["project"],
                    include_definition=arguments.get("include_definition", True),
                )
            elif name == "get_file_structure":
                result = await get_file_structure(
                    project=arguments["project"],
                    path=arguments.get("path", ""),
                    max_depth=arguments.get("max_depth", 3),
                    include_hidden=arguments.get("include_hidden", False),
                )
            elif name == "get_file_summary":
                result = await get_file_summary(
                    project=arguments["project"],
                    file_path=arguments["file_path"],
                )
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

        # List projects as resources
        if PROJECTS_ROOT.exists():
            for project_dir in PROJECTS_ROOT.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    resources.append(
                        Resource(
                            uri=f"codebase://{project_dir.name}",
                            name=f"Project: {project_dir.name}",
                            description=f"Source code for {project_dir.name}",
                            mimeType="application/json",
                        )
                    )

        return resources

    @server.list_resource_templates()
    async def list_resource_templates() -> list[ResourceTemplate]:
        """List resource templates."""
        return [
            ResourceTemplate(
                uriTemplate="codebase://{project}/file/{path}",
                name="Source File",
                description="Read a source file from a project",
            ),
            ResourceTemplate(
                uriTemplate="codebase://{project}/symbols",
                name="Project Symbols",
                description="Get all symbols in a project",
            ),
        ]

    return server


async def search_code(
    query: str,
    project: str,
    file_type: Optional[str] = None,
    context_lines: int = 2,
    max_results: int = 20,
) -> dict:
    """Search for code patterns using ripgrep.

    Args:
        query: Search pattern (regex)
        project: Project name
        file_type: File type filter
        context_lines: Context lines around matches
        max_results: Maximum results

    Returns:
        Search results with matches and context
    """
    project_dir = PROJECTS_ROOT / project
    if not project_dir.exists():
        return {"error": f"Project not found: {project}"}

    cmd = ["rg", "--json", "-C", str(context_lines), "-m", str(max_results)]

    if file_type:
        cmd.extend(["-t", file_type])

    cmd.extend([query, str(project_dir)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    matches.append({
                        "file": match_data["path"]["text"],
                        "line": match_data["line_number"],
                        "text": match_data["lines"]["text"].strip(),
                    })
            except json.JSONDecodeError:
                continue

        return {
            "query": query,
            "project": project,
            "total_matches": len(matches),
            "matches": matches[:max_results],
        }

    except subprocess.TimeoutExpired:
        return {"error": "Search timed out"}
    except FileNotFoundError:
        return {"error": "ripgrep not installed"}


async def get_symbols(
    project: str,
    file_path: Optional[str] = None,
    symbol_type: str = "all",
) -> dict:
    """Get symbols from code files.

    Uses regex patterns to extract function, class, and variable definitions.

    Args:
        project: Project name
        file_path: Specific file (optional)
        symbol_type: Type of symbols to find

    Returns:
        Dictionary of symbols by type
    """
    project_dir = PROJECTS_ROOT / project
    if not project_dir.exists():
        return {"error": f"Project not found: {project}"}

    target = project_dir / file_path if file_path else project_dir

    # Symbol patterns by language
    patterns = {
        "python": {
            "function": r"^\s*(?:async\s+)?def\s+(\w+)\s*\(",
            "class": r"^\s*class\s+(\w+)\s*[:\(]",
            "method": r"^\s+(?:async\s+)?def\s+(\w+)\s*\(",
            "variable": r"^(\w+)\s*[=:]",
        },
        "typescript": {
            "function": r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[<\(]",
            "class": r"(?:export\s+)?class\s+(\w+)",
            "method": r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]",
            "variable": r"(?:export\s+)?(?:const|let|var)\s+(\w+)",
        },
        "javascript": {
            "function": r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
            "class": r"(?:export\s+)?class\s+(\w+)",
            "method": r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{",
            "variable": r"(?:export\s+)?(?:const|let|var)\s+(\w+)",
        },
    }

    # Determine files to scan
    if target.is_file():
        files = [target]
    else:
        files = list(target.rglob("*.py")) + list(target.rglob("*.ts")) + list(target.rglob("*.js"))
        files = [f for f in files if not any(p in str(f) for p in ["node_modules", "__pycache__", ".venv"])]

    symbols: dict[str, list] = {
        "functions": [],
        "classes": [],
        "methods": [],
        "variables": [],
    }

    for file in files[:100]:  # Limit files
        ext = file.suffix.lower()
        lang = {".py": "python", ".ts": "typescript", ".js": "javascript"}.get(ext)
        if not lang:
            continue

        try:
            content = file.read_text()
            rel_path = str(file.relative_to(project_dir))

            for sym_type, pattern in patterns[lang].items():
                if symbol_type not in ("all", sym_type):
                    continue

                for i, line in enumerate(content.split("\n"), 1):
                    match = re.match(pattern, line)
                    if match:
                        symbols[f"{sym_type}s" if not sym_type.endswith("s") else sym_type].append({
                            "name": match.group(1),
                            "file": rel_path,
                            "line": i,
                        })

        except Exception as e:
            logger.warning(f"Error reading {file}: {e}")

    return {
        "project": project,
        "file": file_path,
        "symbols": symbols,
        "total": sum(len(v) for v in symbols.values()),
    }


async def find_references(
    symbol: str,
    project: str,
    include_definition: bool = True,
) -> dict:
    """Find all references to a symbol.

    Args:
        symbol: Symbol name to find
        project: Project name
        include_definition: Include definition location

    Returns:
        List of references with locations
    """
    project_dir = PROJECTS_ROOT / project
    if not project_dir.exists():
        return {"error": f"Project not found: {project}"}

    # Use ripgrep to find word boundaries
    cmd = [
        "rg",
        "--json",
        "-w",  # Word boundaries
        symbol,
        str(project_dir),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        references = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    file_path = match_data["path"]["text"]
                    line_num = match_data["line_number"]
                    line_text = match_data["lines"]["text"].strip()

                    # Determine if this is a definition
                    is_definition = any([
                        re.search(rf"(?:def|function|class)\s+{symbol}\b", line_text),
                        re.search(rf"(?:const|let|var)\s+{symbol}\b", line_text),
                        re.search(rf"{symbol}\s*=", line_text),
                    ])

                    if include_definition or not is_definition:
                        references.append({
                            "file": file_path,
                            "line": line_num,
                            "text": line_text,
                            "is_definition": is_definition,
                        })
            except json.JSONDecodeError:
                continue

        return {
            "symbol": symbol,
            "project": project,
            "total_references": len(references),
            "references": references,
        }

    except subprocess.TimeoutExpired:
        return {"error": "Search timed out"}
    except FileNotFoundError:
        return {"error": "ripgrep not installed"}


async def get_file_structure(
    project: str,
    path: str = "",
    max_depth: int = 3,
    include_hidden: bool = False,
) -> dict:
    """Get project file structure.

    Args:
        project: Project name
        path: Subdirectory path
        max_depth: Maximum traversal depth
        include_hidden: Include hidden files

    Returns:
        Tree structure of files
    """
    project_dir = PROJECTS_ROOT / project
    target = project_dir / path if path else project_dir

    if not target.exists():
        return {"error": f"Path not found: {project}/{path}"}

    def build_tree(dir_path: Path, depth: int = 0) -> dict:
        if depth >= max_depth:
            return {"name": dir_path.name, "type": "directory", "truncated": True}

        result = {
            "name": dir_path.name,
            "type": "directory",
            "children": [],
        }

        try:
            for item in sorted(dir_path.iterdir()):
                if not include_hidden and item.name.startswith("."):
                    continue

                # Skip common non-essential directories
                if item.name in {"node_modules", "__pycache__", ".venv", ".git", "dist", "build"}:
                    continue

                if item.is_dir():
                    result["children"].append(build_tree(item, depth + 1))
                else:
                    result["children"].append({
                        "name": item.name,
                        "type": "file",
                        "size": item.stat().st_size,
                    })

        except PermissionError:
            result["error"] = "Permission denied"

        return result

    return {
        "project": project,
        "path": path,
        "structure": build_tree(target),
    }


async def get_file_summary(
    project: str,
    file_path: str,
) -> dict:
    """Get a summary of a source file.

    Args:
        project: Project name
        file_path: File path relative to project

    Returns:
        File summary with imports, exports, and components
    """
    target = PROJECTS_ROOT / project / file_path

    if not target.exists():
        return {"error": f"File not found: {project}/{file_path}"}

    try:
        content = target.read_text()
        lines = content.split("\n")

        summary = {
            "file": file_path,
            "lines": len(lines),
            "size": len(content),
            "imports": [],
            "exports": [],
            "functions": [],
            "classes": [],
        }

        ext = target.suffix.lower()

        # Python patterns
        if ext == ".py":
            for i, line in enumerate(lines, 1):
                if re.match(r"^import\s+\w+|^from\s+\w+", line):
                    summary["imports"].append({"line": i, "statement": line.strip()})
                elif re.match(r"^(?:async\s+)?def\s+(\w+)", line):
                    match = re.match(r"^(?:async\s+)?def\s+(\w+)", line)
                    if match:
                        summary["functions"].append({"name": match.group(1), "line": i})
                elif re.match(r"^class\s+(\w+)", line):
                    match = re.match(r"^class\s+(\w+)", line)
                    if match:
                        summary["classes"].append({"name": match.group(1), "line": i})

        # TypeScript/JavaScript patterns
        elif ext in (".ts", ".js", ".tsx", ".jsx"):
            for i, line in enumerate(lines, 1):
                if re.match(r"^import\s+", line):
                    summary["imports"].append({"line": i, "statement": line.strip()})
                elif re.match(r"^export\s+", line):
                    summary["exports"].append({"line": i, "statement": line.strip()})
                elif re.match(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", line):
                    match = re.match(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", line)
                    if match:
                        summary["functions"].append({"name": match.group(1), "line": i})
                elif re.match(r"(?:export\s+)?class\s+(\w+)", line):
                    match = re.match(r"(?:export\s+)?class\s+(\w+)", line)
                    if match:
                        summary["classes"].append({"name": match.group(1), "line": i})

        return summary

    except Exception as e:
        return {"error": f"Failed to read file: {e}"}


async def run_server():
    """Run the MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
