"""Claude SDK agent using the Anthropic API.

Provides direct API integration with Claude models for planning
and implementation phases.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Type, TypeVar

from pydantic import BaseModel

from .base_sdk import BaseSDKAgent, SDKConfig, SDKResult, TokenUsageInfo, parse_json_response

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Environment variable for API key
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"


class ClaudeSDKAgent(BaseSDKAgent):
    """SDK agent for Claude using the Anthropic API.

    Features:
    - Direct API calls with async support
    - Streaming responses
    - Token usage tracking with cost estimation
    - Structured output with JSON schema
    - Automatic prompt caching support

    Example:
        async with ClaudeSDKAgent() as agent:
            result = await agent.generate("Explain quantum computing")
            print(result.output)
            print(f"Tokens used: {result.usage.total_tokens}")
    """

    name = "claude_sdk"
    default_model = "claude-sonnet-4-20250514"

    # Claude pricing per million tokens (Sonnet 4)
    input_price_per_m = 3.0
    output_price_per_m = 15.0

    # Supported models
    SUPPORTED_MODELS = {
        "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.0},
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    }

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        config: Optional[SDKConfig] = None,
        model: Optional[str] = None,
    ):
        """Initialize Claude SDK agent.

        Args:
            project_dir: Root directory of the project
            config: SDK configuration
            model: Model to use (overrides config.model)
        """
        super().__init__(project_dir, config)
        if model:
            self.config.model = model

        # Update pricing based on model
        model_name = self._get_model()
        if model_name in self.SUPPORTED_MODELS:
            pricing = self.SUPPORTED_MODELS[model_name]
            self.input_price_per_m = pricing["input"]
            self.output_price_per_m = pricing["output"]

    async def _create_client(self) -> Any:
        """Create the Anthropic client."""
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        api_key = self._get_api_key(ANTHROPIC_API_KEY_ENV)
        if not api_key:
            raise ValueError(
                f"Anthropic API key not found. Set {ANTHROPIC_API_KEY_ENV} environment variable "
                "or pass api_key in config."
            )

        return AsyncAnthropic(
            api_key=api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_retries=0,  # We handle retries ourselves
        )

    async def _close_client(self) -> None:
        """Close the Anthropic client."""
        if self._client:
            await self._client.close()

    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_schema: Optional[Type[T]] = None,
    ) -> SDKResult:
        """Generate a response using the Anthropic API.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            response_schema: Pydantic model for structured output

        Returns:
            SDKResult with generation results
        """
        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        messages = [{"role": "user", "content": prompt}]

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)

            # Extract text content
            output_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    output_text += block.text

            # Parse JSON if present
            parsed_output = parse_json_response(output_text)

            # If schema provided, validate
            if response_schema and parsed_output:
                try:
                    validated = response_schema.model_validate(parsed_output)
                    parsed_output = validated.model_dump()
                except Exception as e:
                    logger.warning(f"Schema validation failed: {e}")

            # Extract usage
            usage = None
            if response.usage:
                usage = TokenUsageInfo(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                    cache_creation_tokens=getattr(
                        response.usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                )

            return SDKResult(
                success=True,
                output=output_text,
                parsed_output=parsed_output,
                usage=usage,
                model=model,
                stop_reason=response.stop_reason,
                raw_response=response,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Claude API error: {error_msg}")
            return SDKResult(
                success=False,
                error=error_msg,
                model=model,
            )

    async def _generate_stream_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Stream a response using the Anthropic API.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they are generated
        """
        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        messages = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.error(f"Claude streaming error: {type(e).__name__}: {e}")
            raise

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> SDKResult:
        """Generate a response with tool use support.

        Args:
            prompt: The user prompt
            tools: List of tool definitions
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            SDKResult with generation results and tool calls
        """
        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        messages = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.messages.create(**kwargs)

            # Extract content
            text_content = ""
            tool_calls = []

            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            # Build parsed output
            parsed_output = {
                "text": text_content,
                "tool_calls": tool_calls,
            }

            usage = None
            if response.usage:
                usage = TokenUsageInfo(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )

            return SDKResult(
                success=True,
                output=text_content,
                parsed_output=parsed_output,
                usage=usage,
                model=model,
                stop_reason=response.stop_reason,
                raw_response=response,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Claude API error with tools: {error_msg}")
            return SDKResult(
                success=False,
                error=error_msg,
                model=model,
            )

    def get_context_file(self) -> Optional[Path]:
        """Get Claude's context file."""
        return self.project_dir / "CLAUDE.md"

    @classmethod
    def is_available(cls) -> bool:
        """Check if Anthropic API key is available."""
        return bool(os.environ.get(ANTHROPIC_API_KEY_ENV))


# Convenience function for one-off calls
async def claude_generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> SDKResult:
    """Convenience function for one-off Claude API calls.

    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt
        model: Model to use
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        SDKResult with generation results
    """
    config = SDKConfig(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    async with ClaudeSDKAgent(config=config) as agent:
        return await agent.generate(prompt, system_prompt=system_prompt)
