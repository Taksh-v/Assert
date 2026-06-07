import asyncio
from functools import wraps
from typing import Callable, Any


def run_blocking(func: Callable[..., Any], *args, **kwargs) -> Any:
    """Run a blocking function in a threadpool from async code.

    Usage:
        result = await run_blocking(some_sync_fn, arg1, kw=val)
    """
    return asyncio.to_thread(func, *args, **kwargs)


def sync_to_async(func: Callable[..., Any]):
    """Decorator to turn a sync function into an async wrapper using threadpool."""

    @wraps(func)
    async def _wrapped(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    return _wrapped
