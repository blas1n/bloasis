# Portfolio Service

BLOASIS user portfolio and position management service.

## Overview

The Portfolio Service provides user-specific portfolio data including:

- **Portfolio Summary**: Total value, cash balance, invested value, and returns
- **Position Details**: Individual stock positions with cost basis and P&L

This is a **user-specific service** (not Tier 1 shared), meaning:
- Results are cached for 1 hour per user
- Data is personalized to each user
- Cache key format: `user:{user_id}:portfolio`

## Architecture

```
+---------------------------------------------------------------------+
|                       Portfolio Service                              |
+---------------------------------------------------------------------+
|  +----------------+  +----------------+  +------------------------+  |
|  |    gRPC        |  |   gRPC         |  |  PortfolioRepository   |  |
|  |  :50057        |  | Health Check   |  |  (SQLAlchemy ORM)      |  |
|  |                |  | grpc.health    |  |                        |  |
|  +----------------+  +----------------+  +------------------------+  |
|                           |                     |                    |
|  +----------------+  +----------------+  +------------------------+  |
|  |    Redis       |  |   PostgreSQL   |  |                        |  |
|  |  (Cache)       |  |  (Persistence) |  |   trading schema       |  |
|  |  1hr TTL       |  |  portfolios    |  |   - portfolios table   |  |
|  +----------------+  |  positions     |  |   - positions table    |  |
|                      +----------------+  +------------------------+  |
+---------------------------------------------------------------------+
```

**Note**: This service exposes only gRPC. Envoy Gateway handles HTTP-to-gRPC transcoding for external REST API access.

## API Endpoints

### gRPC Service (Port 50057)

```protobuf
service PortfolioService {
  // Read Operations
  rpc GetPortfolio(GetPortfolioRequest) returns (GetPortfolioResponse);
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse);

  // Write Operations (MSA: Used by other services to modify portfolio)
  rpc UpdateCashBalance(UpdateCashBalanceRequest) returns (UpdateCashBalanceResponse);
  rpc CreatePosition(CreatePositionRequest) returns (CreatePositionResponse);
  rpc UpdatePosition(UpdatePositionRequest) returns (UpdatePositionResponse);
  rpc DeletePosition(DeletePositionRequest) returns (DeletePositionResponse);
}
```

### gRPC Health Check

The service implements the standard gRPC Health Checking Protocol (`grpc.health.v1.Health`):

```bash
# Using grpcurl to check health
grpcurl -plaintext localhost:50057 grpc.health.v1.Health/Check

# Check specific service
grpcurl -plaintext -d '{"service": "bloasis.portfolio.PortfolioService"}' \
  localhost:50057 grpc.health.v1.Health/Check
```

### REST via Envoy Gateway (Read Operations Only)

Envoy Gateway automatically transcodes gRPC to REST for **read operations only**:

```bash
GET /v1/portfolio/{user_id}                    # Get portfolio summary
GET /v1/portfolio/{user_id}/positions          # Get all positions
```

**Note**: Write operations (UpdateCashBalance, CreatePosition, UpdatePosition, DeletePosition) are internal-only and not exposed via REST. Other backend services must call them directly via gRPC.

## Response Examples

### GetPortfolio Response

```json
{
  "user_id": "user123",
  "total_value": { "amount": "100000.00", "currency": "USD" },
  "cash_balance": { "amount": "25000.00", "currency": "USD" },
  "invested_value": { "amount": "75000.00", "currency": "USD" },
  "total_return": 15.5,
  "total_return_amount": { "amount": "10000.00", "currency": "USD" },
  "timestamp": "2025-01-26T14:30:00Z"
}
```

### GetPositions Response

```json
{
  "user_id": "user123",
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "avg_cost": { "amount": "150.00", "currency": "USD" },
      "current_price": { "amount": "175.00", "currency": "USD" },
      "current_value": { "amount": "17500.00", "currency": "USD" },
      "unrealized_pnl": { "amount": "2500.00", "currency": "USD" },
      "unrealized_pnl_percent": 16.67
    }
  ],
  "timestamp": "2025-01-26T14:30:00Z"
}
```

### UpdateCashBalance Request/Response

**Request:**
```json
{
  "user_id": "user123",
  "amount": { "amount": "5000.00", "currency": "USD" },
  "operation": "delta"  // "set" for absolute, "delta" for relative change
}
```

**Response:**
```json
{
  "success": true,
  "new_balance": { "amount": "30000.00", "currency": "USD" },
  "timestamp": "2025-01-26T14:35:00Z"
}
```

### CreatePosition Request/Response

**Request:**
```json
{
  "user_id": "user123",
  "symbol": "GOOGL",
  "quantity": 50,
  "cost_per_share": { "amount": "2500.00", "currency": "USD" },
  "currency": "USD"
}
```

**Response:**
```json
{
  "success": true,
  "position": {
    "symbol": "GOOGL",
    "quantity": 50,
    "avg_cost": { "amount": "2500.00", "currency": "USD" },
    "current_price": { "amount": "2500.00", "currency": "USD" },
    "current_value": { "amount": "125000.00", "currency": "USD" },
    "unrealized_pnl": { "amount": "0.00", "currency": "USD" },
    "unrealized_pnl_percent": 0.0
  },
  "timestamp": "2025-01-26T14:35:00Z"
}
```

### UpdatePosition Request/Response

