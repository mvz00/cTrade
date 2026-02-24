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
    """FastAPI lifespan: startup and shutdown logic.

    CRITICAL: This function MUST always reach ``yield`` so the server
    accepts connections and Railway's healthcheck can succeed.  Every
    startup step is wrapped in its own try/except to ensure that a
    failure in one step never prevents the server from starting.
    """
    global _event_bus, _db_available
    settings = get_settings()
    feed_task: asyncio.Task[None] | None = None

    print(f"[cTrade] Starting cTrade v0.1.0 on port {settings.api_port}...", flush=True)

    # --- Step 1: Config store ---
    try:
        RuntimeConfigStore.initialize(settings)
        print("[cTrade] [1/6] Config store initialized", flush=True)
    except Exception as e:
        print(f"[cTrade] [1/6] Config store FAILED (non-fatal): {e}", flush=True)

    # --- Step 2: Database ---
    try:
        from ctrade.db.engine import ping_db

        print("[cTrade] [2/6] Initializing database...", flush=True)
        init_db(
            database_url=settings.db.url,
            pool_size=settings.db.pool_size,
            echo=settings.db.echo_sql,
        )
        try:
            db_ok = await asyncio.wait_for(ping_db(timeout=10), timeout=15)
        except asyncio.TimeoutError:
            db_ok = False

        if db_ok:
            _db_available = True
            # Ensure all ORM tables exist (CREATE TABLE IF NOT EXISTS)
            from ctrade.db.engine import ensure_tables
            await ensure_tables()
            print("[cTrade] [2/6] Database connected + tables verified", flush=True)
        else:
            _db_available = False
            await close_db()
            print("[cTrade] [2/6] Database unreachable — memory-only mode", flush=True)
    except Exception as e:
        _db_available = False
        print(f"[cTrade] [2/6] Database FAILED (non-fatal): {e}", flush=True)

    # --- Step 2b: Hydrate singletons from DB ---
    if _db_available:
        try:
            from ctrade.exchange.live_engine import LiveEngine
            from ctrade.exchange.paper_engine import PaperEngine
            from ctrade.notifications.alert_manager import AlertManager
            from ctrade.strategy.orchestrator import TradingOrchestrator
            from ctrade.strategy.signal_manager import SignalManager

            # Config store first — exchanges & settings must be available
            # before engines try to use them
            await RuntimeConfigStore.get().hydrate_from_db()
            await PaperEngine.get_instance().hydrate_from_db()
            await LiveEngine.get_instance().hydrate_from_db()
            await SignalManager.get_instance().hydrate_from_db()
            await AlertManager.get_instance().hydrate_from_db()
            await TradingOrchestrator.get_instance().hydrate_from_db()
            print("[cTrade]        Singletons hydrated from DB", flush=True)
        except Exception as e:
            print(f"[cTrade]        Hydration FAILED (non-fatal): {e}", flush=True)

    # --- Step 3: Event bus ---
    try:
        _event_bus = EventBus.get_instance()
        await _event_bus.start()
        app.state.event_bus = _event_bus
        print("[cTrade] [3/6] Event bus started", flush=True)
    except Exception as e:
        print(f"[cTrade] [3/6] Event bus FAILED (non-fatal): {e}", flush=True)

    # --- Step 4: WebSocket forwarder ---
    try:
        from ctrade.api.websocket import register_event_forwarder
        if _event_bus:
            register_event_forwarder(_event_bus)
        print("[cTrade] [4/6] WebSocket forwarder ready", flush=True)
    except Exception as e:
        print(f"[cTrade] [4/6] WebSocket forwarder FAILED (non-fatal): {e}", flush=True)

    # --- Step 5: Data feeds ---
    try:
        if settings.feeds_enabled:
            from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
            from ctrade.feeds.cvd import CVDFeed
            from ctrade.feeds.derivatives import DerivativesFeed
            from ctrade.feeds.market_sentiment import MarketSentimentFeed
            from ctrade.feeds.onchain import OnChainFeed
            from ctrade.feeds.sentiment import SentimentFeed
            from ctrade.feeds.social_velocity import SocialVelocityFeed

            async def _start_feeds() -> None:
                """Start all data feeds with staggered delays."""
                feeds = [
                    CoinMarketCapFeed.get_instance(),
                    SentimentFeed.get_instance(),
                    OnChainFeed.get_instance(),
                    DerivativesFeed.get_instance(),
                    MarketSentimentFeed.get_instance(),
                    CVDFeed.get_instance(),
                    SocialVelocityFeed.get_instance(),
                ]
                for i, feed in enumerate(feeds):
                    try:
                        await feed.start()
                    except Exception as e:
                        logger.warning("Feed %s failed to start: %s", feed.name, e)
                    if i < len(feeds) - 1:
                        await asyncio.sleep(5)
                logger.info("All data feeds started")

            feed_task = asyncio.create_task(_start_feeds())
            print("[cTrade] [5/6] Feeds starting (background task)", flush=True)
        else:
            print("[cTrade] [5/6] Feeds disabled (CTRADE_FEEDS_ENABLED=false)", flush=True)
    except Exception as e:
        print(f"[cTrade] [5/6] Feeds FAILED (non-fatal): {e}", flush=True)

    # --- Step 6: Notification channels ---
    try:
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

        channels = notification_router.list_channels()
        if channels:
            print(f"[cTrade] [6/6] Notifications: {', '.join(channels)}", flush=True)
        else:
            print("[cTrade] [6/6] No notification channels configured", flush=True)
    except Exception as e:
        print(f"[cTrade] [6/6] Notifications FAILED (non-fatal): {e}", flush=True)

    # === Auth diagnostics ===
    if settings.auth.enabled:
        if settings.auth.password_hash:
            print("[cTrade] [auth] Auth ENABLED — password_hash configured", flush=True)
        else:
            print(
                "[cTrade] [auth] WARNING: Auth ENABLED but password_hash is EMPTY! "
                "Login will be rejected. Check env var: CTRADE_AUTH__PASSWORD_HASH "
                "(double underscore between AUTH and PASSWORD_HASH)",
                flush=True,
            )
    else:
        print("[cTrade] [auth] Auth DISABLED — all logins accepted", flush=True)

    # === SERVER READY — this yield MUST always be reached ===
    print(f"[cTrade] === SERVER READY on 0.0.0.0:{settings.api_port} ===", flush=True)

    yield  # App is running — healthcheck can now respond

    # --- Shutdown (also crash-proof) ---
    print("[cTrade] Shutting down...", flush=True)
    try:
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
    except Exception as e:
        print(f"[cTrade] Feed shutdown error: {e}", flush=True)

    try:
        if _event_bus:
            await _event_bus.stop()
    except Exception as e:
        print(f"[cTrade] Event bus shutdown error: {e}", flush=True)

    try:
        if _db_available:
            await close_db()
    except Exception as e:
        print(f"[cTrade] DB shutdown error: {e}", flush=True)

    _event_bus = None
    _db_available = False
    print("[cTrade] Shutdown complete", flush=True)


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
