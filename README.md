# BLOASIS

**AI-Powered Multi-Asset Trading Platform**

BLOASIS combines Large Language Models and Reinforcement Learning for automated trading decisions across multiple asset classes.

## Mission

- **Risk Management**: User-specific risk profiles (Conservative/Moderate/Aggressive)
- **Strategy Optimization**: LLM strategy generation → Quantitative parameter fitting → RL validation
- **Multi-Asset Trading**: Diversified trading across different asset classes
- **Event-Driven Response**: Real-time market regime detection for critical events (FOMC, CPI, etc.)

## Architecture

Microservices architecture with gRPC-only internal communication and Envoy Gateway for external REST access.

```
Frontend (Next.js) → Envoy Gateway (REST→gRPC) → Backend Services (gRPC)
                                               ↓
                                    Redpanda, PostgreSQL/TimescaleDB
```

**Services**:
- **Market Regime**: Market condition classification (bull/bear/crisis/recovery)
- **Strategy**: LangGraph multi-agent strategy generation via Claude
- **Classification**: 3-Tier asset selection (Sector → Thematic → Factor)
- **Backtesting**: Multi-strategy backtesting with VectorBT + FinRL
- **Risk Committee**: Risk assessment and position sizing
- **Portfolio**: Portfolio tracking and management
- **Executor**: Real-time order execution
- **Market Data**: OHLCV ingestion and caching
- **Auth**: Authentication and authorization
- **User**: User preferences and profiles

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, gRPC-only (no HTTP/REST) |
| AI/ML | Claude (claude-haiku-4-5-20251001), LangGraph |
| Backtesting | VectorBT, FinRL |
| Gateway | Envoy Gateway (gRPC-to-REST transcoding) |
| Messaging | Redpanda (Kafka-compatible) |
| Database | PostgreSQL, TimescaleDB |
| Frontend | TypeScript, React/Next.js |
| Tooling | uv, buf, ruff |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [buf](https://buf.build/) (proto tooling)

### Setup

```bash
# 1. Clone
git clone https://github.com/yourusername/bloasis.git
cd bloasis

# 2. Generate proto files
make proto-generate

# 3. Start infrastructure
docker-compose -f deploy/docker-compose.yml up -d

# 4. Run a service
cd services/market-regime
uv run python -m src.main
```

### Development Commands

```bash
make proto-generate  # Generate proto files + Envoy descriptor
make lint            # ruff check shared/ services/
make test            # pytest with 80% coverage gate
make check           # lint + proto-lint + test
```

## Project Structure

```
services/           # Microservices (gRPC-only, Python)
  auth/             # port 50056
  backtesting/      # port 50058
  classification/   # port 50054
  executor/         # port 50060
  market-data/      # port 50053
  market-regime/    # port 50051
  portfolio/        # port 50057
  risk-committee/   # port 50059
  strategy/         # port 50055
  user/             # port 50052
shared/             # Cross-service code
  proto/            # .proto definitions (buf managed)
  generated/        # Auto-generated (gitignored)
  ai_clients/       # Claude API wrappers
  prompts/          # LLM prompt templates
  utils/            # Shared utilities
tests/              # Integration & E2E tests
frontend/           # Next.js dashboard
infra/              # Envoy, Redpanda, PostgreSQL configs
deploy/             # Docker Compose, Dockerfile
```

## Testing

```bash
# All tests with coverage
make test

# Integration tests only
uv run pytest tests/integration/

# Single service
uv run pytest services/market-regime/tests/ --cov=src --cov-fail-under=80
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run `make check` (lint + proto-lint + tests must pass)
4. Commit: `git commit -m 'feat(scope): description'`
5. Open a Pull Request

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

## Disclaimer

This software is for educational and research purposes only. The developers are not responsible for any losses from actual trading. Trade at your own risk.
