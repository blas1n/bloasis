# BLOASIS Shared Package - Claude Development Guide

## Purpose

The `shared/` directory exists to prevent code duplication between services.

**Architecture Rules**:
- Absolutely no code duplication between services
- Services communicate only via gRPC or Redpanda
- Services do not directly import other services

## Directory Structure

### proto/
**gRPC Protocol Buffer Definitions**

- All .proto files for inter-service communication
- Services create symlinks to this directory: `ln -s ../../shared/proto proto`
- All .proto files must include HTTP annotations for Envoy Gateway
- Examples: market_regime.proto, ai_analysis.proto, common.proto

**Important**: .proto files must always include HTTP annotations.

```protobuf
syntax = "proto3";
import "google/api/annotations.proto";

service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}
```

### utils/
**Shared Utilities**

- **RedisClient**: Redis connection and caching utilities
- **RedpandaClient**: Kafka-compatible event publishing
- **PostgresClient**: Database connection pooling
- **Logging**: Structured JSON logging

Examples: `redis_client.py`, `redpanda_client.py`, `logging.py`

### tests/
**Unit Tests**

- Tests for shared utilities
- Must mock all external dependencies (Redis, Redpanda, PostgreSQL)
- **Minimum 80% coverage required**

## Usage Instructions

### 1. Import Proto Definitions (from service)

```python
from shared.proto import market_regime_pb2, market_regime_pb2_grpc

class MarketRegimeService(market_regime_pb2_grpc.MarketRegimeServiceServicer):
    async def GetCurrentRegime(self, request, context):
        # Implementation...
        return market_regime_pb2.RegimeResponse(regime="bull")
```

### 2. Use Proto Messages (inter-service communication)

```python
from shared.proto import market_regime_pb2, market_regime_pb2_grpc

# Communicate with other services via gRPC client
async def get_market_regime():
    # Create gRPC channel
    channel = grpc.aio.insecure_channel('market-regime-service:50051')
    stub = market_regime_pb2_grpc.MarketRegimeServiceStub(channel)

    # Create request
    request = market_regime_pb2.RegimeRequest()

    # Call service
    response = await stub.GetCurrentRegime(request)

    return response  # Returns Proto message
```

### 3. Use Shared Utilities

```python
from shared.utils.redpanda_client import RedpandaClient
from shared.utils.redis_client import RedisClient

class ClassificationService:
    def __init__(self):
        self.redpanda = RedpandaClient()
        self.redis = RedisClient()

    async def initialize(self):
        await self.redpanda.start()
        await self.redis.connect()

    async def publish_event(self, topic: str, message: dict):
        await self.redpanda.publish(topic, message)

    async def cache_data(self, key: str, value: str, ttl: int = 3600):
        await self.redis.set(key, value, ex=ttl)
```

## Development Guidelines

### Required Rules

1. **Type Hints Required**
   - All public functions must have type hints
   ```python
   async def get_data(user_id: str) -> Dict[str, Any]:
       pass
   ```

2. **Use Decimal for Financial Calculations**
   - Never use float (precision issues)
   ```python
   from decimal import Decimal

   price = Decimal('150.25')
   quantity = Decimal('10')
   total = price * quantity
   ```

3. **Tests Required**
   - Write tests before committing
   - Maintain minimum 80% coverage
   ```bash
   pytest --cov=shared --cov-fail-under=80
   ```

4. **Write Docstrings**
   - All public APIs must have docstrings
   ```python
   async def connect(self) -> None:
       """
       Connect to Redis server.

       Raises:
           ConnectionError: When connection fails
       """
       pass
   ```

### MSA Model Management

**Important**: The `shared/models/` directory does not exist.

- **Each service maintains its own Pydantic and SQLAlchemy models**
- **Inter-service communication is performed only via gRPC proto**
- **Models are not shared to prevent coupling between services**

Example:
```
services/market-regime/
├── src/
│   ├── models.py       # This service's Pydantic/SQLAlchemy models
│   └── service.py      # gRPC service implementation
```

Data exchange between services uses proto messages only:
```python
# services/market-regime/src/models.py
from pydantic import BaseModel

class MarketRegime(BaseModel):
    regime: str
    confidence: float

# services/market-regime/src/service.py
from shared.proto import market_regime_pb2

async def GetCurrentRegime(self, request, context):
    # Use internal model
    regime = MarketRegime(regime="bull", confidence=0.92)

    # Convert to Proto message and return
    return market_regime_pb2.RegimeResponse(
        regime=regime.regime,
        confidence=regime.confidence
    )
```

## Dependencies

### Installation

The project uses `uv` for dependency management.

**Install in development mode**:
```bash
cd /workspace/shared
uv pip install -e .
```

**Include development dependencies**:
```bash
uv pip install -e ".[dev]"
```

### Dependency List

See the `pyproject.toml` file:

**Production Dependencies**:
- gRPC (grpcio, grpcio-tools)
- Database (SQLAlchemy, asyncpg)
- Caching (Redis)
- Messaging (aiokafka)
- Validation (Pydantic)
- Async (aiohttp)

**Development Dependencies**:
- Testing (pytest, pytest-asyncio, pytest-cov)
- Type Checking (mypy)

## Testing

### Running Tests

```bash
# Run all tests
pytest shared/tests/

# With coverage
pytest shared/tests/ --cov=shared --cov-report=term-missing

# Require 80%+ coverage
pytest shared/tests/ --cov=shared --cov-fail-under=80
```

### Using Mocks

External dependencies must be mocked:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_redis():
    with patch('shared.utils.redis_client.RedisClient') as mock:
        mock.return_value.get = AsyncMock(return_value='cached_value')
        yield mock

@pytest.mark.asyncio
async def test_cache_get(mock_redis):
    client = RedisClient()
    result = await client.get('key')
    assert result == 'cached_value'
```

## Important Notes

### What NOT to Do

1. **Direct imports between services**
   ```python
   # Wrong
   from services.market_regime.src.service import MarketRegimeService
   ```

2. **Financial calculations with float**
   ```python
   # Wrong
   price = 150.25  # Precision issues possible
   ```

3. **Commit without tests**
   ```bash
   # Always test before committing
   pytest --cov --cov-fail-under=80
   ```

### What TO Do

1. **Inter-service communication via gRPC**
   ```python
   stub = MarketRegimeServiceStub(channel)
   response = await stub.GetCurrentRegime(request)
   ```

2. **Financial calculations with Decimal**
   ```python
   from decimal import Decimal
   price = Decimal('150.25')
   ```

3. **Write type hints and docstrings**
   ```python
   async def connect(self) -> None:
       """Connect to Redis server."""
       pass
   ```

## Reference Documents

- [Architecture Rules](../.claude/rules/architecture.md)
- [Testing Rules](../.claude/rules/testing.md)
- [gRPC Rules](../.claude/rules/grpc.md)
- [Security Rules](../.claude/rules/security.md)
