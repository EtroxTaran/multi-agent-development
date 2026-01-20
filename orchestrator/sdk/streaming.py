"""Streaming response handlers for SDK agents.

Provides utilities for handling streamed responses from AI APIs,
including progress tracking, buffering, and parsing.
"""

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """Configuration for streaming handlers."""

    # Buffering
    buffer_size: int = 1024  # Characters to buffer before processing
    flush_interval: float = 0.1  # Seconds between flushes

    # Progress
    show_progress: bool = True
    progress_interval: float = 1.0  # Seconds between progress updates

    # Parsing
    extract_json: bool = True  # Try to extract JSON from stream
    json_start_markers: list[str] = field(default_factory=lambda: ["{", "["])
    json_end_markers: list[str] = field(default_factory=lambda: ["}", "]"])

    # Output
    print_to_stdout: bool = False
    callback: Optional[Callable[[str], None]] = None


@dataclass
class StreamingResult:
    """Result from streaming completion."""

    full_text: str
    chunks: list[str]
    parsed_json: Optional[dict | list] = None
    duration_seconds: float = 0.0
    total_chunks: int = 0
    tokens_streamed: int = 0  # Approximate based on whitespace splits


class StreamingHandler:
    """Handler for streaming API responses.

    Features:
    - Buffered output processing
    - JSON extraction from streamed text
    - Progress tracking
    - Callback support for real-time processing

    Example:
        handler = StreamingHandler()

        async for chunk in agent.generate_stream("Hello"):
            await handler.process_chunk(chunk)

        result = handler.get_result()
        print(result.full_text)
    """

    def __init__(self, config: Optional[StreamingConfig] = None):
        """Initialize streaming handler.

        Args:
            config: Streaming configuration
        """
        self.config = config or StreamingConfig()
        self._chunks: list[str] = []
        self._buffer = ""
        self._json_buffer = ""
        self._in_json = False
        self._json_depth = 0
        self._start_time: Optional[float] = None
        self._last_progress_time: float = 0
        self._chars_received: int = 0

    def reset(self) -> None:
        """Reset handler state for reuse."""
        self._chunks = []
        self._buffer = ""
        self._json_buffer = ""
        self._in_json = False
        self._json_depth = 0
        self._start_time = None
        self._last_progress_time = 0
        self._chars_received = 0

    async def process_chunk(self, chunk: str) -> None:
        """Process a streamed chunk.

        Args:
            chunk: Text chunk from stream
        """
        if self._start_time is None:
            self._start_time = time.monotonic()

        self._chunks.append(chunk)
        self._buffer += chunk
        self._chars_received += len(chunk)

        # Track JSON if enabled
        if self.config.extract_json:
            self._track_json(chunk)

        # Print to stdout if enabled
        if self.config.print_to_stdout:
            sys.stdout.write(chunk)
            sys.stdout.flush()

        # Call callback if provided
        if self.config.callback:
            try:
                self.config.callback(chunk)
            except Exception as e:
                logger.warning(f"Streaming callback error: {e}")

        # Show progress if enabled
        if self.config.show_progress:
            await self._show_progress()

    def _track_json(self, chunk: str) -> None:
        """Track JSON structure in streamed text.

        Args:
            chunk: Text chunk to analyze
        """
        for char in chunk:
            if not self._in_json:
                # Look for JSON start
                if char in self.config.json_start_markers:
                    self._in_json = True
                    self._json_depth = 1
                    self._json_buffer = char
            else:
                self._json_buffer += char

                if char in self.config.json_start_markers:
                    self._json_depth += 1
                elif char in self.config.json_end_markers:
                    self._json_depth -= 1

                    if self._json_depth == 0:
                        # Complete JSON object
                        self._in_json = False

    async def _show_progress(self) -> None:
        """Show streaming progress."""
        now = time.monotonic()
        if now - self._last_progress_time >= self.config.progress_interval:
            elapsed = now - (self._start_time or now)
            chars_per_sec = self._chars_received / elapsed if elapsed > 0 else 0

            logger.debug(
                f"Streaming: {self._chars_received} chars, "
                f"{len(self._chunks)} chunks, "
                f"{chars_per_sec:.0f} chars/sec"
            )
            self._last_progress_time = now

    def get_result(self) -> StreamingResult:
        """Get the streaming result.

        Returns:
            StreamingResult with collected data
        """
        full_text = "".join(self._chunks)
        duration = time.monotonic() - (self._start_time or time.monotonic())

        # Parse JSON if we have a complete buffer
        parsed_json = None
        if self.config.extract_json and self._json_buffer:
            try:
                parsed_json = json.loads(self._json_buffer)
            except json.JSONDecodeError:
                # Try to extract JSON from full text
                parsed_json = self._extract_json_from_text(full_text)

        # Approximate token count
        tokens_approx = len(full_text.split())

        return StreamingResult(
            full_text=full_text,
            chunks=self._chunks,
            parsed_json=parsed_json,
            duration_seconds=duration,
            total_chunks=len(self._chunks),
            tokens_streamed=tokens_approx,
        )

    def _extract_json_from_text(self, text: str) -> Optional[dict | list]:
        """Try to extract JSON from text.

        Args:
            text: Text that may contain JSON

        Returns:
            Parsed JSON or None
        """
        # Try to find JSON in markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try to find JSON array
        bracket_match = re.search(r"\[[\s\S]*\]", text)
        if bracket_match:
            try:
                return json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                pass

        return None


