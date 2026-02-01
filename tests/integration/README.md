# Integration Tests

## Prerequisites

1. Docker Compose environment running:
   ```bash
   docker-compose up -d
   ```

2. Services running and registered with Consul:
   - Market Regime Service (port 50051)
   - Portfolio Service (port 50057)

## Running Tests

### Full Integration Suite
```bash
pytest tests/integration/ -v
```

### Consul Tests Only
```bash
pytest tests/integration/test_consul_integration.py -v
```

### Check Consul UI
Open http://localhost:8500 to see registered services and health status.

## Test Categories

### Service Registration Tests
- Verify services register with Consul
- Verify gRPC health checks configured
- Verify service tags

### Health Monitoring Tests
- Verify health checks are passing
- Verify gRPC protocol used (not HTTP)
- Verify all services healthy

### Service Discovery Tests
- Verify healthy instances can be discovered
- Verify service metadata is available
- Verify addresses are configured

## Test Behavior

### Graceful Handling of Unavailability

These tests are designed to **skip gracefully** when:
- Consul is not running
- Services are not registered with Consul

Tests will NOT fail due to infrastructure unavailability. This ensures CI/CD pipelines can run without requiring a full Docker environment.

### Idempotent Tests

All tests are idempotent:
- Tests do not modify state
- Tests can be run multiple times
- Tests do not depend on execution order

## Troubleshooting

### Services not registered
1. Check service logs for Consul connection errors
2. Verify `CONSUL_ENABLED=true` environment variable
3. Check network connectivity to Consul (port 8500)

### Health checks failing
1. Check gRPC Health Check implementation in service
2. Verify service is actually running on expected port
3. Check Consul check configuration with:
   ```bash
   curl http://localhost:8500/v1/agent/checks
   ```

## Architecture Notes

### Why gRPC Health Checks?

Per BLOASIS architecture rules:
- All internal MSA communication uses gRPC (10x faster than HTTP)
- Services implement `grpc.health.v1.Health/Check` protocol
- Consul performs native gRPC health checks, not HTTP

### Service Tags

Services register with tags for discovery:
- `grpc` - Identifies gRPC services
- Additional tags for tier/environment identification

### Health Check Configuration

Consul checks are configured with:
- gRPC endpoint: `{host}:{port}` (e.g., `market-regime:50051`)
- Interval: 10s
- Timeout: 5s
- TLS: Disabled (enable in production)
