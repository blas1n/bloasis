# Market Data Service Integration Tests

## Prerequisites

1. Docker Compose environment running
2. Market Data Service registered with Consul
3. Kong Gateway configured
4. TimescaleDB running
5. Redis running

## Running Tests

### All Market Data Tests

```bash
pytest tests/integration/test_market_data*.py -v
```

### E2E Tests Only

```bash
pytest tests/integration/test_market_data_e2e.py -v
```

### Database Tests Only

```bash
pytest tests/integration/test_market_data_db.py -v
```

### Cache Tests Only

```bash
pytest tests/integration/test_market_data_cache.py -v
```

## Test Categories

- **E2E Tests** (`test_market_data_e2e.py`): Full gRPC flow testing
  - GetOHLCV, GetStockInfo, GetBatchOHLCV
  - SyncSymbol, ListSymbols
  - Health checks
  - Caching behavior

- **Database Tests** (`test_market_data_db.py`): TimescaleDB operations
  - Schema verification
  - OHLCV insert/upsert
  - Time-range queries
  - Stock info persistence

- **Cache Tests** (`test_market_data_cache.py`): Redis caching
  - Set/Get operations
  - TTL expiration
  - Key format consistency
  - Cache invalidation

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKET_DATA_HOST` | `market-data` | Market Data service hostname |
| `MARKET_DATA_GRPC_PORT` | `50053` | Market Data gRPC port |
| `CONSUL_HOST` | `consul` | Consul hostname |
| `CONSUL_PORT` | `8500` | Consul HTTP port |
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/bloasis` | PostgreSQL connection |

## Test Behavior

- Tests skip gracefully when services are unavailable
- Tests are idempotent (can run multiple times)
- Tests clean up any test data created
- Tests use proper timeouts to avoid hanging

## Troubleshooting

### Service Not Available

If tests skip with "Market Data gRPC service not available":

1. Check if the service is running: `docker ps | grep market-data`
2. Check Consul registration: `curl http://localhost:8500/v1/agent/services`
3. Check service logs: `docker logs market-data`

### Database Tests Failing

If database tests fail:

1. Check PostgreSQL is running: `docker ps | grep postgres`
2. Verify schema exists: Connect to DB and check `market_data` schema
3. Run migrations if needed: `alembic upgrade head`

### Cache Tests Failing

If cache tests fail:

1. Check Redis is running: `docker ps | grep redis`
2. Verify connectivity: `redis-cli -h redis ping`
