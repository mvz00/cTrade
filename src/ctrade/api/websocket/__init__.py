"""WebSocket package — real-time event push to frontend."""

from ctrade.api.websocket.endpoint import register_event_forwarder, router
from ctrade.api.websocket.manager import ConnectionManager

__all__ = ["ConnectionManager", "register_event_forwarder", "router"]
