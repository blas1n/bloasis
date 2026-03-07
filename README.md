# BLOASIS

**AI-Powered Multi-Asset Trading Platform**

BLOASIS combines LLMs and deterministic risk rules for automated trading decisions across multiple asset classes.

## Key Features

- **Market Regime Detection**: LLM-based classification (bull/bear/crisis/recovery/sideways)
- **6-Factor Scoring**: Momentum, value, quality, volatility, liquidity, sentiment
- **Deterministic Risk Rules**: Position sizing, sector concentration, VIX-based controls
- **ATR-Based Signals**: Stop loss, take profit, trailing stops, multi-tier profit levels
- **Alpaca Integration**: Paper/live trading via Alpaca API

## Architecture

Single FastAPI monolith with pure domain logic isolated in `core/`.

```
Frontend (Next.js) --> FastAPI (REST) --> PostgreSQL + Redis
```

**Design principles**:
- `core/` -- Pure computation, zero I/O, testable without mocks
- `services/` -- Orchestration layer (LLM calls, DB, cache)
- `routers/` -- Thin HTTP layer, Pydantic validation
- `shared/` -- Infrastructure adapters (LLM, Postgres, Redis clients)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI |
| AI/ML | LiteLLM, deterministic risk rules |
| Data | yfinance, TA-Lib, FRED API |
| Database | PostgreSQL/TimescaleDB, Redis |
| Frontend | TypeScript, React/Next.js |
| Tooling | uv, ruff, Alembic |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)

### Setup

```bash
# 1. Clone
git clone https://github.com/yourusername/bloasis.git
cd bloasis

# 2. Install dependencies
uv sync

# 3. Start infrastructure
docker compose -f deploy/docker-compose.yml up -d postgres redis

# 4. Run database migrations
uv run alembic upgrade head

# 5. Start backend
uv run uvicorn app.main:app --reload

# 6. Start frontend
cd frontend && npm run dev
```

Visit: **http://localhost:3000**

### Development Commands

```bash
ruff check app/ shared/          # Lint
ruff format app/ shared/         # Format
pytest app/ --cov=app            # Test (80% coverage gate)
uvicorn app.main:app --reload    # Dev server
```

## Project Structure

```
app/                  # FastAPI monolith
  main.py             # Entry point + lifespan
  config.py           # Pydantic Settings (all env vars)
  dependencies.py     # FastAPI DI + auth
  core/               # Pure computation (no I/O)
    models.py          # Pydantic domain models
    risk_rules.py      # Deterministic risk evaluation
    signal_generator.py # ATR-based signal generation
    factor_scoring.py  # 6-factor stock scoring
    technical_indicators.py # TA-Lib calculations
    regime_classifier.py # Regime response parsing
    prompts/           # LLM prompt templates
  services/            # Business logic (orchestration)
    strategy.py        # Analysis pipeline
    executor.py        # Order execution + Alpaca
    market_regime.py   # Market regime classification
    classification.py  # Sector/asset classification
    market_data.py     # yfinance + caching
    portfolio.py       # Position/trade management
    user.py            # Auth, preferences, broker
  routers/             # REST endpoints
    auth.py            # /v1/auth/tokens
    market.py          # /v1/market/regimes/current
    signals.py         # /v1/users/{id}/signals
    trading.py         # /v1/users/{id}/trading
    users.py           # /v1/users/{id}/preferences, broker
    portfolios.py      # /v1/portfolios/{id}
    orders.py          # /v1/orders
  shared/utils/        # App utilities
    response.py        # CamelCase JSON response
    cache.py           # @cache_aside decorator
shared/                # Infrastructure adapters
  ai_clients/          # LLM client (LiteLLM)
  utils/               # PostgresClient, RedisClient
frontend/              # Next.js dashboard
deploy/                # Docker Compose
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/auth/tokens | Login |
| POST | /v1/auth/tokens/refresh | Refresh token |
| DELETE | /v1/auth/tokens | Logout |
| GET | /v1/market/regimes/current | Current market regime |
| GET | /v1/users/{id}/preferences | Get preferences |
| PUT | /v1/users/{id}/preferences | Update preferences |
| GET | /v1/users/{id}/broker | Broker status |
| PUT | /v1/users/{id}/broker | Update broker config |
| GET | /v1/users/{id}/signals | Get cached signals |
| POST | /v1/users/{id}/signals | Trigger analysis |
| GET | /v1/users/{id}/trading | Trading status |
| POST | /v1/users/{id}/trading | Start trading |
| DELETE | /v1/users/{id}/trading | Stop trading |
| GET | /v1/portfolios/{id} | Portfolio summary |
| GET | /v1/portfolios/{id}/positions | Positions |
| GET | /v1/portfolios/{id}/trades | Trade history |
| POST | /v1/portfolios/{id}/sync | Sync with Alpaca |
| POST | /v1/orders | Execute order |

## Testing

```bash
# Full test suite with coverage
pytest app/ --cov=app --cov-fail-under=80

# Core domain tests only (no mocks needed)
pytest app/core/tests/ -v

# Lint + format check
ruff check app/ shared/
ruff format --check app/ shared/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run `ruff check app/ shared/` and `pytest app/` (must pass)
4. Commit: `git commit -m 'feat(scope): description'`
5. Open a Pull Request

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

## Disclaimer

This software is for educational and research purposes only. The developers are not responsible for any losses from actual trading. Trade at your own risk.
