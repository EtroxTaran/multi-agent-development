"""Specialist Agent Runner.

Handles loading agent configurations (context, tools) and executing
them using the appropriate CLI wrapper. Supports both single-shot
and iterative (loop) execution modes.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..langgraph.integrations.unified_loop import (
        LoopContext,
        UnifiedLoopConfig,
        UnifiedLoopResult,
    )

from ..agents.base import BaseAgent
from ..agents.claude_agent import ClaudeAgent
from ..agents.cursor_agent import CursorAgent
from ..agents.gemini_agent import GeminiAgent

# Note: unified_loop imports are deferred to avoid circular imports
# These are imported inside run_iterative() method

logger = logging.getLogger(__name__)


class SpecialistRunner:
    """Runs a specific specialist agent with its configured context."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.agents_dir = project_dir / "agents"

    def has_agents_dir(self) -> bool:
        """Check if the agents directory exists and has content.

        Returns:
            True if agents/ directory exists and contains subdirectories
        """
        if not self.agents_dir.exists():
            return False
        if not self.agents_dir.is_dir():
            return False
        # Check if there are any subdirectories
        try:
            return any(p.is_dir() for p in self.agents_dir.iterdir())
        except OSError:
            return False

    def get_agent_config(self, agent_id: str) -> dict[str, Any]:
        """Load configuration for a specialist agent.

        Args:
            agent_id: Agent ID (e.g., "A04-implementer")

        Returns:
            Dictionary with context path, tools, and agent type

        Raises:
            ValueError: If agents directory doesn't exist or agent not found
        """
        # Check if agents directory exists
        if not self.agents_dir.exists():
            raise ValueError(
                f"Agents directory not found: {self.agents_dir}\n"
                f"Projects using specialist agents must have an 'agents/' directory.\n"
                f"If this project doesn't use specialists, the workflow should use "
                f"direct agent invocation instead."
            )

        # Find agent directory matching the ID prefix
        agent_dir = None
        try:
            for path in self.agents_dir.iterdir():
                if path.is_dir() and path.name.startswith(agent_id):
                    agent_dir = path
                    break
        except OSError as e:
            raise ValueError(f"Cannot read agents directory: {e}") from e

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
            "dir": agent_dir,
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
                self.project_dir, allowed_tools=config["tools"], system_prompt_file=str(rel_context)
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
        self, agent_id: str, prompt: str, task_id: str = "unknown", **kwargs
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

        # agent.run returns AgentResult which has a to_dict() method
        # but we return it directly as the callers expect the result object
        return result  # type: ignore[no-any-return]

    async def run_iterative(
        self,
        agent_id: str,
        prompt: str,
        task_id: str,
        context: Optional["LoopContext"] = None,
        config: Optional["UnifiedLoopConfig"] = None,
        **kwargs,
    ) -> "UnifiedLoopResult":
        """Run a specialist agent in iterative loop mode.

        Uses the unified loop runner to iterate until verification passes.
        Works with any agent type (Claude, Cursor, Gemini).

        Args:
            agent_id: Specialist ID (e.g., "A04")
            prompt: The specific task prompt
            task_id: ID of task being executed
            context: Optional loop context with task details
            config: Optional loop configuration override
            **kwargs: Additional config options

        Returns:
            UnifiedLoopResult with execution details
        """
        # Lazy imports to avoid circular dependency
        from ..langgraph.integrations.unified_loop import (
            LoopContext,
            UnifiedLoopConfig,
            UnifiedLoopRunner,
        )

        logger.info(f"Running specialist {agent_id} in iterative mode for task {task_id}")

        # Get agent configuration
        agent_config = self.get_agent_config(agent_id)
        agent_type = agent_config["type"]

        # Build loop configuration
        if config is None:
            config = UnifiedLoopConfig(
                agent_type=agent_type,
                max_iterations=10,
                verification="tests",
                enable_session=(agent_type == "claude"),
                enable_error_context=True,
                enable_budget=True,
                **kwargs,
            )

        # Build loop context
        if context is None:
            context = LoopContext(task_id=task_id)

        # Create and run unified loop
        runner = UnifiedLoopRunner(self.project_dir, config)
        result = await runner.run(task_id, prompt=prompt, context=context)

        return result

    def get_agent_type(self, agent_id: str) -> str:
        """Get the agent type for a specialist.

        Args:
            agent_id: Specialist ID (e.g., "A04")

        Returns:
            Agent type string (claude, cursor, gemini)
        """
        config = self.get_agent_config(agent_id)
        return str(config["type"])

    def get_available_models(self, agent_id: str) -> list[str]:
        """Get available models for a specialist agent.

        Args:
            agent_id: Specialist ID

        Returns:
            List of available model names
        """
        agent_type = self.get_agent_type(agent_id)

        models = {
            "claude": ["sonnet", "opus", "haiku"],
            "cursor": ["codex-5.2", "composer"],
            "gemini": ["gemini-2.0-flash", "gemini-2.0-pro"],
        }

        return models.get(agent_type, [])
