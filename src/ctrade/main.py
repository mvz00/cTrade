"""Application orchestrator — starts all services in correct order."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ctrade.core.events import EventBus
from ctrade.db.engine import close_db, init_db
from ctrade.settings import AppSettings, get_settings
from ctrade.utils.logging import setup_logging

logger = logging.getLogger(__name__)

# Module-level references so the lifespan can share state with the app
_event_bus: EventBus | None = None
_db_available: bool = False


def get_event_bus() -> EventBus | None:
    """Get the global event bus instance."""
    return _event_bus


def is_db_available() -> bool:
    """Check if the database was successfully initialized."""
    return _db_available


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup and shutdown logic."""
    global _event_bus, _db_available
    settings = get_settings()

    logger.info("Starting cTrade v0.1.0...")
    logger.info("Trading mode: %s", settings.trading.mode)

    # Initialize database (non-fatal if unavailable)
    try:
        init_db(
            database_url=settings.db.url,
            pool_size=settings.db.pool_size,
            echo=settings.db.echo_sql,
        )
        _db_available = True
        logger.info("Database engine initialized")
    except Exception as e:
        _db_available = False
        logger.warning(
            "Database unavailable — running without DB. "
            "Start PostgreSQL with: docker-compose up -d  |  Error: %s",
            e,
        )

    # Start event bus
    _event_bus = EventBus()
    await _event_bus.start()
    logger.info("Event bus started")

    logger.info("cTrade startup complete — visit http://%s:%d", settings.api_host, settings.api_port)

    yield  # App is running

    # --- Shutdown ---
    logger.info("Shutting down cTrade...")

    if _event_bus:
        await _event_bus.stop()

    if _db_available:
        await close_db()

    _event_bus = None
    _db_available = False
    logger.info("cTrade shutdown complete")


def create_configured_app() -> FastAPI:
    """Create the FastAPI app with lifespan wired in."""
    from ctrade.api.app import create_app

    app = create_app(lifespan=lifespan)
    return app


def _check_port_available(host: str, port: int) -> bool:
    """Check if a port is available before attempting to bind."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def main() -> None:
    """Entry point for the application."""
    settings = get_settings()

    setup_logging(
        log_level=settings.log_level,
        json_output=not settings.debug,
    )

    host = settings.api_host
    port = settings.api_port

    if not _check_port_available(host, port):
        print(
            f"\n  ERROR: Port {port} is already in use.\n"
            f"\n"
            f"  Another cTrade instance (or another app) is already running on {host}:{port}.\n"
            f"\n"
            f"  To fix this, either:\n"
            f"    1. Stop the other process:  taskkill /F /PID <pid>\n"
            f"       (find the PID with:  netstat -ano | findstr :{port})\n"
            f"    2. Use a different port:  set CTRADE_API_PORT=8001\n"
        )
        raise SystemExit(1)

    app = create_configured_app()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
