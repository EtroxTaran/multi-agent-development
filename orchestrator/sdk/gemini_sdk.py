"""Gemini SDK agent using the Google GenAI API.

Provides direct API integration with Gemini models for validation
and architecture review phases.
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
GOOGLE_API_KEY_ENV = "GOOGLE_API_KEY"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"


class GeminiSDKAgent(BaseSDKAgent):
    """SDK agent for Gemini using the Google GenAI API.

    Features:
    - Direct API calls with async support
    - Streaming responses
    - Token usage tracking
    - Structured output with JSON mode

    Example:
        async with GeminiSDKAgent() as agent:
            result = await agent.generate("Review this architecture")
            print(result.output)
    """

    name = "gemini_sdk"
    default_model = "gemini-2.0-flash"

    # Gemini pricing per million tokens (Flash)
    input_price_per_m = 0.075
    output_price_per_m = 0.30

    # Supported models
    SUPPORTED_MODELS = {
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-lite": {"input": 0.0375, "output": 0.15},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
    }

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        config: Optional[SDKConfig] = None,
        model: Optional[str] = None,
    ):
        """Initialize Gemini SDK agent.

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

    def _get_api_key(self, env_var: str = GOOGLE_API_KEY_ENV) -> Optional[str]:
        """Get API key from config or environment.

        Checks both GOOGLE_API_KEY and GEMINI_API_KEY.
        """
        if self.config.api_key:
            return self.config.api_key
        return os.environ.get(GOOGLE_API_KEY_ENV) or os.environ.get(GEMINI_API_KEY_ENV)

    async def _create_client(self) -> Any:
        """Create the Google GenAI client."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Install with: pip install google-genai"
            )

        api_key = self._get_api_key()
        if not api_key:
            raise ValueError(
                f"Google API key not found. Set {GOOGLE_API_KEY_ENV} or {GEMINI_API_KEY_ENV} "
                "environment variable or pass api_key in config."
            )

        # Create async client
        client = genai.Client(api_key=api_key)
        return client

    async def _close_client(self) -> None:
        """Close the Google GenAI client."""
        # google-genai client doesn't need explicit closing
        self._client = None

    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_schema: Optional[Type[T]] = None,
    ) -> SDKResult:
        """Generate a response using the Google GenAI API.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            response_schema: Pydantic model for structured output

        Returns:
            SDKResult with generation results
        """
        try:
            from google.genai import types
        except ImportError:
            return SDKResult(
                success=False,
                error="google-genai package not installed",
            )

        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        # Build config
        config_dict: dict[str, Any] = {}

        if max_tokens:
            config_dict["max_output_tokens"] = max_tokens

        if temperature is not None:
            config_dict["temperature"] = temperature

        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        # If schema provided, enable JSON mode
        if response_schema:
            config_dict["response_mime_type"] = "application/json"
            config_dict["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_dict) if config_dict else None

        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            # Extract text
            output_text = response.text if response.text else ""

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
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = TokenUsageInfo(
                    input_tokens=response.usage_metadata.prompt_token_count or 0,
                    output_tokens=response.usage_metadata.candidates_token_count or 0,
                    cache_read_tokens=getattr(
                        response.usage_metadata, "cached_content_token_count", 0
                    )
                    or 0,
                )

            # Get stop reason
            stop_reason = None
            if response.candidates and response.candidates[0].finish_reason:
                stop_reason = response.candidates[0].finish_reason.name

            return SDKResult(
                success=True,
                output=output_text,
                parsed_output=parsed_output,
                usage=usage,
                model=model,
                stop_reason=stop_reason,
                raw_response=response,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Gemini API error: {error_msg}")
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
        """Stream a response using the Google GenAI API.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they are generated
        """
        try:
            from google.genai import types
        except ImportError:
            raise ImportError("google-genai package not installed")

        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        # Build config
        config_dict: dict[str, Any] = {}

        if max_tokens:
            config_dict["max_output_tokens"] = max_tokens

        if temperature is not None:
            config_dict["temperature"] = temperature

        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        config = types.GenerateContentConfig(**config_dict) if config_dict else None

        try:
            async for chunk in self._client.aio.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error(f"Gemini streaming error: {type(e).__name__}: {e}")
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
            tools: List of tool definitions (Gemini format)
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            SDKResult with generation results and tool calls
        """
        try:
            from google.genai import types
        except ImportError:
            return SDKResult(
                success=False,
                error="google-genai package not installed",
            )

        model = self._get_model()
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        # Build config
        config_dict: dict[str, Any] = {
            "tools": tools,
        }

        if max_tokens:
            config_dict["max_output_tokens"] = max_tokens

        if temperature is not None:
            config_dict["temperature"] = temperature

        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        config = types.GenerateContentConfig(**config_dict)

        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            # Extract content
            text_content = response.text if response.text else ""
            tool_calls = []

            # Check for function calls
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        tool_calls.append(
                            {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args),
                            }
                        )

            # Build parsed output
            parsed_output = {
                "text": text_content,
                "tool_calls": tool_calls,
            }

            usage = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = TokenUsageInfo(
                    input_tokens=response.usage_metadata.prompt_token_count or 0,
                    output_tokens=response.usage_metadata.candidates_token_count or 0,
                )

            return SDKResult(
                success=True,
                output=text_content,
                parsed_output=parsed_output,
                usage=usage,
                model=model,
                raw_response=response,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Gemini API error with tools: {error_msg}")
            return SDKResult(
                success=False,
                error=error_msg,
                model=model,
            )

    def get_context_file(self) -> Optional[Path]:
        """Get Gemini's context file."""
        return self.project_dir / "GEMINI.md"

    @classmethod
    def is_available(cls) -> bool:
        """Check if Google API key is available."""
        return bool(
            os.environ.get(GOOGLE_API_KEY_ENV) or os.environ.get(GEMINI_API_KEY_ENV)
        )


# Convenience function for one-off calls
async def gemini_generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> SDKResult:
    """Convenience function for one-off Gemini API calls.

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

    async with GeminiSDKAgent(config=config) as agent:
        return await agent.generate(prompt, system_prompt=system_prompt)
