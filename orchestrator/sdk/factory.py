"""Agent factory with automatic SDK/CLI fallback.

Provides a unified interface for creating agents that automatically
selects SDK or CLI implementations based on availability and configuration.
"""

import asyncio
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from .base_sdk import BaseSDKAgent, SDKConfig, SDKResult
from .claude_sdk import ClaudeSDKAgent
from .gemini_sdk import GeminiSDKAgent

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of agents available."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    CURSOR = "cursor"


class AgentMode(str, Enum):
    """Agent execution mode."""

    SDK = "sdk"  # Direct SDK calls (preferred)
    CLI = "cli"  # CLI subprocess calls (fallback)
    AUTO = "auto"  # Auto-select based on availability


# Environment variables for controlling agent mode
ENV_USE_SDK = "ORCHESTRATOR_USE_SDK"
ENV_CLAUDE_USE_SDK = "CLAUDE_USE_SDK"
ENV_GEMINI_USE_SDK = "GEMINI_USE_SDK"


def get_agent_mode(agent_type: AgentType) -> AgentMode:
    """Determine the mode for an agent based on environment variables.

    Args:
        agent_type: The type of agent

    Returns:
        AgentMode to use
    """
    # Check agent-specific override first
    if agent_type == AgentType.CLAUDE:
        env_val = os.environ.get(ENV_CLAUDE_USE_SDK)
    elif agent_type == AgentType.GEMINI:
        env_val = os.environ.get(ENV_GEMINI_USE_SDK)
    else:
        env_val = None

    # Fall back to global setting
    if env_val is None:
        env_val = os.environ.get(ENV_USE_SDK)

    if env_val is None:
        return AgentMode.AUTO
    elif env_val.lower() in ("true", "1", "yes"):
        return AgentMode.SDK
    elif env_val.lower() in ("false", "0", "no"):
        return AgentMode.CLI
    else:
        return AgentMode.AUTO


