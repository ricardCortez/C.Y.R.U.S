"""
C.Y.R.U.S — WebSocket Server.

Broadcasts real-time events (transcript, response, status) to connected
React frontend clients.  Receives no commands from the frontend in Phase 1
(voice control is the sole input).
"""

from __future__ import annotations

import asyncio
import json
from typing import Set

import websockets
from websockets.asyncio.server import ServerConnection

from backend.core.event_bus import EventBus
from backend.utils.logger import get_logger

logger = get_logger("cyrus.api.websocket")

# Event names that the server forwards to frontend clients
_BROADCAST_EVENTS = {"transcript", "response", "status", "error", "metrics", "debug", "wake_words", "enrollment", "system_stats"}


class WebSocketServer:
    """Async WebSocket server that broadcasts C.Y.R.U.S events.

    Args:
        event_bus: Shared :class:`EventBus` instance.
        host: Bind address (default ``"localhost"``).
        port: Bind port (default ``8765``).
        ping_interval: WebSocket keepalive ping interval in seconds.
        ping_timeout: Time to wait for pong before disconnecting.
    """

    def __init__(
        self,
        event_bus: EventBus,
        host: str = "localhost",
        port: int = 8765,
        ping_interval: int = 20,
        ping_timeout: int = 10,
    ) -> None:
        self._bus = event_bus
        self._host = host
        self._port = port
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._clients: Set[ServerConnection] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket server and subscribe to the event bus."""
        # Subscribe to all broadcast events
        for event in _BROADCAST_EVENTS:
            self._bus.subscribe(event, self._make_handler(event))

        logger.info(f"[C.Y.R.U.S] WebSocket: server starting on ws://{self._host}:{self._port}")
        async with websockets.serve(
            self._handle_client,
            self._host,
            self._port,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        ):
            await asyncio.Future()  # Run forever

    # ------------------------------------------------------------------
    # Client handler
    # ------------------------------------------------------------------

    async def _handle_client(self, ws: ServerConnection) -> None:
        """Called for each new frontend connection."""
        self._clients.add(ws)
        addr = ws.remote_address
        logger.info(f"[C.Y.R.U.S] WebSocket: client connected from {addr} ({len(self._clients)} total)")

        # Send a welcome status immediately
        await self._send(ws, "status", {"state": "connected", "message": "C.Y.R.U.S online"})

        # Notify the engine that a client connected (triggers greeting)
        await self._bus.emit("client_connected", {})

        try:
            async for raw_message in ws:
                try:
                    msg = json.loads(raw_message)
                    logger.debug(f"[C.Y.R.U.S] WebSocket: received from client: {msg}")
                    # Route frontend commands to the engine via the event bus
                    if isinstance(msg, dict) and msg.get("type") == "command":
                        await self._bus.emit("frontend_command", msg)
                except json.JSONDecodeError:
                    pass
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            logger.info(f"[C.Y.R.U.S] WebSocket: client disconnected ({len(self._clients)} remaining)")

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, event: str, payload: dict) -> None:
        """Send *payload* to all connected clients.

        Args:
            event: Event name string.
            payload: Arbitrary data dict.
        """
        if not self._clients:
            return
        message = json.dumps({"event": event, "data": payload})
        disconnected: Set[ServerConnection] = set()
        for ws in list(self._clients):
            try:
                await ws.send(message)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
        self._clients -= disconnected

    async def _send(self, ws: ServerConnection, event: str, payload: dict) -> None:
        """Send a message to a single client."""
        try:
            await ws.send(json.dumps({"event": event, "data": payload}))
        except websockets.ConnectionClosed:
            self._clients.discard(ws)

    # ------------------------------------------------------------------
    # Event bus integration
    # ------------------------------------------------------------------

    def _make_handler(self, event: str):
        """Return a coroutine that broadcasts an event-bus payload."""
        async def handler(payload: dict) -> None:
            await self.broadcast(event, payload)
        handler.__name__ = f"broadcast_{event}"
        return handler
