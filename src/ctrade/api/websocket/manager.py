"""WebSocket connection manager — tracks connected clients and subscriptions."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, ClassVar

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Singleton that manages active WebSocket connections.

    Each connection can optionally subscribe to specific event types.
    An empty subscription set means "receive everything".
    """

    _instance: ClassVar[ConnectionManager | None] = None
    _singleton_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_instance(cls) -> ConnectionManager:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._singleton_lock:
            cls._instance = None

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}
        self._lock = threading.Lock()

    def connect(self, ws: WebSocket, subscriptions: set[str] | None = None) -> None:
        """Register a new WebSocket connection."""
        with self._lock:
            self._connections[ws] = subscriptions or set()
        logger.debug("WS connected (total: %d)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection."""
        with self._lock:
            self._connections.pop(ws, None)
        logger.debug("WS disconnected (total: %d)", len(self._connections))

    def update_subscriptions(self, ws: WebSocket, subscriptions: set[str]) -> None:
        """Update the subscription filter for a connection."""
        with self._lock:
            if ws in self._connections:
                self._connections[ws] = subscriptions

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast a message to all subscribed connections.

        Connections with an empty subscription set receive everything.
        Dead connections are cleaned up automatically.
        """
        message = json.dumps({"type": event_type, "data": data})
        dead: list[WebSocket] = []

        # Copy the connections dict to avoid holding lock during async I/O
        with self._lock:
            connections = dict(self._connections)

        for ws, subs in connections.items():
            # Filter: send if client subscribed to this type, or has empty set (= all)
            if subs and event_type not in subs:
                continue

            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            with self._lock:
                for ws in dead:
                    self._connections.pop(ws, None)
            logger.debug("Cleaned up %d dead WS connections", len(dead))
