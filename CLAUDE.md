# BLOASIS

AI-powered multi-asset trading platform combining LLMs and Reinforcement Learning.

## Tech Stack

- **Backend**: Python 3.11+ (gRPC-only services, no FastAPI/HTTP)
- **AI/ML**: Claude (claude-haiku-4-5-20251001), LangGraph (multi-agent orchestration)
- **Backtesting**: VectorBT, FinRL
- **Infra**: Envoy Gateway (gRPC→REST), Redpanda (messaging), PostgreSQL/TimescaleDB
- **Frontend**: TypeScript (React/Next.js)
- **Tooling**: uv (package manager), buf (proto), ruff (lint/format)

## Project Structure

```
services/           # Microservices (gRPC-only, Python)
  auth/             # Authentication
  backtesting/      # Strategy backtesting
  classification/   # Asset classification
  executor/         # Trade execution
  market-data/      # Market data ingestion
  market-regime/    # Market regime detection
  portfolio/        # Portfolio management
  risk-committee/   # Risk assessment
  strategy/         # Strategy generation
  user/             # User management
shared/             # Cross-service code
  proto/            # .proto definitions (buf managed)
  generated/        # Auto-generated proto files (gitignored)
  ai_clients/       # Claude API wrappers
  models/           # Shared data models
  prompts/          # LLM prompt templates
  utils/            # Shared utilities
tests/              # Integration & E2E tests
frontend/           # Next.js frontend
infra/              # Infrastructure configs
deploy/             # Deployment configs
```

## Quick Commands

```bash
make proto-generate  # Generate proto files + Envoy descriptor
make lint            # ruff check shared/ services/
make test            # pytest with 80% coverage gate
make check           # lint + proto-lint + test
```

## Architecture Rules (Quick Reference)

Full rules in `.claude/rules/` — these are the non-negotiable ones:

- **gRPC only** between services (no HTTP/REST internally)
- **Redpanda** for messaging (not Redis Pub/Sub or RabbitMQ)
- **Envoy Gateway** handles external REST via gRPC-to-REST transcoding
- **All .proto files** must have HTTP annotations for Envoy
- **Decimal** for all financial calculations (never float)
- **Type hints** on all public functions
- **No sys.path.insert()** — use PYTHONPATH
- **No service-level Dockerfiles** or requirements.txt — use pyproject.toml + uv
- **No hardcoded secrets** — use .env files (gitignored)
- **Tests mandatory** — 80% minimum coverage, mock all external APIs
- **ruff check** must pass before commit

## Git Conventions

- No `Co-Authored-By` in commit messages
- Format: `type(scope): short description`
- Types: feat, fix, refactor, test, docs, chore

## Cost Optimization

- **Hybrid 3-Tier**: Shared analysis (Tier 1-2) cached across users + per-user customization (Tier 3)
- Claude Haiku for classification, rule-based fallback when no API key
- Reduces API costs by ~93%
