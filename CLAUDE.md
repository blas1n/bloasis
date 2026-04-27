# BLOASIS — Claude Working Notes

CLI trading research and execution platform. Deterministic factor scoring
on US large caps with optional ML and LLM sentiment.

> Read [`docs/mission.md`](./docs/mission.md) and [`docs/roadmap.md`](./docs/roadmap.md)
> before changing anything. Mission constrains design.

## Tech Stack

- Python 3.11+ (CLI app, single user)
- typer + rich (CLI)
- pydantic v2 (config + domain models on API boundary)
- SQLAlchemy core, SQLite (Postgres migration path open)
- yfinance (OHLCV/fundamentals), Finnhub (news)
- LiteLLM for sentiment scoring — provider-agnostic (Anthropic/OpenAI/Azure/Ollama).
  Configure via `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`. Default is
  Claude Haiku for cost; users may switch via `.env`.
- TA-Lib (technical indicators)
- LightGBM + SHAP (Phase 3 ML stub now)
- Alpaca (paper trading)
- ruff (lint/format), mypy strict, pytest

## Quick Commands

```bash
ruff check bloasis/ tests/        # lint
ruff format bloasis/ tests/       # format
mypy bloasis/                     # type check (strict)
pytest tests/ --cov=bloasis       # tests
bloasis init-db                   # create SQLite + tables
bloasis config show configs/baseline.yaml
```

## Architecture Rules (non-negotiable)

### 1. CLI single-process, single-user

No web server, no message broker, no multi-user concerns. `user_id`
column exists on user-scoped tables but always `0` in v1.

### 2. Pure scoring layer

`bloasis/scoring/` and `bloasis/data/extractor.py` must have **no I/O**.
Same code runs in live and backtest paths. Any I/O lives in
`bloasis/data/fetchers/` and `bloasis/storage/`.

### 3. Look-ahead bias protection

`ExtractionContext.__post_init__` asserts `ohlcv.index.max() <= timestamp`.
Tests must include a regression case constructing an "evil" context with
future data and verifying the assertion fires.

### 4. Walk-forward only

Backtests use train/test windows. Full-history optimization is forbidden
as a CI-enforced rule once `bloasis/backtest/walk_forward.py` lands.

### 5. Repository pattern

All DB access goes through `bloasis/storage/` modules. No raw SQL strings
in business logic. SQLAlchemy core (`Table()`, `select()`, `insert()`) —
no ORM mappers in v1.

### 6. Decimal for money on ledger boundary

Prices/quantities flowing into `trades` and `positions` tables use
`decimal.Decimal`. Floats are acceptable inside scoring computations.

### 7. Type hints required

All public functions need type hints. mypy strict must pass.

### 8. No hardcoded secrets

Use `.env` (gitignored) + pydantic settings. Never log API keys.

### 9. Tests mandatory

New code needs tests. CI enforces > 70% coverage on `bloasis/`. Mock all
external APIs (yfinance, Finnhub, LLM, Alpaca) in tests.

### 10. Acceptance gates respected

Promoting a config to live trading requires walk-forward backtest passing
the config's `acceptance_criteria`. CLI enforces this.

## Feature & Schema Versioning

- `feature_log.feature_version` integer column. Bump when extraction logic
  changes. ML training filters by version.
- DDL changes use SQLAlchemy `MetaData.create_all()` for v1. When
  migrating to Postgres or schema gets non-trivial, introduce alembic.

## Git Conventions

- No `Co-Authored-By` in commit messages
- Format: `type(scope): description`
- Types: feat, fix, refactor, test, docs, chore
- One PR per phase milestone (PR1..PR6 for Phase 1)

## Cost & Risk Discipline

- Daily LLM call budget caps in `configs/*.yaml`
- yfinance scrapes; pinned version, parquet cache for resilience
- Finnhub free tier rate-limited via `aiolimiter`
- All financial calculations on the ledger use `Decimal`
- Live trading defaults to **paper** until acceptance gate passes
