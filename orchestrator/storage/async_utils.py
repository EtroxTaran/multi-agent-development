"""Async/sync bridge utilities for storage adapters.

Provides utilities for calling async repository methods from synchronous code,
which is common in the orchestrator where callers may be sync but SurrealDB
repositories are async.

Usage:
    from orchestrator.storage.async_utils import run_async

    # In sync code:
    result = run_async(async_repo.create_entry(...))
"""

import asyncio
import atexit
import concurrent.futures
import functools
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Module-level ThreadPoolExecutor singleton for async-to-sync bridge
# Reused across calls to avoid creating new threads per invocation
_thread_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
_thread_pool_lock = threading.Lock()


def _get_thread_pool() -> concurrent.futures.ThreadPoolExecutor:
    """Get or create the module-level ThreadPoolExecutor.

    Thread-safe lazy initialization of the executor pool.

    Returns:
        The shared ThreadPoolExecutor instance
    """
    global _thread_pool
    if _thread_pool is None:
        with _thread_pool_lock:
            # Double-check after acquiring lock
            if _thread_pool is None:
                _thread_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="async_bridge_"
                )
                logger.debug("Created async bridge ThreadPoolExecutor with 4 workers")
    return _thread_pool


def _shutdown_thread_pool() -> None:
    """Shutdown the thread pool on interpreter exit."""
    global _thread_pool
    if _thread_pool is not None:
        _thread_pool.shutdown(wait=False)
        _thread_pool = None


# Register cleanup on interpreter exit
atexit.register(_shutdown_thread_pool)


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from synchronous code.

    Handles the complexity of:
    - Detecting if we're already in an event loop
    - Creating a new event loop if needed
    - Proper cleanup of resources

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine

    Raises:
        RuntimeError: If called from within an async context incorrectly

    Examples:
        # Simple usage
        result = run_async(repo.get_state())

        # With arguments
        result = run_async(repo.create_entry(agent="claude", task_id="T1", prompt="..."))
    """
    try:
        # Check if we're already in an async context
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create a new one
        loop = None

    if loop is not None:
        # We're in an async context - this is trickier
        # We can't just run the coroutine directly as it would block
        # Instead, we need to run it in a thread with its own loop
        # Use the shared thread pool to avoid creating new threads per call

        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()

        executor = _get_thread_pool()
        future = executor.submit(run_in_thread)
        return future.result()
    else:
        # No running loop, we can use asyncio.run()
        return asyncio.run(coro)


def sync_wrapper(async_func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., T]:
    """Decorator to create a sync wrapper for an async function.

    Useful for creating sync versions of async repository methods.

    Args:
        async_func: The async function to wrap

    Returns:
        A synchronous function that runs the async function

    Example:
        class MyRepo:
            async def get_data_async(self) -> Data:
                ...

            get_data = sync_wrapper(get_data_async)
    """

    @functools.wraps(async_func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return run_async(async_func(*args, **kwargs))

    return wrapper


class AsyncContextAdapter:
    """Adapter to use async context managers in sync code.

    Wraps an async context manager to work in synchronous code.

    Usage:
        # Async context manager
        async with repo.record(...) as entry:
            ...

        # Sync equivalent using adapter
        with AsyncContextAdapter(repo.record(...)) as entry:
            ...
    """

    def __init__(self, async_cm: Any):
        """Initialize with an async context manager.

        Args:
            async_cm: The async context manager to wrap
        """
        self._async_cm = async_cm
        self._result = None

    def __enter__(self) -> Any:
        """Enter the context manager synchronously."""
        self._result = run_async(self._async_cm.__aenter__())
        return self._result

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Exit the context manager synchronously."""
        return run_async(self._async_cm.__aexit__(exc_type, exc_val, exc_tb))


def ensure_async(func_or_coro: Any) -> Coroutine:
    """Ensure something is a coroutine.

    If given a coroutine, returns it unchanged.
    If given a sync function, wraps it in a coroutine.

    Args:
        func_or_coro: A coroutine or sync value

    Returns:
        A coroutine

    Example:
        # These both work:
        result = await ensure_async(sync_result)
        result = await ensure_async(async_function())
    """
    if asyncio.iscoroutine(func_or_coro):
        return func_or_coro

    async def wrapper() -> Any:
        return func_or_coro

    return wrapper()


async def gather_with_fallback(*coros: Coroutine, return_exceptions: bool = True) -> list:
    """Gather coroutines with graceful error handling.

    Similar to asyncio.gather but with better defaults for storage operations.

    Args:
        *coros: Coroutines to gather
        return_exceptions: If True, exceptions are returned as results

    Returns:
        List of results (or exceptions if return_exceptions=True)
    """
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)
