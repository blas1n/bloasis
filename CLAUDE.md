# BLOASIS

AI-powered multi-asset trading platform combining LLMs and deterministic risk rules.

## Tech Stack

- **Backend**: Python 3.11+ (FastAPI monolith)
- **AI/ML**: Claude Haiku (via LiteLLM), deterministic risk rules, 6-factor scoring
- **Data**: yfinance (market data), TA-Lib (technical indicators)
- **Infra**: PostgreSQL/TimescaleDB, Redis (caching), Docker Compose
- **Frontend**: TypeScript (React/Next.js)
- **Tooling**: uv (package manager), ruff (lint/format), Alembic (migrations)

## Project Structure

```
app/                # FastAPI monolith
  main.py           # Application entry point + lifespan
  config.py         # Unified Pydantic Settings
  dependencies.py   # FastAPI dependency injection + auth
  routers/          # API endpoints (REST)
    auth.py         # /v1/auth/tokens
    market.py       # /v1/market/regimes/current
    signals.py      # /v1/users/{userId}/signals
    trading.py      # /v1/users/{userId}/trading
    users.py        # /v1/users/{userId}/preferences, broker
    portfolios.py   # /v1/portfolios/{userId}
  services/         # Business logic layer
    strategy.py     # Analysis pipeline (regime → classification → scoring → signals)
    executor.py     # Order execution with risk checks + Alpaca API
    market_regime.py # Market regime classification (LLM)
    classification.py # Sector/asset classification (LLM)
    market_data.py  # yfinance data + caching
    portfolio.py    # Position/trade management
    user.py         # Supabase Auth proxy, preferences, broker config
  core/             # Pure computation (no I/O)
    models.py       # Pydantic domain models
    risk_rules.py   # Deterministic risk evaluation
    signal_generator.py # ATR-based signal generation
    factor_scoring.py   # 6-factor stock scoring engine
    technical_indicators.py # TA-Lib calculations
    regime_classifier.py    # Regime response parsing
    prompts/        # LLM prompt templates
  repositories/     # Database access (SQLAlchemy ORM)
    models.py       # ORM table definitions
    user_repository.py
    portfolio_repository.py
    trade_repository.py
  shared/utils/     # App-level utilities
    response.py     # CamelCase JSON response
    cache.py        # @cache_aside decorator
shared/             # Shared infrastructure clients
  ai_clients/       # LLM client (LiteLLM)
  utils/            # PostgresClient, RedisClient
frontend/           # Next.js frontend
deploy/             # Docker Compose configs
```

## Quick Commands

```bash
ruff check app/ shared/          # Lint
ruff format app/ shared/         # Format
mypy app/ shared/                # Type check
pytest app/ --cov=app            # Test with coverage
python scripts/export_openapi.py # Export OpenAPI schema
uvicorn app.main:app --reload    # Dev server
```

## Architecture Rules (Quick Reference)

Full rules in `.claude/rules/` — these are the non-negotiable ones:

- **FastAPI REST** — single monolith, no gRPC or message brokers
- **Repository pattern** — all DB access via `app/repositories/` (SQLAlchemy ORM, no raw SQL)
- **Pure core/** — no I/O in `app/core/`, only computation and models
- **Decimal** for all financial calculations (never float)
- **Type hints** on all public functions
- **Supabase Auth** — token verification via `bsvibe-auth` (HS256), all endpoints except `/v1/auth/*` and `/health`
- **No sys.path.insert()** — use PYTHONPATH
- **No hardcoded secrets** — use .env files (gitignored)
- **Tests mandatory** — 80% minimum coverage, mock all external APIs
- **ruff check** must pass before commit

## Git Conventions

- No `Co-Authored-By` in commit messages
- Format: `type(scope): short description`
- Types: feat, fix, refactor, test, docs, chore

## Caching Strategy (3-Tier)

| Tier | Data | TTL | Shared? |
|------|------|-----|---------|
| Tier 1 | Market regime, sector candidates | 6h | All users |
| Tier 2 | User analysis results | 1h | Per-user |
| Tier 3 | Preferences, OHLCV, stock info | 5m-30d | Per-user/symbol |

## Cost Optimization

- **Hybrid 3-Tier**: Shared analysis (Tier 1) cached across users + per-user customization (Tier 2-3)
- Claude Haiku for classification, rule-based fallback when no API key
- Deterministic risk rules (no LLM for risk evaluation)
