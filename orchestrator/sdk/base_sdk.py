"""Base SDK agent class for async API calls.

Provides the foundation for SDK-based agents that communicate directly
with AI APIs instead of using CLI wrappers.
"""

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Type, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class TokenUsageInfo:
    """Token usage information from API calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used in the request."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "total_tokens": self.total_tokens,
        }

    def estimate_cost(self, input_price_per_m: float, output_price_per_m: float) -> float:
        """Estimate cost based on token usage.

        Args:
            input_price_per_m: Price per million input tokens
            output_price_per_m: Price per million output tokens

        Returns:
            Estimated cost in dollars
        """
        input_cost = (self.input_tokens / 1_000_000) * input_price_per_m
        output_cost = (self.output_tokens / 1_000_000) * output_price_per_m
        return input_cost + output_cost


@dataclass
class SDKResult:
    """Result from an SDK agent execution.

    Enhanced version of AgentResult with token usage tracking and
    model information.
    """

    success: bool
    output: Optional[str] = None
    parsed_output: Optional[dict] = None
    error: Optional[str] = None
    usage: Optional[TokenUsageInfo] = None
    duration_seconds: float = 0.0
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    raw_response: Optional[Any] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "parsed_output": self.parsed_output,
            "error": self.error,
            "usage": self.usage.to_dict() if self.usage else None,
            "duration_seconds": self.duration_seconds,
            "model": self.model,
            "stop_reason": self.stop_reason,
        }

    def to_agent_result(self) -> "AgentResult":
        """Convert to legacy AgentResult for compatibility."""
        from ..agents.base import AgentResult

        return AgentResult(
            success=self.success,
            output=self.output,
            parsed_output=self.parsed_output,
            error=self.error,
            exit_code=0 if self.success else 1,
            duration_seconds=self.duration_seconds,
        )


@dataclass
class SDKConfig:
    """Configuration for SDK agents."""

    # API settings
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    # Model settings
    model: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0

    # Timeout settings
    timeout_seconds: int = 300
    connect_timeout_seconds: int = 30

    # Retry settings
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 60.0

    # Rate limiting
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000

    # Feature flags
    enable_streaming: bool = True
    enable_caching: bool = True


class BaseSDKAgent(ABC):
    """Base class for SDK-based agent implementations.

    Provides async-first API for interacting with AI services directly
    through their SDKs rather than CLI wrappers.

    Features:
    - Async context manager for proper resource management
    - Token usage tracking
    - Streaming support
    - JSON schema validation for structured outputs
    - Automatic retry with exponential backoff
    """

    name: str = "base_sdk"
    default_model: str = ""

    # Pricing per million tokens (override in subclasses)
    input_price_per_m: float = 0.0
    output_price_per_m: float = 0.0

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        config: Optional[SDKConfig] = None,
    ):
        """Initialize the SDK agent.

        Args:
            project_dir: Root directory of the project
            config: SDK configuration
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.config = config or SDKConfig()
        self._client: Optional[Any] = None
        self._initialized = False

    @abstractmethod
    async def _create_client(self) -> Any:
        """Create the SDK client.

        Returns:
            The initialized SDK client
        """
        pass

    @abstractmethod
    async def _close_client(self) -> None:
        """Close the SDK client and release resources."""
        pass

    @abstractmethod
    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_schema: Optional[Type[T]] = None,
    ) -> SDKResult:
        """Implementation of generate logic.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            response_schema: Pydantic model for structured output

        Returns:
            SDKResult with generation results
        """
        pass

    @abstractmethod
    async def _generate_stream_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Implementation of streaming generation.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they are generated
        """
        pass

    async def __aenter__(self) -> "BaseSDKAgent":
        """Async context manager entry."""
        if not self._initialized:
            self._client = await self._create_client()
            self._initialized = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._initialized:
            await self._close_client()
            self._client = None
            self._initialized = False

    def _get_api_key(self, env_var: str) -> Optional[str]:
        """Get API key from config or environment.

        Args:
            env_var: Environment variable name

        Returns:
            API key or None
        """
        return self.config.api_key or os.environ.get(env_var)

    def _get_model(self) -> str:
        """Get model to use."""
        return self.config.model or self.default_model

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_schema: Optional[Type[T]] = None,
    ) -> SDKResult:
        """Generate a response from the AI model.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate (defaults to config)
            temperature: Sampling temperature (defaults to config)
            response_schema: Pydantic model for structured output

        Returns:
            SDKResult with generation results

        Raises:
            RuntimeError: If not initialized via context manager
        """
        if not self._initialized:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as async context manager"
            )

        start_time = time.time()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        try:
            result = await self._generate_impl(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                response_schema=response_schema,
            )
            result.duration_seconds = time.time() - start_time
            return result

        except Exception as e:
            logger.error(f"Generation failed: {type(e).__name__}: {e}")
            return SDKResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                duration_seconds=time.time() - start_time,
                model=self._get_model(),
            )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the AI model.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they are generated

        Raises:
            RuntimeError: If not initialized via context manager
        """
        if not self._initialized:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as async context manager"
            )

        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        async for chunk in self._generate_stream_impl(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield chunk

    async def generate_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_schema: Optional[Type[T]] = None,
        max_retries: Optional[int] = None,
    ) -> SDKResult:
        """Generate with automatic retry on failure.

        Uses exponential backoff for retries.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            response_schema: Pydantic model for structured output
            max_retries: Override default max retries

        Returns:
            SDKResult with generation results
        """
        max_retries = max_retries or self.config.max_retries
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            result = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                response_schema=response_schema,
            )

            if result.success:
                return result

            last_error = Exception(result.error)

            if attempt < max_retries - 1:
                delay = min(
                    self.config.retry_delay_base * (2 ** attempt),
                    self.config.retry_delay_max,
                )
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {result.error}"
                )
                await asyncio.sleep(delay)

        return SDKResult(
            success=False,
            error=f"All {max_retries} retries failed: {last_error}",
            model=self._get_model(),
        )

    def estimate_cost(self, usage: TokenUsageInfo) -> float:
        """Estimate cost for token usage.

        Args:
            usage: Token usage information

        Returns:
            Estimated cost in dollars
        """
        return usage.estimate_cost(self.input_price_per_m, self.output_price_per_m)

    @classmethod
    def is_available(cls) -> bool:
        """Check if this SDK agent is available (API key set).

        Returns:
            True if the required API key is available
        """
        return False  # Override in subclasses

    def get_context_file(self) -> Optional[Path]:
        """Get the context file path for this agent."""
        return None

    def read_context_file(self) -> Optional[str]:
        """Read the context file content if it exists."""
        context_file = self.get_context_file()
        if context_file and context_file.exists():
            return context_file.read_text()
        return None


def parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from a response that may contain markdown code blocks.

    Args:
        text: Response text that may contain JSON

    Returns:
        Parsed JSON dict or None if parsing fails
    """
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code block
    import re

    json_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object in text
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None
