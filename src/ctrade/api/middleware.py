"""FastAPI middleware for CORS, request logging, JWT auth, etc."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that never require authentication
_PUBLIC_PATHS: set[str] = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
}

# Path prefixes that are always public
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/assets",      # static frontend assets
    "/favicon",
)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI application."""

    # CORS — allow dashboard frontend (in development, allow all origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth_middleware(
        request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """Enforce JWT authentication on API routes.

        Skips auth for public paths, non-API paths (frontend SPA),
        and WebSocket upgrade requests (WS endpoint handles its own auth).
        """
        path = request.url.path

        # Skip auth entirely if disabled
        from ctrade.settings import get_settings
        settings = get_settings()
        if not settings.auth.enabled:
            return await call_next(request)

        # Skip non-API paths (frontend SPA, static files)
        if not path.startswith("/api"):
            return await call_next(request)

        # Skip public paths
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip WebSocket upgrade requests (handled by the endpoint itself)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Check for the WS path specifically
        if path == "/api/v1/ws":
            return await call_next(request)

        # Validate Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "
        from ctrade.core.exceptions import AuthenticationError
        from ctrade.security.auth import verify_access_token

        try:
            verify_access_token(
                token,
                secret_key=settings.auth.secret_key.get_secret_value(),
                algorithm=settings.auth.algorithm,
            )
        except AuthenticationError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """Log request method, path, status code, and duration."""
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
