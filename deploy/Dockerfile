FROM python:3.11-slim AS base

# Install TA-Lib C library (required by python TA-Lib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    && wget -q https://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz \
    && apt-get purge -y build-essential wget \
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

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
