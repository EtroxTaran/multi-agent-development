"""Specialist Agent Runner.

Handles loading agent configurations (context, tools) and executing
them using the appropriate CLI wrapper.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Type

from ..agents.base import BaseAgent
from ..agents.claude_agent import ClaudeAgent
from ..agents.cursor_agent import CursorAgent
from ..agents.gemini_agent import GeminiAgent

logger = logging.getLogger(__name__)

class SpecialistRunner:
    """Runs a specific specialist agent with its configured context."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.agents_dir = project_dir / "agents"

    def get_agent_config(self, agent_id: str) -> dict[str, Any]:
        """Load configuration for a specialist agent.

        Args:
            agent_id: Agent ID (e.g., "A04-implementer")

        Returns:
            Dictionary with context path, tools, and agent type
        """
        # Find agent directory matching the ID prefix
        agent_dir = None
        for path in self.agents_dir.iterdir():
            if path.is_dir() and path.name.startswith(agent_id):
                agent_dir = path
                break
        
        if not agent_dir:
            raise ValueError(f"Agent directory not found for ID: {agent_id}")

        # Determine agent type and context file
        agent_type = "claude"
        context_file = None
        
        if (agent_dir / "CLAUDE.md").exists():
            agent_type = "claude"
            context_file = agent_dir / "CLAUDE.md"
        elif (agent_dir / "GEMINI.md").exists():
            agent_type = "gemini"
            context_file = agent_dir / "GEMINI.md"
        elif (agent_dir / "CURSOR-RULES.md").exists():
            agent_type = "cursor"
            context_file = agent_dir / "CURSOR-RULES.md"
        
        # Load tools
        tools = []
        tools_file = agent_dir / "TOOLS.json"
        if tools_file.exists():
            try:
                tools = json.loads(tools_file.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse TOOLS.json for {agent_id}")

        return {
            "name": agent_dir.name,
            "type": agent_type,
            "context_file": context_file,
            "tools": tools,
            "dir": agent_dir
        }

    def create_agent(self, agent_id: str) -> BaseAgent:
        """Create an agent instance configured for the specialist.

        Args:
            agent_id: Agent ID (e.g., "A04")

        Returns:
            Configured agent instance
        """
        config = self.get_agent_config(agent_id)
        
        if config["type"] == "claude":
            # For Claude, we inject the context file as a system prompt
            # relative path from project root is required by ClaudeAgent
            rel_context = config["context_file"].relative_to(self.project_dir)
            return ClaudeAgent(
                self.project_dir,
                allowed_tools=config["tools"],
                system_prompt_file=str(rel_context)
            )
            
        elif config["type"] == "cursor":
            # Cursor agent handles its own rules via .cursor/rules usually,
            # but we can pass instructions in the prompt.
            # For now, we return the standard agent, prompt injection happens at run time.
            return CursorAgent(self.project_dir)
            
        elif config["type"] == "gemini":
            return GeminiAgent(self.project_dir)
            
        else:
            raise ValueError(f"Unknown agent type: {config['type']}")

    async def run_specialist(
        self,
        agent_id: str,
        prompt: str,
        task_id: str = "unknown",
        **kwargs
    ) -> dict[str, Any]:
        """Run a specialist agent task.

        Args:
            agent_id: Specialist ID (e.g., "A04")
            prompt: The specific task prompt
            task_id: ID of task being executed
            **kwargs: Additional args for the agent run method

        Returns:
            Agent output
        """
        logger.info(f"Running specialist {agent_id} for task {task_id}")
        
        config = self.get_agent_config(agent_id)
        agent = self.create_agent(agent_id)
        
        # Prepend context for non-Claude agents (Claude handles it via system prompt file)
        final_prompt = prompt
        if config["type"] != "claude" and config["context_file"]:
            context_content = config["context_file"].read_text()
            final_prompt = f"{context_content}\n\nTASK:\n{prompt}"

        # Run the agent
        # We use the synchronous run method wrapped in asyncio if needed, 
        # or just rely on the agent's implementation.
        # Note: BaseAgent.run is synchronous currently.
        
        result = agent.run(final_prompt, **kwargs)
        
        return result
