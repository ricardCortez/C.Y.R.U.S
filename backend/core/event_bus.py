"""
C.Y.R.U.S — Async Event Bus.

Lightweight publish/subscribe dispatcher built on asyncio queues.
Modules publish events; the WebSocket server and other listeners subscribe.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict, List

from backend.utils.logger import get_logger

logger = get_logger("cyrus.event_bus")


class EventBus:
    """Simple async pub/sub event bus.

    Events are identified by string names.  Subscribers receive a copy of the
    payload dict posted by the publisher.

    Usage::

        bus = EventBus()

        @bus.on("transcript")
        async def handle(payload):
            print(payload["text"])

        await bus.emit("transcript", {"text": "Hola C.Y.R.U.S"})
    """

    def __init__(self) -> None:
        self._listeners: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[str, Dict[str, Any]]] = asyncio.Queue()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on(self, event: str) -> Callable:
        """Decorator — register *handler* as a listener for *event*.

        Args:
            event: Event name string (e.g. ``"transcript"``, ``"response"``).

        Returns:
            The original function, unchanged.
        """
        def decorator(handler: Callable) -> Callable:
            self._listeners[event].append(handler)
            return handler
        return decorator

    def subscribe(self, event: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Register *handler* for *event* (non-decorator form).

        Args:
            event: Event name.
            handler: Async or sync callable receiving one ``dict`` argument.
        """
        self._listeners[event].append(handler)
        logger.debug(f"[C.Y.R.U.S] EventBus: subscribed {handler.__name__!r} to '{event}'")

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def emit(self, event: str, payload: Dict[str, Any] | None = None) -> None:
        """Dispatch *event* to all registered listeners.

        Args:
            event: Event name.
            payload: Arbitrary data dict; defaults to ``{}``.
        """
        data = payload or {}
        handlers = self._listeners.get(event, [])
        if not handlers:
            logger.debug(f"[C.Y.R.U.S] EventBus: no listeners for '{event}'")
            return

        for handler in handlers:
            try:
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error(f"[C.Y.R.U.S] EventBus: handler {handler.__name__!r} raised {exc}")


# Module-level singleton — import and use directly.
bus = EventBus()
