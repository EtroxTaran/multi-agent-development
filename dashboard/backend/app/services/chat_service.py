"""Chat service for Claude integration.

Provides full Claude Code integration for the dashboard.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


class ChatService:
    """Service for Claude chat integration.

    Provides:
    - Single-shot chat messages
    - Streaming responses
    - Command execution
    - Context-aware chat within projects
    """

    def __init__(self, project_dir: Optional[Path] = None):
        """Initialize chat service.

        Args:
            project_dir: Optional project directory for context
        """
        self.project_dir = project_dir
        self.settings = get_settings()

    @property
    def working_dir(self) -> Path:
        """Get working directory for Claude."""
        return self.project_dir or self.settings.conductor_root

    async def send_message(
        self,
        message: str,
        output_format: str = "text",
    ) -> str:
        """Send a message to Claude and get a response.

        Args:
            message: Message to send
            output_format: Output format (text, json)

        Returns:
            Claude's response
        """
        cmd = ["claude", "-p", message, "--output-format", output_format]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.claude_timeout,
            )

            if process.returncode == 0:
                return stdout.decode()
            else:
                logger.warning(f"Claude returned error: {stderr.decode()}")
                return stderr.decode()

        except asyncio.TimeoutError:
            raise TimeoutError("Claude request timed out")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found")

    async def stream_message(
        self,
        message: str,
    ) -> AsyncGenerator[str, None]:
        """Stream a message response from Claude.

        Args:
            message: Message to send

        Yields:
            Response chunks
        """
        cmd = ["claude", "-p", message, "--output-format", "stream-json"]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )

            async for line in process.stdout:
                if line:
                    try:
                        chunk = json.loads(line.decode())
                        content = chunk.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        yield line.decode()

            await process.wait()

        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found")

    async def execute_command(
        self,
        command: str,
        args: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Execute a Claude slash command.

        Args:
            command: Command name (without /)
            args: Optional command arguments

        Returns:
            Result dictionary with success, output, error
        """
        # Format command as prompt
        command_prompt = f"/{command}"
        if args:
            command_prompt += " " + " ".join(args)

        cmd = ["claude", "-p", command_prompt, "--output-format", "text"]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.claude_timeout,
            )

            return {
                "success": process.returncode == 0,
                "output": stdout.decode(),
                "error": stderr.decode() if process.returncode != 0 else None,
            }

        except asyncio.TimeoutError:
            return {"success": False, "error": "Command timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "Claude CLI not found"}

    async def get_context_summary(self) -> dict[str, Any]:
        """Get a summary of the current context.

        Returns:
            Context summary dictionary
        """
        if not self.project_dir:
            return {"type": "workspace", "path": str(self.settings.conductor_root)}

        return {
            "type": "project",
            "path": str(self.project_dir),
            "name": self.project_dir.name,
            "has_claude_md": (self.project_dir / "CLAUDE.md").exists(),
            "has_product_md": (self.project_dir / "PRODUCT.md").exists()
            or (self.project_dir / "Docs" / "PRODUCT.md").exists(),
        }


class ChatHistory:
    """Manages chat history for a project."""

    def __init__(self, project_dir: Path):
        """Initialize chat history.

        Args:
            project_dir: Project directory
        """
        self.project_dir = project_dir
        self.history_file = project_dir / ".workflow" / "chat_history.jsonl"

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a message to history.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
        """
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "role": role,
            "content": content,
            "timestamp": asyncio.get_event_loop().time(),
            "metadata": metadata or {},
        }

        with open(self.history_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_history(self, limit: int = 50) -> list[dict]:
        """Get chat history.

        Args:
            limit: Maximum messages to return

        Returns:
            List of message dictionaries
        """
        if not self.history_file.exists():
            return []

        messages = []
        with open(self.history_file) as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return messages[-limit:] if len(messages) > limit else messages

    def clear(self) -> None:
        """Clear chat history."""
        if self.history_file.exists():
            self.history_file.unlink()
