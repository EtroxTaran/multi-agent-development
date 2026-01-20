"""Unified MCP client for connecting to all MCP servers.

Provides a single interface for the orchestrator to access all
MCP server functionality.
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    command: str
    args: list[str]
    env: Optional[dict[str, str]] = None


@dataclass
class MCPToolResult:
    """Result from an MCP tool call."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class MCPClient:
    """Unified client for MCP servers.

    Manages connections to multiple MCP servers and provides
    a unified interface for tool calls.

    Example:
        async with MCPClient() as client:
            # Search code
            result = await client.call_tool(
                "mcp-codebase",
                "search_code",
                {"query": "def authenticate", "project": "my-app"}
            )

            # Get workflow state
            state = await client.call_tool(
                "mcp-workflow",
                "get_state",
                {"project": "my-app"}
            )
    """

    # Default server configurations
    DEFAULT_SERVERS = {
        "mcp-codebase": MCPServerConfig(
            name="mcp-codebase",
            command="python",
            args=["-m", "mcp_servers.codebase"],
            env={"PROJECTS_ROOT": "projects/"},
        ),
        "mcp-workflow": MCPServerConfig(
            name="mcp-workflow",
            command="python",
            args=["-m", "mcp_servers.workflow"],
            env={"PROJECTS_ROOT": "projects/"},
        ),
        "mcp-docs": MCPServerConfig(
            name="mcp-docs",
            command="python",
            args=["-m", "mcp_servers.docs"],
            env={"PROJECTS_ROOT": "projects/", "META_ROOT": "."},
        ),
        "mcp-git": MCPServerConfig(
            name="mcp-git",
            command="python",
            args=["-m", "mcp_servers.git"],
            env={"PROJECTS_ROOT": "projects/"},
        ),
    }

    def __init__(
        self,
        config_path: Optional[Path] = None,
        servers: Optional[dict[str, MCPServerConfig]] = None,
    ):
        """Initialize the MCP client.

        Args:
            config_path: Path to mcp.json configuration file
            servers: Optional server configurations (overrides config file)
        """
        self.servers = servers or self._load_config(config_path)
        self._processes: dict[str, subprocess.Popen] = {}
        self._initialized = False

    def _load_config(self, config_path: Optional[Path]) -> dict[str, MCPServerConfig]:
        """Load server configurations from mcp.json.

        Args:
            config_path: Path to configuration file

        Returns:
            Dictionary of server configurations
        """
        if config_path is None:
            config_path = Path("mcp.json")

        if not config_path.exists():
            logger.info("No mcp.json found, using default server configurations")
            return self.DEFAULT_SERVERS.copy()

        try:
            config = json.loads(config_path.read_text())
            servers = {}

            for name, server_config in config.get("mcpServers", {}).items():
                servers[name] = MCPServerConfig(
                    name=name,
                    command=server_config.get("command", "python"),
                    args=server_config.get("args", []),
                    env=server_config.get("env"),
                )

            return servers

        except Exception as e:
            logger.error(f"Failed to load mcp.json: {e}")
            return self.DEFAULT_SERVERS.copy()

    async def __aenter__(self) -> "MCPClient":
        """Initialize and start MCP servers."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop MCP servers."""
        await self.stop()

    async def start(self) -> None:
        """Start all configured MCP servers."""
        if self._initialized:
            return

        for name, config in self.servers.items():
            try:
                env = {**dict(__import__("os").environ)}
                if config.env:
                    env.update(config.env)

                # Note: In a full implementation, we would use MCP client library
                # to connect to servers. For now, we use direct tool imports.
                logger.info(f"Registered MCP server: {name}")

            except Exception as e:
                logger.error(f"Failed to start MCP server {name}: {e}")

        self._initialized = True

    async def stop(self) -> None:
        """Stop all MCP servers."""
        for name, process in self._processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping MCP server {name}: {e}")

        self._processes.clear()
        self._initialized = False

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: dict,
    ) -> MCPToolResult:
        """Call a tool on an MCP server.

        Args:
            server: Server name (e.g., "mcp-codebase")
            tool: Tool name (e.g., "search_code")
            arguments: Tool arguments

        Returns:
            MCPToolResult with tool output
        """
        if server not in self.servers:
            return MCPToolResult(
                success=False,
                error=f"Unknown server: {server}",
            )

        try:
            # Direct import and call (simplified for local use)
            # In production, would use MCP client protocol
            if server == "mcp-codebase":
                from mcp_servers.codebase import server as codebase_server

                result = await self._call_local_tool(codebase_server, tool, arguments)
            elif server == "mcp-workflow":
                from mcp_servers.workflow import server as workflow_server

                result = await self._call_local_tool(workflow_server, tool, arguments)
            elif server == "mcp-docs":
                from mcp_servers.docs import server as docs_server

                result = await self._call_local_tool(docs_server, tool, arguments)
            elif server == "mcp-git":
                from mcp_servers.git import server as git_server

                result = await self._call_local_tool(git_server, tool, arguments)
            else:
                return MCPToolResult(
                    success=False,
                    error=f"Server not implemented: {server}",
                )

            return MCPToolResult(success=True, data=result)

        except Exception as e:
            logger.error(f"Tool call failed: {server}/{tool}: {e}")
            return MCPToolResult(
                success=False,
                error=str(e),
            )

    async def _call_local_tool(
        self,
        server_module: Any,
        tool: str,
        arguments: dict,
    ) -> Any:
        """Call a tool on a locally imported server module.

        Args:
            server_module: Server module
            tool: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        # Map tool names to functions
        tool_map = {
            # Codebase tools
            "search_code": "search_code",
            "get_symbols": "get_symbols",
            "find_references": "find_references",
            "get_file_structure": "get_file_structure",
            "get_file_summary": "get_file_summary",
            # Workflow tools
            "get_state": "get_state",
            "update_phase": "update_phase",
            "get_plan": "get_plan",
            "save_plan": "save_plan",
            "create_checkpoint": "create_checkpoint",
            "get_phase_feedback": "get_phase_feedback",
            "save_phase_feedback": "save_phase_feedback",
            "add_blocker": "add_blocker",
            "resolve_blocker": "resolve_blocker",
            # Docs tools
            "get_spec": "get_spec",
            "get_context": "get_context",
            "get_rules": "get_rules",
            "search_docs": "search_docs",
            "get_readme": "get_readme",
            "list_docs": "list_docs",
            # Git tools
            "get_diff": "get_diff",
            "get_history": "get_history",
            "list_changes": "list_changes",
            "get_file_at_commit": "get_file_at_commit",
            "get_blame": "get_blame",
            "get_branch_info": "get_branch_info",
            "compare_commits": "compare_commits",
        }

        if tool not in tool_map:
            raise ValueError(f"Unknown tool: {tool}")

        func_name = tool_map[tool]
        func = getattr(server_module, func_name)

        return await func(**arguments)

    async def search_code(self, project: str, query: str, **kwargs) -> MCPToolResult:
        """Convenience method for code search."""
        return await self.call_tool(
            "mcp-codebase",
            "search_code",
            {"project": project, "query": query, **kwargs},
        )

    async def get_workflow_state(self, project: str) -> MCPToolResult:
        """Convenience method for getting workflow state."""
        return await self.call_tool(
            "mcp-workflow",
            "get_state",
            {"project": project},
        )

    async def get_plan(self, project: str) -> MCPToolResult:
        """Convenience method for getting implementation plan."""
        return await self.call_tool(
            "mcp-workflow",
            "get_plan",
            {"project": project},
        )

    async def get_spec(self, project: str) -> MCPToolResult:
        """Convenience method for getting product specification."""
        return await self.call_tool(
            "mcp-docs",
            "get_spec",
            {"project": project},
        )

    async def get_diff(self, project: str, **kwargs) -> MCPToolResult:
        """Convenience method for getting git diff."""
        return await self.call_tool(
            "mcp-git",
            "get_diff",
            {"project": project, **kwargs},
        )

    async def list_changes(self, project: str, **kwargs) -> MCPToolResult:
        """Convenience method for listing changed files."""
        return await self.call_tool(
            "mcp-git",
            "list_changes",
            {"project": project, **kwargs},
        )


# Singleton client instance
_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the global MCP client.

    Returns:
        MCPClient instance
    """
    global _client
    if _client is None:
        _client = MCPClient()
    return _client


async def reset_mcp_client() -> None:
    """Reset the global MCP client."""
    global _client
    if _client is not None:
        await _client.stop()
        _client = None
