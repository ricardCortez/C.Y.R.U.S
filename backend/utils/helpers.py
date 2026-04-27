"""JARVIS — Miscellaneous utility helpers."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def current_time_str() -> str:
    """Return the current local time as a human-readable string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_time_friendly() -> str:
    """Return e.g. ``'14:35 on Saturday, 11 April 2026'``."""
    return datetime.now().strftime("%-H:%M on %A, %-d %B %Y")


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries an async function with exponential back-off.

    Args:
        max_attempts: Total number of tries (including the first).
        base_delay: Initial wait in seconds; doubles on each retry.
        exceptions: Only retry on these exception types.

    Returns:
        Decorated async function.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        await asyncio.sleep(delay)
                        delay *= 2
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator  # type: ignore[return-value]


def timeit(label: str = "") -> Callable[[F], F]:
    """Simple sync decorator that prints elapsed ms to stdout."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            tag = label or func.__name__
            print(f"[JARVIS] {tag} took {elapsed:.1f} ms")
            return result
        return wrapper  # type: ignore[return-value]
    return decorator  # type: ignore[return-value]
