FROM python:3.11-slim AS base

# Install TA-Lib C library (latest from GitHub, aarch64-compatible)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    autoconf \
    automake \
    libtool \
    && git clone --depth 1 https://github.com/TA-Lib/ta-lib.git \
    && cd ta-lib \
    && autoreconf -fiv \
    && ./configure --prefix=/usr \
    && make -j$(nproc) \
    && make install \
    && cd .. \
    && rm -rf ta-lib \
    && apt-get purge -y build-essential git autoconf automake libtool \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache .

# Copy application code
COPY app/ ./app/
COPY shared/ ./shared/

# Copy migration files
COPY alembic.ini ./
COPY deploy/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
