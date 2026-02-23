# ============================================================
# cTrade — Multi-stage Docker build
# Stage 1: Build frontend + install Python deps
# Stage 2: Lean runtime image
# ============================================================

# --------------- Stage 1: Builder ---------------
FROM python:3.13-slim AS builder

WORKDIR /app

# System deps for building Python packages (asyncpg, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node 20 for the frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- Frontend build ----
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm ci --ignore-scripts

COPY frontend/ frontend/
RUN cd frontend && npm run build

# ---- Python: install app + core deps ----
COPY src/ src/
COPY pyproject.toml alembic.ini ./
COPY alembic/ alembic/
COPY config/ config/

# Install the app and all core dependencies (non-editable for multi-stage)
RUN pip install --no-cache-dir .

# --------------- Stage 2: Runtime ---------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime system deps only (libpq5 for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/
COPY --from=builder /app/alembic.ini /app/
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/config /app/config

# Copy built frontend
COPY --from=builder /app/frontend/dist /app/frontend/dist

# Bind to all interfaces (required for Railway / container networking)
ENV CTRADE_API_HOST=0.0.0.0

# Default port for local docker run (Railway overrides via $PORT at runtime)
ENV CTRADE_API_PORT=8000

# Tell app.py where the built frontend lives (non-editable install means
# __file__-based path resolution won't reach /app from site-packages)
ENV CTRADE_FRONTEND_DIR=/app/frontend/dist

# Ensure Python output is sent straight to Railway logs (no buffering)
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# NOTE: No Dockerfile HEALTHCHECK — Railway uses its own healthcheck
# configured in railway.json (healthcheckPath: /api/v1/health).
# A Dockerfile HEALTHCHECK would conflict because Railway sets PORT
# dynamically, but CTRADE_API_PORT defaults to 8000.

# Start the app (Railway's $PORT is read directly by settings.py)
CMD ["python", "-m", "ctrade.main"]