class AgentFactory:
    """Factory for creating agents with automatic fallback.

    Features:
    - Auto-detects SDK availability
    - Falls back to CLI if SDK not available
    - Consistent interface across implementations
    - Environment variable control

    Example:
        factory = AgentFactory(project_dir="/path/to/project")

        # Get Claude agent (SDK if available, CLI otherwise)
        claude = factory.get_claude_agent()

        # Force SDK mode
        claude_sdk = factory.get_claude_agent(mode=AgentMode.SDK)

        # Run generation
        result = await factory.generate(
            agent_type=AgentType.CLAUDE,
            prompt="Explain this code",
        )
    """

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        sdk_config: Optional[SDKConfig] = None,
        default_mode: AgentMode = AgentMode.AUTO,
    ):
        """Initialize the agent factory.

        Args:
            project_dir: Root directory of the project
            sdk_config: Configuration for SDK agents
            default_mode: Default mode for creating agents
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.sdk_config = sdk_config or SDKConfig()
        self.default_mode = default_mode

        # Cache SDK availability
        self._sdk_available: dict[AgentType, bool] = {}

    def is_sdk_available(self, agent_type: AgentType) -> bool:
        """Check if SDK is available for an agent type.

        Args:
            agent_type: The type of agent to check

        Returns:
            True if SDK is available
        """
        if agent_type in self._sdk_available:
            return self._sdk_available[agent_type]

        available = False
        if agent_type == AgentType.CLAUDE:
            available = ClaudeSDKAgent.is_available()
        elif agent_type == AgentType.GEMINI:
            available = GeminiSDKAgent.is_available()
        elif agent_type == AgentType.CURSOR:
            # Cursor has no SDK, always use CLI
            available = False

        self._sdk_available[agent_type] = available
        return available

    def _resolve_mode(self, agent_type: AgentType, mode: Optional[AgentMode] = None) -> AgentMode:
        """Resolve the actual mode to use.

        Args:
            agent_type: The type of agent
            mode: Requested mode (or None for default)

        Returns:
            Resolved AgentMode
        """
        if mode is None:
            mode = get_agent_mode(agent_type)
            if mode == AgentMode.AUTO:
                mode = self.default_mode

        if mode == AgentMode.AUTO:
            # Auto-select based on availability
            if self.is_sdk_available(agent_type):
                return AgentMode.SDK
            else:
                return AgentMode.CLI

        return mode

    def get_claude_agent(
        self,
        mode: Optional[AgentMode] = None,
        model: Optional[str] = None,
    ) -> Union[ClaudeSDKAgent, "ClaudeAgent"]:
        """Get a Claude agent.

        Args:
            mode: Execution mode (SDK, CLI, or AUTO)
            model: Model to use

        Returns:
            Claude agent (SDK or CLI)
        """
        resolved_mode = self._resolve_mode(AgentType.CLAUDE, mode)

        if resolved_mode == AgentMode.SDK:
            if not self.is_sdk_available(AgentType.CLAUDE):
                logger.warning("Claude SDK requested but not available, falling back to CLI")
                resolved_mode = AgentMode.CLI

        if resolved_mode == AgentMode.SDK:
            return ClaudeSDKAgent(
                project_dir=self.project_dir,
                config=self.sdk_config,
                model=model,
            )
        else:
            from ..agents.claude_agent import ClaudeAgent

            return ClaudeAgent(
                project_dir=self.project_dir,
                timeout=self.sdk_config.timeout_seconds,
            )

    def get_gemini_agent(
        self,
        mode: Optional[AgentMode] = None,
        model: Optional[str] = None,
    ) -> Union[GeminiSDKAgent, "GeminiAgent"]:
        """Get a Gemini agent.

        Args:
            mode: Execution mode (SDK, CLI, or AUTO)
            model: Model to use

        Returns:
            Gemini agent (SDK or CLI)
        """
        resolved_mode = self._resolve_mode(AgentType.GEMINI, mode)

        if resolved_mode == AgentMode.SDK:
            if not self.is_sdk_available(AgentType.GEMINI):
                logger.warning("Gemini SDK requested but not available, falling back to CLI")
                resolved_mode = AgentMode.CLI

        if resolved_mode == AgentMode.SDK:
            return GeminiSDKAgent(
                project_dir=self.project_dir,
                config=self.sdk_config,
                model=model,
            )
        else:
            from ..agents.gemini_agent import GeminiAgent

            return GeminiAgent(
                project_dir=self.project_dir,
                timeout=self.sdk_config.timeout_seconds,
            )

    def get_cursor_agent(self) -> "CursorAgent":
        """Get a Cursor agent.

        Cursor always uses CLI (no SDK available).

        Returns:
            Cursor CLI agent
        """
        from ..agents.cursor_agent import CursorAgent

        return CursorAgent(
            project_dir=self.project_dir,
            timeout=self.sdk_config.timeout_seconds,
        )

    async def generate(
        self,
        agent_type: AgentType,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        mode: Optional[AgentMode] = None,
    ) -> SDKResult:
        """Generate a response using the specified agent.

        Handles both SDK and CLI agents transparently.

        Args:
            agent_type: Type of agent to use
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            mode: Execution mode

        Returns:
            SDKResult with generation results
        """
        resolved_mode = self._resolve_mode(agent_type, mode)

        if resolved_mode == AgentMode.SDK and agent_type != AgentType.CURSOR:
            return await self._generate_sdk(
                agent_type=agent_type,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            return await self._generate_cli(
                agent_type=agent_type,
                prompt=prompt,
            )

    async def _generate_sdk(
        self,
        agent_type: AgentType,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> SDKResult:
        """Generate using SDK agent.

        Args:
            agent_type: Type of agent to use
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            SDKResult with generation results
        """
        if agent_type == AgentType.CLAUDE:
            agent = self.get_claude_agent(mode=AgentMode.SDK)
        elif agent_type == AgentType.GEMINI:
            agent = self.get_gemini_agent(mode=AgentMode.SDK)
        else:
            raise ValueError(f"No SDK available for {agent_type}")

        async with agent:
            return await agent.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    async def _generate_cli(
        self,
        agent_type: AgentType,
        prompt: str,
    ) -> SDKResult:
        """Generate using CLI agent.

        Runs CLI agent in a thread pool to avoid blocking.

        Args:
            agent_type: Type of agent to use
            prompt: The user prompt

        Returns:
            SDKResult with generation results
        """
        if agent_type == AgentType.CLAUDE:
            agent = self.get_claude_agent(mode=AgentMode.CLI)
        elif agent_type == AgentType.GEMINI:
            agent = self.get_gemini_agent(mode=AgentMode.CLI)
        elif agent_type == AgentType.CURSOR:
            agent = self.get_cursor_agent()
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Run CLI agent in thread pool
        loop = asyncio.get_event_loop()
        cli_result = await loop.run_in_executor(None, agent.run, prompt)

        # Convert to SDKResult
        return SDKResult(
            success=cli_result.success,
            output=cli_result.output,
            parsed_output=cli_result.parsed_output,
            error=cli_result.error,
            duration_seconds=cli_result.duration_seconds,
        )

    def get_availability_report(self) -> dict:
        """Get a report of agent availability.

        Returns:
            Dictionary with availability information
        """
        from ..agents.claude_agent import ClaudeAgent
        from ..agents.cursor_agent import CursorAgent
        from ..agents.gemini_agent import GeminiAgent

        return {
            "claude": {
                "sdk_available": self.is_sdk_available(AgentType.CLAUDE),
                "cli_available": ClaudeAgent(self.project_dir).check_available(),
                "mode": get_agent_mode(AgentType.CLAUDE).value,
            },
            "gemini": {
                "sdk_available": self.is_sdk_available(AgentType.GEMINI),
                "cli_available": GeminiAgent(self.project_dir).check_available(),
                "mode": get_agent_mode(AgentType.GEMINI).value,
            },
            "cursor": {
                "sdk_available": False,
                "cli_available": CursorAgent(self.project_dir).check_available(),
                "mode": "cli",
            },
        }


# Global factory instance for convenience
_default_factory: Optional[AgentFactory] = None


def get_default_factory(project_dir: Optional[str | Path] = None) -> AgentFactory:
    """Get or create the default agent factory.

    Args:
        project_dir: Project directory (only used on first call)

    Returns:
        Default AgentFactory instance
    """
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory(project_dir=project_dir)
    return _default_factory


def reset_default_factory() -> None:
    """Reset the default factory."""
    global _default_factory
    _default_factory = None
