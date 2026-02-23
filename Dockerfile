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

# ---- Python dependencies ----
# Install CPU-only PyTorch first (saves ~1.5 GB vs CUDA build)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# Copy only dependency metadata first (better layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir . 2>/dev/null || true
# The above may partially fail because src/ctrade isn't copied yet.
# We do a proper install after copying source below.

# ---- Frontend build ----
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm ci --ignore-scripts

COPY frontend/ frontend/
RUN cd frontend && npm run build

# ---- Copy Python source & install ----
COPY src/ src/
COPY pyproject.toml alembic.ini ./
COPY alembic/ alembic/
COPY config/ config/

# Full install (editable so ctrade package is importable)
RUN pip install --no-cache-dir -e .

# --------------- Stage 2: Runtime ---------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
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

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${CTRADE_API_PORT}/api/v1/health || exit 1

# At runtime, map Railway's $PORT to our env var, then start the app
CMD sh -c "CTRADE_API_PORT=\${PORT:-\$CTRADE_API_PORT} exec python -m ctrade.main"
