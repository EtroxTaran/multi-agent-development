"""Agent wrappers for CLI tools.

This module provides wrappers for various CLI agents used in the orchestrator:
- ClaudeAgent: Wrapper for Claude Code CLI with enhanced features
- CursorAgent: Wrapper for Cursor CLI
- GeminiAgent: Wrapper for Gemini CLI

Enhanced features available across agents:
- Session continuity for iterative refinement
- Audit trail for debugging and compliance
- Error context preservation for intelligent retries
- Budget control for cost management
- Unified adapter layer for loop execution
"""

from .adapter import (
    AgentAdapter,
    AgentCapabilities,
    AgentType,
    ClaudeAdapter,
    CursorAdapter,
    GeminiAdapter,
    IterationResult,
    create_adapter,
    get_agent_capabilities,
    get_agent_for_task,
    get_available_agents,
)
from .base import AgentResult, BaseAgent
from .budget import (
    AGENT_PRICING,
    BudgetConfig,
    BudgetEnforcementResult,
    BudgetExceeded,
    BudgetManager,
    SpendRecord,
    get_model_pricing,
)
from .claude_agent import ClaudeAgent
from .cursor_agent import CursorAgent
from .error_context import ErrorContext, ErrorContextManager, ErrorType
from .gemini_agent import GeminiAgent
from .session_manager import SessionInfo, SessionManager

__all__ = [
    # Base classes
    "BaseAgent",
    "AgentResult",
    # Agent implementations
    "ClaudeAgent",
    "CursorAgent",
    "GeminiAgent",
    # Session management
    "SessionManager",
    "SessionInfo",
    # Error handling
    "ErrorContextManager",
    "ErrorContext",
    "ErrorType",
    # Budget control
    "BudgetManager",
    "BudgetConfig",
    "BudgetExceeded",
    "BudgetEnforcementResult",
    "SpendRecord",
    "AGENT_PRICING",
    "get_model_pricing",
    # Adapter layer
    "AgentType",
    "AgentAdapter",
    "AgentCapabilities",
    "IterationResult",
    "ClaudeAdapter",
    "CursorAdapter",
    "GeminiAdapter",
    "create_adapter",
    "get_agent_capabilities",
    "get_available_agents",
    "get_agent_for_task",
]
