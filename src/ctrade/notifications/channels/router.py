"""Notification router — dispatches to all active channels."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, ClassVar, Protocol

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """Protocol all notification channels must implement."""

    name: str

    async def send(
        self,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> bool: ...


class NotificationRouter:
    """Singleton that manages active notification channels and dispatches
    messages to all of them concurrently.
    """

    _instance: ClassVar[NotificationRouter | None] = None
    _singleton_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_instance(cls) -> NotificationRouter:
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
        self._channels: list[NotificationChannel] = []

    def register(self, channel: NotificationChannel) -> None:
        """Register a new notification channel."""
        # Replace existing channel with the same name (hot-reload support)
        self._channels = [ch for ch in self._channels if ch.name != channel.name]
        self._channels.append(channel)
        logger.info("Registered notification channel: %s", channel.name)

    def unregister(self, name: str) -> None:
        """Remove a notification channel by name."""
        before = len(self._channels)
        self._channels = [ch for ch in self._channels if ch.name != name]
        if len(self._channels) < before:
            logger.info("Unregistered notification channel: %s", name)

    def list_channels(self) -> list[str]:
        """Return names of all registered channels."""
        return [ch.name for ch in self._channels]

    async def dispatch(
        self,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Send a notification to all registered channels concurrently.

        Returns a mapping of channel_name → success/failure.
        """
        if not self._channels:
            return {}

        results: dict[str, bool] = {}

        async def _send(ch: NotificationChannel) -> tuple[str, bool]:
            try:
                ok = await ch.send(message, severity, metadata)
                return ch.name, ok
            except Exception:
                logger.warning("Channel %s failed", ch.name, exc_info=True)
                return ch.name, False

        tasks = [_send(ch) for ch in self._channels]
        for name, success in await asyncio.gather(*tasks):
            results[name] = success

        return results