async def stream_to_string(stream: AsyncIterator[str]) -> str:
    """Collect a stream into a single string.

    Args:
        stream: Async iterator of text chunks

    Returns:
        Concatenated string
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return "".join(chunks)


async def stream_with_handler(
    stream: AsyncIterator[str],
    handler: Optional[StreamingHandler] = None,
) -> StreamingResult:
    """Process a stream with a handler.

    Args:
        stream: Async iterator of text chunks
        handler: Optional handler (creates default if not provided)

    Returns:
        StreamingResult with collected data
    """
    if handler is None:
        handler = StreamingHandler()

    handler.reset()

    async for chunk in stream:
        await handler.process_chunk(chunk)

    return handler.get_result()


async def stream_with_callback(
    stream: AsyncIterator[str],
    callback: Callable[[str], None],
) -> str:
    """Process a stream with a callback.

    Args:
        stream: Async iterator of text chunks
        callback: Function to call with each chunk

    Returns:
        Full concatenated text
    """
    config = StreamingConfig(callback=callback)
    handler = StreamingHandler(config)
    result = await stream_with_handler(stream, handler)
    return result.full_text


async def stream_with_progress(
    stream: AsyncIterator[str],
    print_chunks: bool = True,
) -> StreamingResult:
    """Process a stream with progress output.

    Args:
        stream: Async iterator of text chunks
        print_chunks: Whether to print chunks to stdout

    Returns:
        StreamingResult with collected data
    """
    config = StreamingConfig(
        show_progress=True,
        print_to_stdout=print_chunks,
    )
    handler = StreamingHandler(config)
    return await stream_with_handler(stream, handler)


class StreamBuffer:
    """Async buffer for managing streamed content.

    Useful for processing streams in batches or with backpressure.
    """

    def __init__(self, max_size: int = 10000):
        """Initialize buffer.

        Args:
            max_size: Maximum buffer size in characters
        """
        self.max_size = max_size
        self._buffer: list[str] = []
        self._size = 0
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        self._not_full = asyncio.Event()
        self._not_full.set()
        self._closed = False

    async def put(self, chunk: str) -> None:
        """Add a chunk to the buffer.

        Args:
            chunk: Text chunk to add
        """
        while self._size + len(chunk) > self.max_size and not self._closed:
            self._not_full.clear()
            await self._not_full.wait()

        async with self._lock:
            self._buffer.append(chunk)
            self._size += len(chunk)
            self._not_empty.set()

    async def get(self) -> Optional[str]:
        """Get a chunk from the buffer.

        Returns:
            Text chunk or None if buffer closed and empty
        """
        while not self._buffer:
            if self._closed:
                return None
            self._not_empty.clear()
            await self._not_empty.wait()

        async with self._lock:
            chunk = self._buffer.pop(0)
            self._size -= len(chunk)
            self._not_full.set()
            return chunk

    async def get_all(self) -> str:
        """Get all content from buffer.

        Returns:
            Concatenated buffer content
        """
        async with self._lock:
            content = "".join(self._buffer)
            self._buffer.clear()
            self._size = 0
            self._not_full.set()
            return content

    def close(self) -> None:
        """Close the buffer."""
        self._closed = True
        self._not_empty.set()
        self._not_full.set()

    @property
    def is_closed(self) -> bool:
        """Check if buffer is closed."""
        return self._closed

    @property
    def size(self) -> int:
        """Get current buffer size."""
        return self._size


async def buffered_stream(
    stream: AsyncIterator[str],
    buffer_size: int = 1024,
) -> AsyncIterator[str]:
    """Buffer a stream to reduce callback frequency.

    Args:
        stream: Source stream
        buffer_size: Characters to buffer before yielding

    Yields:
        Buffered text chunks
    """
    buffer = ""

    async for chunk in stream:
        buffer += chunk

        if len(buffer) >= buffer_size:
            yield buffer
            buffer = ""

    if buffer:
        yield buffer
