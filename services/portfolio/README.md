# Portfolio Service

BLOASIS user portfolio and position management service.

## Overview

The Portfolio Service provides user-specific portfolio data including:

- **Portfolio Summary**: Total value, cash balance, invested value, and returns
- **Position Details**: Individual stock positions with cost basis and P&L
- **P&L Tracking**: Realized/unrealized P&L, daily P&L
- **Alpaca Sync**: Synchronize positions with Alpaca paper trading account
- **Trade Recording**: Automatic trade recording via order-filled events from Executor

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
|  |  :50057        |  | Health Check   |  |  TradeRepository       |  |
|  |                |  | grpc.health    |  |  (SQLAlchemy ORM)      |  |
|  +----------------+  +----------------+  +------------------------+  |
|                           |                     |                    |
|  +----------------+  +----------------+  +------------------------+  |
|  |    Redis       |  |   PostgreSQL   |  |  Executor Client       |  |
|  |  (Cache)       |  |  (Persistence) |  |  (gRPC → Executor)     |  |
|  |  1hr TTL       |  |  portfolios    |  |  positions + account   |  |
|  +----------------+  |  positions     |  +------------------------+  |
|                      |  trades        |                              |
|  +----------------+  +----------------+  +------------------------+  |
|  |  Redpanda      |                     |  Market Data Client     |  |
|  |  Consumer       |                     |  (gRPC → Market Data)   |  |
|  |  order-filled  |                     |  current prices          |  |
|  +----------------+                     +------------------------+  |
+---------------------------------------------------------------------+
```

**Note**: This service exposes only gRPC. Envoy Gateway handles HTTP-to-gRPC transcoding for external REST API access.

## API Endpoints

### gRPC Service (Port 50057)

```protobuf
service PortfolioService {
  // Read Operations (REST via Envoy)
  rpc GetPortfolio(GetPortfolioRequest) returns (GetPortfolioResponse);
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse);
  rpc GetPortfolioSummary(GetPortfolioSummaryRequest) returns (GetPortfolioSummaryResponse);
  rpc GetTradeHistory(GetTradeHistoryRequest) returns (GetTradeHistoryResponse);

  // Alpaca Sync (REST via Envoy)
  rpc SyncWithAlpaca(SyncWithAlpacaRequest) returns (SyncWithAlpacaResponse);

  // Trade Recording (internal only - called by event consumer)
  rpc RecordTrade(RecordTradeRequest) returns (RecordTradeResponse);

  // Write Operations (internal only - used by other services)
  rpc UpdateCashBalance(UpdateCashBalanceRequest) returns (UpdateCashBalanceResponse);
  rpc CreatePosition(CreatePositionRequest) returns (CreatePositionResponse);
  rpc UpdatePosition(UpdatePositionRequest) returns (UpdatePositionResponse);
  rpc DeletePosition(DeletePositionRequest) returns (DeletePositionResponse);
}
```

### REST via Envoy Gateway

```bash
GET  /v1/portfolio/{user_id}              # Get portfolio summary
GET  /v1/portfolio/{user_id}/positions    # Get all positions
GET  /v1/portfolio/{user_id}/summary      # Get detailed P&L summary
GET  /v1/portfolio/{user_id}/trades       # Get trade history
POST /v1/portfolio/{user_id}/sync         # Sync with Alpaca
```

**Note**: Write operations (UpdateCashBalance, CreatePosition, etc.) and RecordTrade are internal-only gRPC.

## Alpaca Sync

The `SyncWithAlpaca` RPC synchronizes local portfolio data with Alpaca:

1. Calls **Executor Service** `GetPositions` to get current Alpaca positions
2. Calls **Executor Service** `GetAccount` to get cash balance
3. Upserts positions into the local database
4. Deletes stale positions (in DB but no longer in Alpaca)
5. Updates cash balance
6. Invalidates Redis cache

```
Frontend "Sync" button → POST /v1/portfolio/{userId}/sync
  → Portfolio.SyncWithAlpaca
    → Executor.GetPositions → Alpaca SDK
    → Executor.GetAccount → Alpaca SDK
    → DB sync (positions + cash) + cache invalidation
  ← { success: true, positions_synced: N }
```

## Event-Driven Trade Recording

The service consumes `order-filled` events from Redpanda (published by Executor Service):

- **Topic**: `order-filled`
- **Consumer Group**: `portfolio-service`
- **Idempotent**: Checks `trade_repository.get_trade_by_order_id()` before processing
- **Actions**: Records trade, updates position, calculates realized P&L for sell trades

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | portfolio | Service identifier |
| `GRPC_PORT` | 50057 | gRPC server port |
| `REDIS_HOST` | redis | Redis server hostname |
| `REDIS_PORT` | 6379 | Redis server port |
| `DATABASE_URL` | - | PostgreSQL connection URL |
| `REDPANDA_BROKERS` | redpanda:9092 | Redpanda broker addresses |
| `EXECUTOR_HOST` | executor | Executor Service host |
| `EXECUTOR_PORT` | 50060 | Executor Service port |
| `CACHE_TTL` | 3600 | Cache TTL in seconds (1 hour) |
| `LOG_LEVEL` | INFO | Logging level |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run with coverage threshold (80% required)
pytest tests/ --cov=src --cov-fail-under=80
```

## Related Services

- **Executor Service** - Provides Alpaca positions/account via gRPC; publishes order-filled events
- **Market Data Service** - Provides current market prices for position valuation
- **Market Regime Service** (Tier 1) - Provides market context

## Troubleshooting

### Service won't start

1. Check Redis connection: `redis-cli ping`
2. Check PostgreSQL: `psql -c "SELECT 1"`
3. Verify environment variables in `.env`

### Portfolio always shows $0

1. Verify Alpaca keys are configured (Settings page or env vars)
2. Click "Sync with Alpaca" on the Portfolio page
3. Check Executor Service is running: `grpcurl -plaintext localhost:50060 grpc.health.v1.Health/Check`

### Health check failing

1. Use grpcurl to check health status:
   ```bash
   grpcurl -plaintext localhost:50057 grpc.health.v1.Health/Check
   ```
2. Check service logs for initialization errors
3. Verify all dependencies (Redis, PostgreSQL, Executor) are accessible
