"""Structured logging setup using structlog."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any

import structlog


class WebSocketLogHandler(logging.Handler):
    """Logging handler that publishes log records to the EventBus.

    Records are forwarded as ``log.entry`` events and reach WebSocket
    clients via the existing EventBus → WebSocket pipeline.

    Uses ``loop.call_soon_threadsafe`` so that log records emitted from
    *any* thread (background workers, threadpool, etc.) are safely
    enqueued on the asyncio event loop.

    A thread-local guard prevents infinite recursion when the EventBus
    or WebSocket code itself emits log messages.
    """

    _local = threading.local()
    _loop: asyncio.AbstractEventLoop | None = None

    def emit(self, record: logging.LogRecord) -> None:
        # Guard against recursion
        if getattr(self._local, "emitting", False):
            return
        self._local.emitting = True
        try:
            from ctrade.core.events import Event, EventBus, EventTypes

            bus = EventBus._instance  # noqa: SLF001 — avoid get_instance() to skip init
            if bus is None or not bus._running:  # noqa: SLF001
                return

            data: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "func": record.funcName,
                "lineno": record.lineno,
            }

            event = Event(event_type=EventTypes.LOG_ENTRY, data=data)

            # Lazily capture the running event loop reference
            if self._loop is None or self._loop.is_closed():
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

            if self._loop is not None and self._loop.is_running():
                # Thread-safe: works from event-loop thread AND worker threads
                self._loop.call_soon_threadsafe(bus.publish_nowait, event)
            else:
                # Fallback for edge cases (e.g., during shutdown)
                bus.publish_nowait(event)
        except Exception:
            pass  # Never let logging handler errors propagate
        finally:
            self._local.emitting = False


def setup_logging(
    log_level: str = "INFO",
    json_output: bool = False,
    enable_ws_handler: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output logs as JSON. If False, use human-readable console format.
        enable_ws_handler: If True, attach a handler that streams logs to WebSocket clients.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors for both structlog and stdlib logging
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Stream logs to WebSocket clients via EventBus
    if enable_ws_handler:
        ws_handler = WebSocketLogHandler()
        ws_handler.setLevel(level)
        root_logger.addHandler(ws_handler)

    # Quiet noisy libraries
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
