"""MCP Server for git operations.

Provides access to git diff, history, and change tracking
for AI agents reviewing code changes.
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
)

logger = logging.getLogger(__name__)

# Get projects root from environment or default
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "projects"))


def create_server() -> Server:
    """Create and configure the MCP git server.

    Returns:
        Configured MCP Server instance
    """
    server = Server("mcp-git")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_diff",
                description=(
                    "Get git diff for a project. Shows changes between commits, "
                    "staged changes, or working directory changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "base": {
                            "type": "string",
                            "description": "Base commit/ref (default: HEAD)",
                            "default": "HEAD",
                        },
                        "target": {
                            "type": "string",
                            "description": "Target commit/ref (default: working directory)",
                        },
                        "staged": {
                            "type": "boolean",
                            "description": "Show only staged changes",
                            "default": False,
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Specific file to diff",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="get_history",
                description=(
                    "Get git commit history for a project. "
                    "Returns recent commits with messages and stats."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of commits to retrieve",
                            "default": 10,
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Filter by file path",
                        },
                        "since": {
                            "type": "string",
                            "description": "Show commits since date (e.g., '2024-01-01')",
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="list_changes",
                description=(
                    "List changed files in a project. "
                    "Shows modified, added, and deleted files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "staged": {
                            "type": "boolean",
                            "description": "Show only staged changes",
                            "default": False,
                        },
                        "include_untracked": {
                            "type": "boolean",
                            "description": "Include untracked files",
                            "default": True,
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="get_file_at_commit",
                description=(
                    "Get file contents at a specific commit. "
                    "Useful for comparing with current version."
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
                        "commit": {
                            "type": "string",
                            "description": "Commit hash or ref",
                            "default": "HEAD",
                        },
                    },
                    "required": ["project", "file_path"],
                },
            ),
            Tool(
                name="get_blame",
                description=(
                    "Get git blame for a file. "
                    "Shows who last modified each line."
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
                        "line_start": {
                            "type": "integer",
                            "description": "Starting line number",
                        },
                        "line_end": {
                            "type": "integer",
                            "description": "Ending line number",
                        },
                    },
                    "required": ["project", "file_path"],
                },
            ),
            Tool(
                name="get_branch_info",
                description=(
                    "Get information about branches. "
                    "Shows current branch and list of branches."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "include_remote": {
                            "type": "boolean",
                            "description": "Include remote branches",
                            "default": False,
                        },
                    },
                    "required": ["project"],
                },
            ),
            Tool(
                name="compare_commits",
                description=(
                    "Compare two commits. "
                    "Shows files changed and summary of changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "base": {
                            "type": "string",
                            "description": "Base commit/ref",
                        },
                        "target": {
                            "type": "string",
                            "description": "Target commit/ref",
                        },
                    },
                    "required": ["project", "base", "target"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "get_diff":
                result = await get_diff(
                    project=arguments["project"],
                    base=arguments.get("base", "HEAD"),
                    target=arguments.get("target"),
                    staged=arguments.get("staged", False),
                    file_path=arguments.get("file_path"),
                )
            elif name == "get_history":
                result = await get_history(
                    project=arguments["project"],
                    limit=arguments.get("limit", 10),
                    file_path=arguments.get("file_path"),
                    since=arguments.get("since"),
                )
            elif name == "list_changes":
                result = await list_changes(
                    project=arguments["project"],
                    staged=arguments.get("staged", False),
                    include_untracked=arguments.get("include_untracked", True),
                )
            elif name == "get_file_at_commit":
                result = await get_file_at_commit(
                    project=arguments["project"],
                    file_path=arguments["file_path"],
                    commit=arguments.get("commit", "HEAD"),
                )
            elif name == "get_blame":
                result = await get_blame(
                    project=arguments["project"],
                    file_path=arguments["file_path"],
                    line_start=arguments.get("line_start"),
                    line_end=arguments.get("line_end"),
                )
            elif name == "get_branch_info":
                result = await get_branch_info(
                    project=arguments["project"],
                    include_remote=arguments.get("include_remote", False),
                )
            elif name == "compare_commits":
                result = await compare_commits(
                    project=arguments["project"],
                    base=arguments["base"],
                    target=arguments["target"],
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

        if PROJECTS_ROOT.exists():
            for project_dir in PROJECTS_ROOT.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    git_dir = project_dir / ".git"
                    if git_dir.exists():
                        resources.append(
                            Resource(
                                uri=f"git://{project_dir.name}/status",
                                name=f"Git Status: {project_dir.name}",
                                description=f"Git status for {project_dir.name}",
                                mimeType="application/json",
                            )
                        )

        return resources

    return server


def _run_git(project: str, *args: str) -> tuple[bool, str]:
    """Run a git command in a project directory.

    Args:
        project: Project name
        *args: Git command arguments

    Returns:
        Tuple of (success, output)
    """
    project_dir = PROJECTS_ROOT / project

    if not project_dir.exists():
        return False, f"Project not found: {project}"

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr or f"Git command failed with code {result.returncode}"

    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except FileNotFoundError:
        return False, "Git not found"


async def get_diff(
    project: str,
    base: str = "HEAD",
    target: Optional[str] = None,
    staged: bool = False,
    file_path: Optional[str] = None,
) -> dict:
    """Get git diff for a project.

    Args:
        project: Project name
        base: Base commit/ref
        target: Target commit/ref
        staged: Show only staged changes
        file_path: Specific file to diff

    Returns:
        Diff content and metadata
    """
    args = ["diff"]

    if staged:
        args.append("--cached")
    elif target:
        args.extend([base, target])
    else:
        args.append(base)

    args.extend(["--stat", "--"])

    if file_path:
        args.append(file_path)

    # Get stat first
    success, stat_output = _run_git(project, *args)
    if not success:
        return {"error": stat_output}

    # Get actual diff
    diff_args = ["diff"]
    if staged:
        diff_args.append("--cached")
    elif target:
        diff_args.extend([base, target])
    else:
        diff_args.append(base)

    diff_args.append("--")
    if file_path:
        diff_args.append(file_path)

    success, diff_output = _run_git(project, *diff_args)
    if not success:
        return {"error": diff_output}

    return {
        "project": project,
        "base": base,
        "target": target or "working directory",
        "staged": staged,
        "stat": stat_output,
        "diff": diff_output,
        "lines_added": diff_output.count("\n+") - diff_output.count("\n+++"),
        "lines_removed": diff_output.count("\n-") - diff_output.count("\n---"),
    }


async def get_history(
    project: str,
    limit: int = 10,
    file_path: Optional[str] = None,
    since: Optional[str] = None,
) -> dict:
    """Get git commit history.

    Args:
        project: Project name
        limit: Number of commits
        file_path: Filter by file
        since: Date filter

    Returns:
        List of commits
    """
    args = [
        "log",
        f"-{limit}",
        "--format=%H|%an|%ae|%at|%s",
    ]

    if since:
        args.append(f"--since={since}")

    if file_path:
        args.extend(["--", file_path])

    success, output = _run_git(project, *args)
    if not success:
        return {"error": output}

    commits = []
    for line in output.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "timestamp": int(parts[3]),
                "message": parts[4],
            })

    return {
        "project": project,
        "limit": limit,
        "total": len(commits),
        "commits": commits,
    }


async def list_changes(
    project: str,
    staged: bool = False,
    include_untracked: bool = True,
) -> dict:
    """List changed files.

    Args:
        project: Project name
        staged: Show only staged
        include_untracked: Include untracked files

    Returns:
        Lists of changed files by type
    """
    # Get status
    args = ["status", "--porcelain"]
    if include_untracked:
        args.append("-u")

    success, output = _run_git(project, *args)
    if not success:
        return {"error": output}

    modified = []
    added = []
    deleted = []
    untracked = []

    for line in output.strip().split("\n"):
        if not line:
            continue

        status = line[:2]
        file_path = line[3:]

        # Staged vs unstaged
        if staged:
            status_char = status[0]
        else:
            status_char = status[1] if status[1] != " " else status[0]

        if status_char == "M":
            modified.append(file_path)
        elif status_char == "A":
            added.append(file_path)
        elif status_char == "D":
            deleted.append(file_path)
        elif status_char == "?":
            untracked.append(file_path)

    return {
        "project": project,
        "staged_only": staged,
        "modified": modified,
        "added": added,
        "deleted": deleted,
        "untracked": untracked if include_untracked else [],
        "total": len(modified) + len(added) + len(deleted) + len(untracked),
    }


async def get_file_at_commit(
    project: str,
    file_path: str,
    commit: str = "HEAD",
) -> dict:
    """Get file contents at a commit.

    Args:
        project: Project name
        file_path: File path
        commit: Commit hash/ref

    Returns:
        File content at the commit
    """
    success, output = _run_git(project, "show", f"{commit}:{file_path}")
    if not success:
        return {"error": output}

    return {
        "project": project,
        "file": file_path,
        "commit": commit,
        "content": output,
        "lines": len(output.split("\n")),
    }


async def get_blame(
    project: str,
    file_path: str,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
) -> dict:
    """Get git blame for a file.

    Args:
        project: Project name
        file_path: File path
        line_start: Starting line
        line_end: Ending line

    Returns:
        Blame information
    """
    args = ["blame", "--line-porcelain"]

    if line_start and line_end:
        args.extend(["-L", f"{line_start},{line_end}"])

    args.append(file_path)

    success, output = _run_git(project, *args)
    if not success:
        return {"error": output}

    # Parse blame output
    lines = []
    current_commit = None
    current_author = None

    for line in output.split("\n"):
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line[:40].lower()):
            current_commit = line[:40]
        elif line.startswith("author "):
            current_author = line[7:]
        elif line.startswith("\t"):
            lines.append({
                "commit": current_commit[:8] if current_commit else None,
                "author": current_author,
                "content": line[1:],
            })

    return {
        "project": project,
        "file": file_path,
        "lines": lines,
    }


async def get_branch_info(
    project: str,
    include_remote: bool = False,
) -> dict:
    """Get branch information.

    Args:
        project: Project name
        include_remote: Include remote branches

    Returns:
        Branch information
    """
    # Get current branch
    success, current = _run_git(project, "branch", "--show-current")
    if not success:
        return {"error": current}

    # Get all branches
    args = ["branch", "--format=%(refname:short)|%(upstream:short)|%(upstream:track)"]
    if include_remote:
        args.append("-a")

    success, output = _run_git(project, *args)
    if not success:
        return {"error": output}

    branches = []
    for line in output.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|")
        branches.append({
            "name": parts[0],
            "upstream": parts[1] if len(parts) > 1 and parts[1] else None,
            "tracking": parts[2] if len(parts) > 2 and parts[2] else None,
        })

    return {
        "project": project,
        "current": current.strip(),
        "branches": branches,
    }


async def compare_commits(
    project: str,
    base: str,
    target: str,
) -> dict:
    """Compare two commits.

    Args:
        project: Project name
        base: Base commit/ref
        target: Target commit/ref

    Returns:
        Comparison summary
    """
    # Get changed files
    success, output = _run_git(project, "diff", "--name-status", base, target)
    if not success:
        return {"error": output}

    files = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append({
                "status": parts[0],
                "path": parts[1],
            })

    # Get stats
    success, stat_output = _run_git(project, "diff", "--stat", base, target)

    return {
        "project": project,
        "base": base,
        "target": target,
        "files_changed": len(files),
        "files": files,
        "stat": stat_output if success else None,
    }


async def run_server():
    """Run the MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
