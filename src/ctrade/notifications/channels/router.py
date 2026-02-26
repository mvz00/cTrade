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

    def ensure_email_channel(self) -> None:
        """Auto-register the email channel from config if enabled but missing.

        Handles edge cases where the channel wasn't registered at startup
        (e.g. config loaded from DB after step 6, hot-reload failed, etc.).
        """
        if any(ch.name == "email" for ch in self._channels):
            return
        try:
            from ctrade.core.config_store import RuntimeConfigStore

            if not RuntimeConfigStore.is_initialized():
                return
            store = RuntimeConfigStore.get()
            email_cfg = store.get_email()
            api_key = store.get_email_api_key_decrypted()
            if email_cfg.get("enabled") and api_key and email_cfg.get("to_address"):
                from ctrade.notifications.channels.email import EmailChannel

                ch = EmailChannel(
                    api_key=api_key,
                    from_address=email_cfg.get("from_address", ""),
                    to_address=email_cfg["to_address"],
                    notify_on_buy=email_cfg.get("notify_on_buy", True),
                    notify_on_sell=email_cfg.get("notify_on_sell", True),
                )
                self.register(ch)
                logger.info("Auto-registered email channel from config")
        except Exception:
            logger.debug("Could not auto-register email channel", exc_info=True)

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
