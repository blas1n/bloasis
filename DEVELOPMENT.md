# BLOASIS Development Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### Architecture Overview

```
Frontend (Next.js :3000) --> FastAPI (:8000) --> PostgreSQL + Redis
```

Single FastAPI monolith. No gRPC, no message brokers, no service mesh.

---

## Starting the Full Stack

### 1. Start Infrastructure

```bash
docker compose -f deploy/docker-compose.yml up -d postgres redis
```

Expected services:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)

### 2. Run Database Migrations

```bash
uv run alembic upgrade head
```

### 3. Start Backend

```bash
uv run uvicorn app.main:app --reload
```

Backend runs at **http://localhost:8000**. Health check: `GET /health`

### 4. Start Frontend

```bash
cd frontend
npm run dev
```

Visit: **http://localhost:3000**

---

## Service Ports

| Service | Port | Type |
|---------|------|------|
| Frontend | 3000 | HTTP (dev) |
| FastAPI backend | 8000 | HTTP/REST |
| PostgreSQL | 5432 | TCP |
| Redis | 6379 | TCP |

---

## Development Workflow

### Commands

```bash
ruff check app/ shared/          # Lint
ruff format app/ shared/         # Format
pytest app/ --cov=app            # Test with 80% coverage gate
pytest app/core/tests/ -v        # Core domain tests only (no mocks)
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bloasis
REDIS_HOST=localhost
REDIS_PORT=6379
LLM_API_KEY=your-api-key
LLM_MODEL=anthropic/claude-haiku-4-5-20251001
JWT_SECRET_KEY=your-secret
```

All variables validated via Pydantic Settings in `app/config.py`.

---

## Code Organization

### Adding a New Endpoint

1. Add route handler in `app/routers/`
2. Add business logic in `app/services/`
3. Put pure computation in `app/core/` (if applicable)
4. Register router in `app/main.py`
5. Add DI wiring in `app/dependencies.py`
6. Write tests

### Layer Rules

| Layer | Can Import | Cannot Import |
|-------|-----------|---------------|
| `core/` | stdlib, pydantic | services, routers, shared, DB, Redis |
| `services/` | core, shared | routers |
| `routers/` | services, dependencies | core (directly), shared |
| `shared/` | stdlib, third-party | app (anything) |

---

## Troubleshooting

### Backend Won't Start

```bash
# Check infrastructure is running
docker compose -f deploy/docker-compose.yml ps

# Verify database connection
psql -h localhost -U postgres -d bloasis -c "SELECT 1;"

# Check Redis
redis-cli ping
```

### Database Connection Failed

```bash
docker compose -f deploy/docker-compose.yml restart postgres
```

### Module Import Errors

Never use `pip install` or `requirements.txt`. Use:

```bash
uv sync                          # Install dependencies
PYTHONPATH=/workspace uv run ...  # Run with correct path
```

---

## Quick Health Check

```bash
echo "=== BLOASIS Health Check ==="

echo -n "Backend: "
curl -s http://localhost:8000/health > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "Frontend: "
curl -s http://localhost:3000 > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "PostgreSQL: "
pg_isready -h localhost -p 5432 > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "Redis: "
redis-cli ping > /dev/null 2>&1 && echo "OK" || echo "DOWN"
```

---

## Additional Resources

- **Architecture rules**: `.claude/rules/`
- **Database schema**: `infra/postgres/`
- **Docker config**: `deploy/docker-compose.yml`
