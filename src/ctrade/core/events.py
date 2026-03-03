"""In-process async event bus for component communication.

Components publish events (e.g., new candle data, signal generated, order filled)
and subscribers react to them. This decouples producers from consumers.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Coroutine

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class Event:
    """Base event with metadata."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Simple in-process async event bus using asyncio.

    Supports publish/subscribe pattern with multiple handlers per event type.
    Handlers are called concurrently for each event.

    Use ``get_instance()`` / ``reset()`` for singleton access (same pattern as
    every other manager in the codebase).
    """

    _instance: ClassVar[EventBus | None] = None
    _singleton_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_instance(cls) -> EventBus:
        """Return the singleton EventBus, creating it on first call."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (mainly for tests)."""
        with cls._singleton_lock:
            cls._instance = None

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler %s to event '%s'", handler.__name__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed handler %s from event '%s'", handler.__name__, event_type)

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus. Non-blocking."""
        await self._queue.put(event)

    def publish_nowait(self, event: Event) -> None:
        """Publish an event without waiting. Use from sync contexts."""
        self._queue.put_nowait(event)

    async def start(self) -> None:
        """Start processing events from the queue."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop processing events and drain the queue."""
        self._running = False
        if self._task:
            # Put a sentinel to unblock the queue.get()
            await self._queue.put(Event(event_type="__shutdown__"))
            await self._task
            self._task = None
        logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                event = await self._queue.get()
                if event.event_type == "__shutdown__":
                    break

                handlers = self._handlers.get(event.event_type, [])
                if not handlers:
                    self._queue.task_done()
                    continue

                # Run all handlers concurrently
                tasks = [self._safe_call(handler, event) for handler in handlers]
                await asyncio.gather(*tasks)
                self._queue.task_done()
            except Exception:
                logger.exception("Error in event processing loop")

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call a handler with error isolation."""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Error in event handler %s for event '%s'",
                handler.__name__,
                event.event_type,
            )


# Well-known event types
class EventTypes:
    """Constants for event type strings."""

    # Market data
    CANDLE_UPDATE = "candle.update"
    TICKER_UPDATE = "ticker.update"

    # Signals
    SIGNAL_GENERATED = "signal.generated"

    # Orders & positions
    ORDER_CREATED = "order.created"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"

    # Risk
    STOP_LOSS_HIT = "risk.stop_loss_hit"
    TAKE_PROFIT_HIT = "risk.take_profit_hit"
    CIRCUIT_BREAKER_TRIGGERED = "risk.circuit_breaker"

    # Feeds
    FEED_STARTED = "feed.started"
    FEED_STOPPED = "feed.stopped"
    FEED_ERROR = "feed.error"

    # Sentiment
    SENTIMENT_UPDATE = "sentiment.update"

    # On-chain
    ONCHAIN_UPDATE = "onchain.update"

    # Alerts
    ALERT_TRIGGERED = "alert.triggered"

    # Logging
    LOG_ENTRY = "log.entry"

    # System
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
