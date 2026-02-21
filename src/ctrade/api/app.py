"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ctrade.api.middleware import setup_middleware
from ctrade.api.routers import (
    alerts,
    backtest,
    config,
    dashboard,
    exchanges,
    health,
    screener,
    signals,
    trading,
)

logger = logging.getLogger(__name__)

# Path to the React build output
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Default lifespan that initializes the config store.

    Used when create_app() is called directly (e.g. uvicorn ctrade.api.app:create_app --factory)
    without going through main.py.
    """
    from ctrade.core.config_store import RuntimeConfigStore
    from ctrade.core.events import EventBus
    from ctrade.settings import get_settings

    settings = get_settings()

    # Only initialize if not already done (main.py may have already called this)
    if not RuntimeConfigStore.is_initialized():
        RuntimeConfigStore.initialize(settings)
        logger.info("Runtime config store initialized (default lifespan)")

    # Start event bus
    event_bus = EventBus()
    await event_bus.start()

    # Initialize database (non-fatal)
    db_available = False
    try:
        from ctrade.db.engine import close_db, init_db, ping_db
        init_db(
            database_url=settings.db.url,
            pool_size=settings.db.pool_size,
            echo=settings.db.echo_sql,
        )
        # Engine created, but verify actual connectivity before proceeding
        if await ping_db():
            db_available = True
            logger.info("Database connected and ready")
        else:
            await close_db()
            logger.warning(
                "Database unreachable — running in memory-only mode. "
                "Start PostgreSQL with: docker-compose up -d"
            )
    except Exception:
        logger.warning("Database unavailable in default lifespan (non-fatal)")

    # Hydrate singletons from DB
    if db_available:
        try:
            from ctrade.exchange.paper_engine import PaperEngine
            from ctrade.notifications.alert_manager import AlertManager
            from ctrade.strategy.orchestrator import TradingOrchestrator
            from ctrade.strategy.signal_manager import SignalManager

            await PaperEngine.get_instance().hydrate_from_db()
            await SignalManager.get_instance().hydrate_from_db()
            await AlertManager.get_instance().hydrate_from_db()
            await TradingOrchestrator.get_instance().hydrate_from_db()
            logger.info("All singletons hydrated from database")
        except Exception as e:
            logger.warning("Singleton hydration failed (non-fatal): %s", e)

    # Start CoinMarketCap feed (no-op if no API key configured)
    from ctrade.feeds.coinmarketcap import CoinMarketCapFeed

    cmc_feed = CoinMarketCapFeed.get_instance()
    await cmc_feed.start()

    logger.info("cTrade ready — visit http://%s:%d", settings.api_host, settings.api_port)

    yield

    await cmc_feed.stop()
    await event_bus.stop()
    if db_available:
        try:
            await close_db()
        except Exception:
            pass
    logger.info("cTrade shutdown complete")


def create_app(lifespan: Any = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        lifespan: Optional async context manager for startup/shutdown lifecycle.
                  If not provided, a default lifespan initializes core services.
    """
    app = FastAPI(
        title="cTrade",
        description="Comprehensive crypto trading application",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan or _default_lifespan,
    )

    # Middleware
    setup_middleware(app)

    # API routers (must be registered before the static catch-all)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")
    app.include_router(exchanges.router, prefix="/api/v1")
    app.include_router(trading.router, prefix="/api/v1")
    app.include_router(signals.router, prefix="/api/v1")
    app.include_router(backtest.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(screener.router, prefix="/api/v1")

    # Serve React SPA if the build exists, otherwise fall back to landing page
    if _FRONTEND_DIR.is_dir() and (_FRONTEND_DIR / "index.html").exists():
        # Serve static assets (JS, CSS, images) under /assets
        assets_dir = _FRONTEND_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # Serve other static files (favicon, etc.) at their exact paths
        @app.get("/favicon.svg")
        async def favicon() -> FileResponse:
            return FileResponse(str(_FRONTEND_DIR / "favicon.svg"))

        # SPA catch-all: serve index.html for all non-API routes
        @app.get("/{path:path}")
        async def spa_catch_all(request: Request, path: str) -> FileResponse:
            # If the exact file exists in dist, serve it
            file_path = _FRONTEND_DIR / path
            if path and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for client-side routing
            return FileResponse(str(_FRONTEND_DIR / "index.html"))
    else:
        # No React build available — show landing page
        @app.get("/", response_class=HTMLResponse)
        async def root() -> str:
            return _landing_page_html()

    return app


def _landing_page_html() -> str:
    """Fallback landing page when React build is not available."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>cTrade</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17; color: #e1e4e8; min-height: 100vh;
            display: flex; align-items: center; justify-content: center;
        }
        .container { text-align: center; padding: 40px 20px; }
        h1 {
            font-size: 3rem; font-weight: 700;
            background: linear-gradient(135deg, #00d4aa, #0099ff);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
        }
        p { color: #8b949e; font-size: 1.1rem; margin-bottom: 32px; }
        .hint {
            background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 24px; max-width: 480px; margin: 0 auto; text-align: left;
        }
        .hint h3 { color: #e1e4e8; margin-bottom: 12px; font-size: 1rem; }
        code {
            display: block; background: #0d1117; border: 1px solid #21262d;
            border-radius: 6px; padding: 12px; margin: 8px 0;
            font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85rem;
            color: #00d4aa;
        }
        a { color: #0099ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>cTrade</h1>
        <p>Comprehensive Crypto Trading Platform</p>
        <div class="hint">
            <h3>Frontend not built yet</h3>
            <p style="color:#8b949e; font-size:0.9rem;">Build the React dashboard to get started:</p>
            <code>cd frontend && npm run build</code>
            <p style="color:#8b949e; font-size:0.9rem; margin-top:12px;">
                Or use dev mode with hot-reload:
            </p>
            <code>cd frontend && npm run dev</code>
            <p style="color:#8b949e; font-size:0.85rem; margin-top:16px;">
                API docs available at <a href="/api/docs">/api/docs</a>
            </p>
        </div>
    </div>
</body>
</html>"""
