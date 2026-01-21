"""Agent registry module for multi-agent orchestration."""

from orchestrator.registry.agents import (
    AGENT_REGISTRY,
    get_agent,
    get_agent_reviewers,
    get_all_agents,
    get_agents_by_cli,
    AgentConfig,
)

__all__ = [
    "AGENT_REGISTRY",
    "get_agent",
    "get_agent_reviewers",
    "get_all_agents",
    "get_agents_by_cli",
    "AgentConfig",
]
