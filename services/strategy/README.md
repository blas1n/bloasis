# Strategy Service

Stock Selection Pipeline Stage 3 - Factor Scoring and User Preferences Management

## Overview

The Strategy Service implements Stage 3 of the Stock Selection Pipeline, performing factor-based scoring and user preference management. It combines candidate symbols from Classification Service (Stage 1-2) with 6-factor analysis and risk profile-based weighting to generate personalized stock recommendations.

## Features

### Stage 3: Factor Scoring

- **6-Factor Scoring System**:
  - Momentum: Price trend vs moving averages
  - Value: P/E, P/B ratios (placeholder)
  - Quality: ROE, debt ratios (placeholder)
  - Volatility: Price volatility (inverse scoring)
  - Liquidity: Trading volume
  - Sentiment: News/social sentiment (placeholder)

- **Risk Profile-Based Weighting**:
  - Conservative: High quality/value, low volatility
  - Moderate: Balanced approach
  - Aggressive: High momentum/sentiment

### User Preferences Management

- **Risk Profiles**: Conservative, Moderate, Aggressive
- **Sector Preferences**: Preferred and excluded sectors
- **Position Sizing**: Maximum single position limit

### Layer 3 Caching

- **User-specific caching** with 1-hour TTL
- Preferences cached for 30 days
- Automatic cache invalidation on preference updates

## Architecture

### Service Information

- **Port**: 50055 (gRPC)
- **Protocol**: gRPC with HTTP annotations (Envoy Gateway transcoding)
- **Caching**: Layer 3 (user-specific)

### Dependencies

- Classification Service (Stage 1-2 results)
- Market Data Service (OHLCV data)
- Market Regime Service (current regime)
- Redis (Layer 3 caching)

## gRPC API

### Methods

#### GetStockPicks

Get stock picks with factor scoring for a user.

```protobuf
rpc GetStockPicks(StockPicksRequest) returns (StockPicksResponse)
```

#### GetPersonalizedStrategy

Get complete personalized strategy (Layer 1+2+3 combined).

```protobuf
rpc GetPersonalizedStrategy(StrategyRequest) returns (StrategyResponse)
```

#### UpdatePreferences

Update user preferences (risk profile, sectors).

```protobuf
rpc UpdatePreferences(UpdatePreferencesRequest) returns (UpdatePreferencesResponse)
```

#### GetPreferences

Get current user preferences.

```protobuf
rpc GetPreferences(GetPreferencesRequest) returns (UserPreferences)
```

## Development

### Requirements

- Python 3.11+
- Redis (for caching)
- Classification, Market Data, Market Regime services (for integration)

### Installation

```bash
cd services/strategy
uv pip install -e ".[dev]"
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Service
SERVICE_NAME=strategy
GRPC_PORT=50055

# Redis (Layer 3 caching)
REDIS_HOST=redis
REDIS_PORT=6379

# Dependent Services
MARKET_REGIME_HOST=market-regime
MARKET_REGIME_PORT=50051
CLASSIFICATION_HOST=classification
CLASSIFICATION_PORT=50054
MARKET_DATA_HOST=market-data
MARKET_DATA_PORT=50053
```

### Running

```bash
# Development
python -m src.main

# With auto-reload
watchmedo auto-restart -d src/ -p '*.py' -- python -m src.main
```

### Testing

```bash
# Run all tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_service.py -v

# Run with coverage threshold
pytest tests/ --cov=src --cov-fail-under=80
```

### Code Quality

```bash
# Lint check
ruff check src/ tests/

# Format check
ruff format --check src/ tests/

# Auto-fix
ruff check --fix src/ tests/
ruff format src/ tests/
```

## Implementation Status

### Completed

- ✅ 6-factor scoring engine
- ✅ Risk profile-based weighting
- ✅ User preferences management
- ✅ Layer 3 caching (user-specific)
- ✅ gRPC service with HTTP annotations
- ✅ gRPC clients (Classification, Market Data, Market Regime)
- ✅ Comprehensive tests (87.71% coverage)

### TODO (Future Tasks)

- 🔄 Value factor: Integrate financial data API (Alpha Vantage, yfinance)
- 🔄 Quality factor: Integrate financial data API
- 🔄 Sentiment factor: Integrate news sentiment analysis (Claude or external API)
- 🔄 LangGraph integration: Task 5 (5-Layer AI Flow)

## Proto Definition

Service proto: `shared/proto/strategy.proto`

Key messages:
- `StockPicksRequest/Response`: Factor-scored stock picks
- `StrategyRequest/Response`: Complete personalized strategy
- `UserPreferences`: Risk profile and sector preferences
- `FactorScores`: 6-factor breakdown

## Architecture Rules

- **gRPC only**: No HTTP endpoints (Envoy handles transcoding)
- **No direct service imports**: Use gRPC clients only
- **Decimal for money**: No float for financial calculations
- **Type hints required**: All public functions
- **80%+ test coverage**: Required for all code

## Related Services

- **Market Regime Service** (Port 50051): Layer 1 - Market regime classification
- **Classification Service** (Port 50054): Layer 2 - Sector/theme filtering
- **Market Data Service** (Port 50053): OHLCV data provider

## Documentation

- Worker Prompt: `docs/internal/prompts/phase1/task4/task-4.2-worker.md`
- Architecture: `docs/architecture/06-classification.md` (Stage 3)
- Caching Strategy: `docs/architecture/08-caching-layers.md` (Layer 3)
