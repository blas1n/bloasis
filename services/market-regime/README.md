# Market Regime Service

BLOASIS Tier 1 service for market regime classification using FinGPT AI analysis.

## Overview

The Market Regime Service classifies current market conditions into one of six regimes:

- **crisis**: High volatility, risk-off (VIX > 30, major drawdowns)
- **normal_bear**: Declining market, moderate volatility
- **normal_bull**: Rising market, low-moderate volatility
- **euphoria**: Extreme optimism, potential bubble conditions
- **high_volatility**: Elevated VIX without clear direction
- **low_volatility**: Unusually calm markets, potential complacency

This is a **Tier 1 shared service**, meaning:
- Results are cached for 6 hours
- Shared across all users (not personalized)
- Reduces FinGPT API costs by 93%

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Market Regime Service                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │    gRPC      │  │   gRPC       │  │  RegimeClassifier    │  │
│  │  :50051      │  │ Health Check │  │  (FinGPT wrapper)    │  │
│  │              │  │ grpc.health  │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                           │                     │               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │    Redis     │  │   Redpanda   │  │     PostgreSQL       │  │
│  │  (Cache)     │  │  (Events)    │  │   (Persistence)      │  │
│  │  6hr TTL     │  │ regime-change│  │ market_data schema   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Note**: This service exposes only gRPC. Kong Gateway handles HTTP-to-gRPC transcoding for external REST API access.

## API Endpoints

### gRPC Service (Port 50051)

```protobuf
service MarketRegimeService {
  // Get current market regime classification
  rpc GetCurrentRegime(GetCurrentRegimeRequest) returns (GetCurrentRegimeResponse);

  // Get historical regime classifications
  rpc GetRegimeHistory(GetRegimeHistoryRequest) returns (GetRegimeHistoryResponse);
}
```

### gRPC Health Check

The service implements the standard gRPC Health Checking Protocol (`grpc.health.v1.Health`):

```bash
# Using grpcurl to check health
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Check specific service
grpcurl -plaintext -d '{"service": "bloasis.market_regime.MarketRegimeService"}' \
  localhost:50051 grpc.health.v1.Health/Check
```

### REST via Kong Gateway

Kong automatically transcodes gRPC to REST:

```bash
# Get current regime
GET /v1/market-regime/current

# Get regime history
GET /v1/market-regime/history?time_range.start_date=2025-01-25T00:00:00Z&time_range.end_date=2025-01-26T23:59:59Z
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | market-regime | Service identifier |
| `GRPC_PORT` | 50051 | gRPC server port |
| `REDIS_HOST` | redis | Redis server hostname |
| `REDIS_PORT` | 6379 | Redis server port |
| `REDPANDA_BROKERS` | redpanda:9092 | Redpanda broker addresses |
| `DATABASE_URL` | - | PostgreSQL connection URL |
| `FINGPT_API_KEY` | - | FinGPT API key (required for production) |
| `LOG_LEVEL` | INFO | Logging level |

## Running Locally

### Prerequisites

- Python 3.11+
- Redis
- Redpanda (or Kafka)
- PostgreSQL with TimescaleDB

### Setup

```bash
# Navigate to service directory
cd services/market-regime

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your configuration

# Run the service
python -m src.main
```

### Running with Docker

```bash
# Build image
docker build -t bloasis/market-regime:latest .

# Run container
docker run -p 50051:50051 \
  --env-file .env \
  bloasis/market-regime:latest
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run with coverage threshold (80% required)
pytest tests/ --cov=src --cov-fail-under=80

# Run only unit tests
pytest tests/test_service.py -v

# Run only integration tests
pytest tests/test_integration.py -v
```

## Event Publishing

The service publishes events to the `regime-change` Redpanda topic:

```json
{
  "event_type": "regime_classified",
  "regime": "normal_bull",
  "confidence": 0.92,
  "timestamp": "2025-01-26T14:30:00Z",
  "trigger": "baseline"
}
```

## Database Schema

Requires the `market_data.market_regimes` table:

```sql
CREATE SCHEMA IF NOT EXISTS market_data;

CREATE TABLE market_data.market_regimes (
    id SERIAL PRIMARY KEY,
    regime VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    trigger VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_market_regimes_timestamp
ON market_data.market_regimes(timestamp);
```

## Development Guidelines

1. **Type hints required** on all public functions
2. **Decimal for money** - never use float for financial calculations
3. **Tests required** - minimum 80% coverage
4. **gRPC for internal communication** - no HTTP between services
5. **Redpanda for events** - not Redis Pub/Sub
6. **gRPC-only exposure** - no HTTP endpoints, Kong handles REST transcoding

## Related Services

- **Sector Strategy Service** (Tier 2) - Uses regime data for sector allocation
- **AI Analysis Service** - Consumes regime-change events
- **Notification Service** - Broadcasts regime changes to clients

## Troubleshooting

### Service won't start

1. Check Redis connection: `redis-cli ping`
2. Check Redpanda: `rpk cluster health`
3. Check PostgreSQL: `psql -c "SELECT 1"`
4. Verify environment variables in `.env`

### Cache not working

1. Verify `REDIS_HOST` and `REDIS_PORT`
2. Check Redis logs for connection issues
3. Manually test: `redis-cli GET market:regime:current`

### Events not publishing

1. Verify `REDPANDA_BROKERS` configuration
2. Check topic exists: `rpk topic list`
3. Check Redpanda logs for producer errors

### Health check failing

1. Use grpcurl to check health status:
   ```bash
   grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
   ```
2. Check service logs for initialization errors
3. Verify all dependencies (Redis, Redpanda, PostgreSQL) are accessible
