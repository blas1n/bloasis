# =============================================================================
# BLOASIS Frontend - Next.js Production Dockerfile
# =============================================================================
# Build context: monorepo root (..)
# Multi-stage build:
#   Stage 0 (schema-gen): Python -> generate openapi.json from FastAPI app
#   Stage 1 (deps):       Node   -> npm ci
#   Stage 2 (builder):    Node   -> generate:api + next build
#   Stage 3 (runner):     Node   -> production runtime (standalone)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 0: Generate OpenAPI schema (Python)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS schema-gen

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen

COPY app/ ./app/
COPY shared/ ./shared/
COPY scripts/ ./scripts/

# Generates /app/openapi.json (no DB connection needed)
RUN PYTHONPATH=/app uv run python scripts/export_openapi.py

# -----------------------------------------------------------------------------
# Stage 1: Node.js dependencies
# -----------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./

# devDependencies required for build: tailwindcss, postcss, typescript
RUN npm ci

# -----------------------------------------------------------------------------
# Stage 2: Builder
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules

# Place openapi.json at /openapi.json so ../openapi.json resolves from /app
COPY --from=schema-gen /app/openapi.json /openapi.json

# Frontend source
COPY frontend/ .

# Generate TypeScript types from OpenAPI schema
RUN npm run generate:api

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 3: Runner (Production)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

CMD ["node", "server.js"]
