"""SDK-based agent implementations for direct API calls.

This module provides async SDK wrappers for AI APIs, replacing subprocess-based
CLI calls with direct API integrations for better performance and control.

Key components:
- BaseSDKAgent: Abstract base class for SDK agents
- SDKResult: Standardized result dataclass with token usage tracking
- ClaudeSDKAgent: Anthropic API wrapper
- GeminiSDKAgent: Google GenAI API wrapper
- AgentFactory: Factory with automatic fallback to CLI agents
"""

from .base_sdk import BaseSDKAgent, SDKConfig, SDKResult, TokenUsageInfo, parse_json_response
from .claude_sdk import ClaudeSDKAgent, claude_generate
from .gemini_sdk import GeminiSDKAgent, gemini_generate
from .factory import AgentFactory, AgentType, AgentMode, get_default_factory
from .rate_limiter import (
    AsyncRateLimiter,
    RateLimitConfig,
    RateLimitStats,
    get_rate_limiter,
    CLAUDE_RATE_LIMIT,
    GEMINI_RATE_LIMIT,
)
from .streaming import (
    StreamingHandler,
    StreamingConfig,
    StreamingResult,
    StreamBuffer,
    stream_to_string,
    stream_with_handler,
    stream_with_callback,
    stream_with_progress,
    buffered_stream,
)

__all__ = [
    # Base
    "BaseSDKAgent",
    "SDKConfig",
    "SDKResult",
    "TokenUsageInfo",
    "parse_json_response",
    # Agents
    "ClaudeSDKAgent",
    "GeminiSDKAgent",
    "claude_generate",
    "gemini_generate",
    # Factory
    "AgentFactory",
    "AgentType",
    "AgentMode",
    "get_default_factory",
    # Rate Limiting
    "AsyncRateLimiter",
    "RateLimitConfig",
    "RateLimitStats",
    "get_rate_limiter",
    "CLAUDE_RATE_LIMIT",
    "GEMINI_RATE_LIMIT",
    # Streaming
    "StreamingHandler",
    "StreamingConfig",
    "StreamingResult",
    "StreamBuffer",
    "stream_to_string",
    "stream_with_handler",
    "stream_with_callback",
    "stream_with_progress",
    "buffered_stream",
]
