"""Application orchestrator — starts all services in correct order."""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ctrade.core.config_store import RuntimeConfigStore
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

    # Use print() alongside logger for Railway deploy logs visibility
    print("[cTrade] Starting cTrade v0.1.0...", flush=True)
    logger.info("Starting cTrade v0.1.0...")

    # Initialize runtime config store (must happen before any API calls)
    RuntimeConfigStore.initialize(settings)
    logger.info("Runtime config store initialized")
    logger.info("Trading mode: %s", settings.trading.mode)

    # Initialize database (non-fatal if unavailable)
    # Use a strict timeout so an unreachable DB never blocks startup.
    try:
        from ctrade.db.engine import ping_db

        print("[cTrade] Initializing database engine...", flush=True)
        init_db(
            database_url=settings.db.url,
            pool_size=settings.db.pool_size,
            echo=settings.db.echo_sql,
        )
        # Engine created, but verify actual connectivity before proceeding.
        # ping_db() already has an internal asyncio.wait_for timeout (10s),
        # but we add an outer guard just in case.
        print("[cTrade] Pinging database (10s timeout)...", flush=True)
        try:
            db_ok = await asyncio.wait_for(ping_db(timeout=10), timeout=15)
        except asyncio.TimeoutError:
            db_ok = False

        if db_ok:
            _db_available = True
            print("[cTrade] Database connected and ready", flush=True)
            logger.info("Database connected and ready")
        else:
            _db_available = False
            await close_db()
            print("[cTrade] Database unreachable — running in memory-only mode", flush=True)
            logger.warning(
                "Database unreachable — running in memory-only mode. "
                "Start PostgreSQL with: docker-compose up -d"
            )
    except Exception as e:
        _db_available = False
        print(f"[cTrade] Database unavailable: {e}", flush=True)
        logger.warning(
            "Database unavailable — running without DB. "
            "Start PostgreSQL with: docker-compose up -d  |  Error: %s",
            e,
        )

    # Hydrate singletons from DB (non-fatal if anything goes wrong)
    if _db_available:
        try:
            from ctrade.exchange.live_engine import LiveEngine
            from ctrade.exchange.paper_engine import PaperEngine
            from ctrade.notifications.alert_manager import AlertManager
            from ctrade.strategy.orchestrator import TradingOrchestrator
            from ctrade.strategy.signal_manager import SignalManager

            await PaperEngine.get_instance().hydrate_from_db()
            await LiveEngine.get_instance().hydrate_from_db()
            await SignalManager.get_instance().hydrate_from_db()
            await AlertManager.get_instance().hydrate_from_db()
            await TradingOrchestrator.get_instance().hydrate_from_db()
            logger.info("All singletons hydrated from database")
        except Exception as e:
            logger.warning("Singleton hydration failed (non-fatal): %s", e)

    # Start event bus (singleton — accessible via EventBus.get_instance())
    _event_bus = EventBus.get_instance()
    await _event_bus.start()
    app.state.event_bus = _event_bus
    logger.info("Event bus started")

    # Wire WebSocket event forwarder
    from ctrade.api.websocket import register_event_forwarder
    register_event_forwarder(_event_bus)

    print("[cTrade] Core services ready — starting server...", flush=True)

    # Start data feeds in background (skipped when CTRADE_FEEDS_ENABLED=false)
    feed_task: asyncio.Task[None] | None = None
    if settings.feeds_enabled:
        from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
        from ctrade.feeds.cvd import CVDFeed
        from ctrade.feeds.derivatives import DerivativesFeed
        from ctrade.feeds.market_sentiment import MarketSentimentFeed
        from ctrade.feeds.onchain import OnChainFeed
        from ctrade.feeds.sentiment import SentimentFeed
        from ctrade.feeds.social_velocity import SocialVelocityFeed

        async def _start_feeds() -> None:
            """Start all data feeds sequentially in background."""
            feeds = [
                CoinMarketCapFeed.get_instance(),
                SentimentFeed.get_instance(),
                OnChainFeed.get_instance(),
                DerivativesFeed.get_instance(),
                MarketSentimentFeed.get_instance(),
                CVDFeed.get_instance(),
                SocialVelocityFeed.get_instance(),
            ]
            for feed in feeds:
                try:
                    await feed.start()
                except Exception as e:
                    logger.warning("Feed %s failed to start (non-fatal): %s", feed.name, e)
            logger.info("All data feeds started")

        feed_task = asyncio.create_task(_start_feeds())
    else:
        print("[cTrade] Data feeds disabled (CTRADE_FEEDS_ENABLED=false)", flush=True)
        logger.info("Data feeds disabled via CTRADE_FEEDS_ENABLED=false")

    # Register notification channels (optional — only when env vars are set)
    from ctrade.notifications.channels.router import NotificationRouter
    notification_router = NotificationRouter.get_instance()

    if settings.discord.enabled and settings.discord.webhook_url.get_secret_value():
        from ctrade.notifications.channels.discord import DiscordChannel
        notification_router.register(
            DiscordChannel(settings.discord.webhook_url.get_secret_value())
        )

    if settings.telegram.enabled and settings.telegram.bot_token.get_secret_value():
        from ctrade.notifications.channels.telegram import TelegramChannel
        notification_router.register(
            TelegramChannel(
                settings.telegram.bot_token.get_secret_value(),
                settings.telegram.chat_id,
            )
        )

    if notification_router.list_channels():
        logger.info("Notification channels active: %s", ", ".join(notification_router.list_channels()))

    print(f"[cTrade] Startup complete — listening on {settings.api_host}:{settings.api_port}", flush=True)
    logger.info("cTrade startup complete — visit http://%s:%d", settings.api_host, settings.api_port)

    yield  # App is running

    # --- Shutdown ---
    logger.info("Shutting down cTrade...")

    # Cancel feed startup if still running, then stop all feeds
    if feed_task is not None:
        if not feed_task.done():
            feed_task.cancel()
            try:
                await feed_task
            except asyncio.CancelledError:
                pass

        from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
        from ctrade.feeds.cvd import CVDFeed
        from ctrade.feeds.derivatives import DerivativesFeed
        from ctrade.feeds.market_sentiment import MarketSentimentFeed
        from ctrade.feeds.onchain import OnChainFeed
        from ctrade.feeds.sentiment import SentimentFeed
        from ctrade.feeds.social_velocity import SocialVelocityFeed

        await SocialVelocityFeed.get_instance().stop()
        await CVDFeed.get_instance().stop()
        await MarketSentimentFeed.get_instance().stop()
        await DerivativesFeed.get_instance().stop()
        await OnChainFeed.get_instance().stop()
        await SentimentFeed.get_instance().stop()
        await CoinMarketCapFeed.get_instance().stop()

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
    # Ensure stdout is unbuffered so Railway sees logs immediately
    print("[cTrade] Process starting...", flush=True)

    try:
        settings = get_settings()
    except Exception as e:
        print(f"[cTrade] FATAL: Failed to load settings: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    setup_logging(
        log_level=settings.log_level,
        json_output=not settings.debug,
    )

    host = settings.api_host
    port = settings.api_port

    print(f"[cTrade] Configured: host={host}, port={port}", flush=True)

    # Skip port check in container environments (Railway sets PORT env var;
    # the check can false-positive in some container runtimes).
    import os

    if not os.environ.get("PORT"):
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

    try:
        app = create_configured_app()
    except Exception as e:
        print(f"[cTrade] FATAL: Failed to create app: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    print(f"[cTrade] Starting uvicorn on {host}:{port}...", flush=True)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
