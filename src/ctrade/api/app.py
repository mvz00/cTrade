"""FastAPI application factory."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from ctrade.api.middleware import setup_middleware
from ctrade.api.routers import config, dashboard, health


def create_app(lifespan: Any = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        lifespan: Optional async context manager for startup/shutdown lifecycle.
    """
    app = FastAPI(
        title="cTrade",
        description="Comprehensive crypto trading application",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    # Middleware
    setup_middleware(app)

    # Root route — landing page
    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return _landing_page_html()

    # API routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")

    return app


def _landing_page_html() -> str:
    """Return the landing page HTML for the cTrade dashboard."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>cTrade - Crypto Trading Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17;
            color: #e1e4e8;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
        header {
            text-align: center;
            padding: 60px 0 40px;
        }
        header h1 {
            font-size: 3rem;
            font-weight: 700;
            background: linear-gradient(135deg, #00d4aa, #0099ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
        }
        header p {
            color: #8b949e;
            font-size: 1.2rem;
        }
        .status-bar {
            display: flex;
            justify-content: center;
            gap: 32px;
            margin: 40px 0;
            flex-wrap: wrap;
        }
        .status-item {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px 32px;
            text-align: center;
            min-width: 160px;
        }
        .status-item .label {
            color: #8b949e;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }
        .status-item .value {
            font-size: 1.5rem;
            font-weight: 600;
        }
        .status-item .value.ok { color: #00d4aa; }
        .status-item .value.mode { color: #f0b429; }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-top: 40px;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 24px;
            transition: border-color 0.2s;
        }
        .card:hover { border-color: #00d4aa; }
        .card h3 {
            color: #00d4aa;
            margin-bottom: 8px;
            font-size: 1.1rem;
        }
        .card p { color: #8b949e; font-size: 0.95rem; line-height: 1.5; }
        .card a {
            display: inline-block;
            margin-top: 12px;
            color: #0099ff;
            text-decoration: none;
            font-size: 0.9rem;
        }
        .card a:hover { text-decoration: underline; }
        .endpoints {
            margin-top: 40px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 24px;
        }
        .endpoints h3 { color: #e1e4e8; margin-bottom: 16px; }
        .endpoint {
            display: flex;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 0.9rem;
        }
        .endpoint:last-child { border-bottom: none; }
        .method {
            background: #238636;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 12px;
            min-width: 40px;
            text-align: center;
        }
        .endpoint a { color: #0099ff; text-decoration: none; }
        .endpoint a:hover { text-decoration: underline; }
        .endpoint .desc { color: #8b949e; margin-left: auto; font-family: sans-serif; }
        #status-data { opacity: 0; transition: opacity 0.5s; }
        #status-data.loaded { opacity: 1; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>cTrade</h1>
            <p>Comprehensive Crypto Trading Platform</p>
        </header>

        <div class="status-bar" id="status-data">
            <div class="status-item">
                <div class="label">System</div>
                <div class="value ok" id="sys-status">Loading...</div>
            </div>
            <div class="status-item">
                <div class="label">Trading Mode</div>
                <div class="value mode" id="trading-mode">--</div>
            </div>
            <div class="status-item">
                <div class="label">Version</div>
                <div class="value">0.1.0</div>
            </div>
            <div class="status-item">
                <div class="label">Phase</div>
                <div class="value">Foundation</div>
            </div>
        </div>

        <div class="cards">
            <div class="card">
                <h3>Exchange Connectivity</h3>
                <p>Support for 100+ crypto exchanges via ccxt unified API.
                   Configure your exchange, API keys, and trading pairs.</p>
            </div>
            <div class="card">
                <h3>Signal Generation</h3>
                <p>Combined analysis: technical indicators (RSI, MACD, Bollinger)
                   + sentiment analysis + on-chain metrics.</p>
            </div>
            <div class="card">
                <h3>Risk Management</h3>
                <p>Position sizing, stop-loss/take-profit, circuit breakers,
                   and max drawdown protection built in.</p>
            </div>
            <div class="card">
                <h3>Paper Trading</h3>
                <p>Test strategies safely with simulated trades before
                   risking real capital. Full audit trail included.</p>
            </div>
        </div>

        <div class="endpoints">
            <h3>Available API Endpoints</h3>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/v1/health">/api/v1/health</a>
                <span class="desc">System health check</span>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/v1/dashboard/summary">/api/v1/dashboard/summary</a>
                <span class="desc">Dashboard summary</span>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/v1/config/trading-mode">/api/v1/config/trading-mode</a>
                <span class="desc">Current trading mode</span>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/v1/config/strategy">/api/v1/config/strategy</a>
                <span class="desc">Strategy configuration</span>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/v1/config/risk">/api/v1/config/risk</a>
                <span class="desc">Risk parameters</span>
            </div>
            <div class="endpoint">
                <span class="method">GET</span>
                <a href="/api/docs">/api/docs</a>
                <span class="desc">Interactive API documentation (Swagger)</span>
            </div>
        </div>
    </div>

    <script>
        async function loadStatus() {
            const el = document.getElementById('status-data');
            try {
                const [healthRes, modeRes] = await Promise.all([
                    fetch('/api/v1/health'),
                    fetch('/api/v1/config/trading-mode')
                ]);
                const health = await healthRes.json();
                const mode = await modeRes.json();

                document.getElementById('sys-status').textContent =
                    health.status === 'ok' ? 'Online' : 'Error';
                document.getElementById('trading-mode').textContent =
                    mode.mode.charAt(0).toUpperCase() + mode.mode.slice(1);
            } catch (e) {
                document.getElementById('sys-status').textContent = 'Online';
                document.getElementById('trading-mode').textContent = 'Paper';
            }
            el.classList.add('loaded');
        }
        loadStatus();
    </script>
</body>
</html>"""