**Request (adding shares):**
```json
{
  "user_id": "user123",
  "symbol": "AAPL",
  "quantity_delta": 50,
  "cost_per_share": { "amount": "180.00", "currency": "USD" },
  "current_price": { "amount": "185.00", "currency": "USD" }
}
```

**Request (reducing shares):**
```json
{
  "user_id": "user123",
  "symbol": "AAPL",
  "quantity_delta": -30,
  "current_price": { "amount": "185.00", "currency": "USD" }
}
```

**Response:**
```json
{
  "success": true,
  "position": {
    "symbol": "AAPL",
    "quantity": 150,
    "avg_cost": { "amount": "160.00", "currency": "USD" },
    "current_price": { "amount": "185.00", "currency": "USD" },
    "current_value": { "amount": "27750.00", "currency": "USD" },
    "unrealized_pnl": { "amount": "3750.00", "currency": "USD" },
    "unrealized_pnl_percent": 15.625
  },
  "timestamp": "2025-01-26T14:35:00Z"
}
```

### DeletePosition Request/Response

**Request:**
```json
{
  "user_id": "user123",
  "symbol": "AAPL"
}
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2025-01-26T14:35:00Z"
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | portfolio | Service identifier |
| `GRPC_PORT` | 50057 | gRPC server port |
| `REDIS_HOST` | redis | Redis server hostname |
| `REDIS_PORT` | 6379 | Redis server port |
| `DATABASE_URL` | - | PostgreSQL connection URL |
| `CACHE_TTL` | 3600 | Cache TTL in seconds (1 hour) |
| `LOG_LEVEL` | INFO | Logging level |

## Running Locally

### Prerequisites

- Python 3.11+
- Redis
- PostgreSQL with TimescaleDB

### Setup

```bash
# Navigate to service directory
cd services/portfolio

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

# Run only repository tests
pytest tests/test_repository.py -v

# Run only integration tests
pytest tests/test_integration.py -v
```

## Database Schema

Requires the `trading` schema with `portfolios` and `positions` tables:

```sql
CREATE SCHEMA IF NOT EXISTS trading;

CREATE TABLE trading.portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL UNIQUE,
    cash_balance NUMERIC(20, 8) NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolios_user_id ON trading.portfolios(user_id);

CREATE TABLE trading.positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_cost NUMERIC(20, 8) NOT NULL,
    current_price NUMERIC(20, 8) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_positions_user_id ON trading.positions(user_id);
CREATE INDEX idx_positions_symbol ON trading.positions(symbol);
```

## Caching Strategy

This service uses user-specific caching:

```python
# Cache keys (user-specific)
portfolio_key = f"user:{user_id}:portfolio"
positions_key = f"user:{user_id}:positions"

# TTL: 1 hour
cache_ttl = 3600
```

### Cache Invalidation

All write operations (UpdateCashBalance, CreatePosition, UpdatePosition, DeletePosition) automatically invalidate the user's cache:

```python
# After any write operation:
await redis.delete(f"user:{user_id}:portfolio")
await redis.delete(f"user:{user_id}:positions")
```

This ensures that subsequent read operations fetch fresh data from the database.

## Financial Precision

All monetary values use `Decimal` for precision:

```python
from decimal import Decimal

# Correct
price = Decimal("150.25")
quantity = Decimal("10")
total = price * quantity  # Exact result

# Proto Money type uses string for precision
message Money {
  string amount = 1;  // "150.25", not 150.25
  string currency = 2;
}
```

## Development Guidelines

1. **Type hints required** on all public functions
2. **Decimal for money** - never use float for financial calculations
3. **Tests required** - minimum 80% coverage
4. **gRPC for internal communication** - no HTTP between services
5. **gRPC-only exposure** - no HTTP endpoints, Envoy handles REST transcoding

## MSA Integration

This service follows the MSA principle that each service is responsible for its own data. Other services must use the Portfolio Service's gRPC APIs to modify portfolio data.

### Write Operations for Other Services

```python
# Example: Order Service updating portfolio after trade execution

# 1. Deduct cash for purchase
await portfolio_stub.UpdateCashBalance(
    UpdateCashBalanceRequest(
        user_id="user123",
        amount=Money(amount="-15000.00", currency="USD"),
        operation="delta"
    )
)

# 2. Create or update position
await portfolio_stub.CreatePosition(
    CreatePositionRequest(
        user_id="user123",
        symbol="AAPL",
        quantity=100,
        cost_per_share=Money(amount="150.00", currency="USD")
    )
)
```

### Average Cost Calculation

When adding shares to an existing position:
```python
new_avg_cost = ((old_quantity * old_avg_cost) + (added_quantity * cost_per_share)) / new_quantity
```

When reducing shares, avg_cost remains unchanged.

## Related Services

- **Market Regime Service** (Tier 1) - Provides market context
- **AI Analysis Service** - Uses portfolio data for personalized recommendations
- **Order Service** - Uses write operations to update positions after trades

## Troubleshooting

### Service won't start

1. Check Redis connection: `redis-cli ping`
2. Check PostgreSQL: `psql -c "SELECT 1"`
3. Verify environment variables in `.env`

### Cache not working

1. Verify `REDIS_HOST` and `REDIS_PORT`
2. Check Redis logs for connection issues
3. Manually test: `redis-cli GET user:testuser:portfolio`

### Health check failing

1. Use grpcurl to check health status:
   ```bash
   grpcurl -plaintext localhost:50057 grpc.health.v1.Health/Check
   ```
2. Check service logs for initialization errors
3. Verify all dependencies (Redis, PostgreSQL) are accessible
