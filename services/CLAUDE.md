# Services Implementation Guide

Practical guide for implementing microservices in BLOASIS.

---

## Service Structure Standard

Each service follows this structure:

```
services/<service-name>/
├── src/
│   ├── __init__.py
│   ├── main.py           # gRPC server only (no HTTP)
│   ├── service.py        # gRPC Servicer implementation
│   ├── config.py         # Pydantic-based configuration
│   ├── models.py         # Business logic
│   └── clients/          # External API clients
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_*.py
├── pyproject.toml        # Dependencies managed here (uv)
├── .env.example
└── README.md
```

**What NOT to include:**
- Dockerfile (managed at root level)
- requirements.txt (use pyproject.toml + uv only)
- proto symlink (access via PYTHONPATH)
- shared code copies
- FastAPI or HTTP endpoints (Kong handles HTTP-to-gRPC transcoding)

---

## Import Rules

PYTHONPATH is set to `/workspace`, so:

```python
# Correct
from shared.generated import market_regime_pb2
from shared.utils import PostgresClient, setup_logger

# Wrong (sys.path manipulation forbidden)
import sys
sys.path.insert(0, ...)
```

---

## Environment Configuration (config.py)

All services MUST include a Pydantic-based configuration class in `src/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class ServiceConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity (no http_port - Kong handles HTTP)
    service_name: str = "market-regime"
    grpc_port: int = 50051

    # Infrastructure
    redis_host: str = "localhost"
    redis_port: int = 6379
    redpanda_brokers: str = "localhost:9092"
    database_url: str = ""

    # Optional API keys
    fingpt_api_key: str = ""
```

**Note**: Services expose only gRPC. Kong Gateway handles HTTP-to-gRPC transcoding.

---

## Creating a New Service

### 1. Service Setup

```bash
# Create service directory
mkdir -p services/market-regime/{src,tests}
cd services/market-regime

# Create base files
touch src/__init__.py src/main.py src/service.py src/config.py src/models.py
touch tests/__init__.py tests/conftest.py tests/test_service.py
touch pyproject.toml .env.example README.md
```

### 2. Proto Definition (shared/proto/)

```protobuf
// shared/proto/market_regime.proto
syntax = "proto3";
package bloasis.market_regime;

import "google/api/annotations.proto";

service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}

message RegimeRequest {
  string user_id = 1;
}

message RegimeResponse {
  string regime = 1;          // "crisis", "bear", "bull", "sideways", "recovery"
  double confidence = 2;       // 0.0 - 1.0
  string timestamp = 3;        // ISO 8601
}
```

### 3. Service Implementation (src/)

**src/main.py** - Server Entry Point (gRPC only):
```python
"""
Service - gRPC only.

Kong Gateway handles HTTP-to-gRPC transcoding.
"""

import asyncio
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from shared.generated import market_regime_pb2_grpc
from shared.utils import PostgresClient, RedisClient, RedpandaClient, setup_logger

from .config import config
from .service import MarketRegimeServicer

logger = setup_logger(__name__)


async def serve() -> None:
    """Start and run the gRPC server."""
    logger.info(f"Starting {config.service_name} service...")

    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()

    redpanda_client = RedpandaClient()
    await redpanda_client.start()

    postgres_client = PostgresClient()
    await postgres_client.connect()

    # Create gRPC server
    server = grpc.aio.server()

    # Add service
    servicer = MarketRegimeServicer(
        redis_client=redis_client,
        redpanda_client=redpanda_client,
        postgres_client=postgres_client,
    )
    market_regime_pb2_grpc.add_MarketRegimeServiceServicer_to_server(servicer, server)

    # Add gRPC health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.market_regime.MarketRegimeService",
        health_pb2.HealthCheckResponse.SERVING
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Start server
    listen_addr = f"[::]:{config.grpc_port}"
    server.add_insecure_port(listen_addr)
    await server.start()
    logger.info(f"gRPC server started on {listen_addr}")

    # Handle shutdown
    async def shutdown() -> None:
        logger.info("Shutting down...")
        await server.stop(grace=5)
        await postgres_client.close()
        await redpanda_client.stop()
        await redis_client.close()

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await shutdown()


def main() -> None:
    """Main entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
```

**src/service.py** - Business Logic:
```python
import grpc
from datetime import datetime
from typing import Optional

from shared.proto import market_regime_pb2, market_regime_pb2_grpc
from shared.utils.redpanda_client import RedpandaClient
from shared.utils.redis_client import RedisClient
from shared.models.risk_profile import RiskProfile
from .models import RegimeClassifier


class MarketRegimeService(market_regime_pb2_grpc.MarketRegimeServiceServicer):
    """Market Regime Service implementation."""

    def __init__(self):
        self.redpanda: Optional[RedpandaClient] = None
        self.redis: Optional[RedisClient] = None
        self.classifier: Optional[RegimeClassifier] = None

    async def initialize(self):
        """Initialize service dependencies."""
        self.redpanda = RedpandaClient()
        await self.redpanda.start()

        self.redis = RedisClient()
        await self.redis.connect()

        self.classifier = RegimeClassifier()

    async def shutdown(self):
        """Cleanup resources."""
        if self.redpanda:
            await self.redpanda.stop()
        if self.redis:
            await self.redis.close()

    async def GetCurrentRegime(
        self,
        request: market_regime_pb2.RegimeRequest,
        context: grpc.aio.ServicerContext
    ) -> market_regime_pb2.RegimeResponse:
        """Get current market regime."""
        try:
            # 1. Check cache
            cache_key = f"market:regime:current"
            cached = await self.redis.get(cache_key)
            if cached:
                return market_regime_pb2.RegimeResponse(**cached)

            # 2. Classify regime
            regime_data = await self.classifier.classify()

            # 3. Cache result (6 hours TTL)
            await self.redis.setex(cache_key, 21600, regime_data)

            # 4. Publish event
            await self.redpanda.publish('regime-change', {
                'regime': regime_data['regime'],
                'confidence': regime_data['confidence'],
                'timestamp': datetime.now().isoformat()
            })

            return market_regime_pb2.RegimeResponse(
                regime=regime_data['regime'],
                confidence=regime_data['confidence'],
                timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f'Classification error: {str(e)}')
            raise
```

**src/models.py** - Service-specific Models:
```python
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class RegimeClassifier:
    """Market regime classification logic."""

    async def classify(self) -> Dict[str, any]:
        """Classify current market regime."""
        # FinGPT integration
        # Market data analysis
        # Return regime classification
        pass
```

### 4. Environment Variables

**services/market-regime/.env.example**:
```bash
# Service config (no HTTP_PORT - Kong handles HTTP)
SERVICE_NAME=market-regime
GRPC_PORT=50051

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Redpanda
REDPANDA_BROKERS=redpanda:9092

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/bloasis

# External APIs
FINGPT_API_KEY=your_api_key_here

# Logging
LOG_LEVEL=INFO
```

**Loading environment via Pydantic**:
```python
from .config import config

# Access configuration - validated at import time
grpc_port = config.grpc_port
redis_host = config.redis_host
fingpt_api_key = config.fingpt_api_key
```

---

## Inter-Service Communication

### gRPC Client Usage

**src/clients/ai_analysis_client.py**:
```python
import grpc
import logging
from typing import Dict, Optional

from shared.proto import ai_analysis_pb2, ai_analysis_pb2_grpc

logger = logging.getLogger(__name__)


class AIAnalysisClient:
    """AI Analysis Service gRPC client."""

    def __init__(self, host: str = 'ai-analysis:50052'):
        self.host = host
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[ai_analysis_pb2_grpc.AIAnalysisServiceStub] = None

    async def connect(self):
        """Establish connection."""
        self.channel = grpc.aio.insecure_channel(
            self.host,
            options=[
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                ('grpc.keepalive_time_ms', 10000),
            ]
        )
        self.stub = ai_analysis_pb2_grpc.AIAnalysisServiceStub(self.channel)
        logger.info(f"Connected to AI Analysis Service at {self.host}")

    async def get_strategy(self, regime: str, symbols: list) -> Dict:
        """Get trading strategy."""
        if not self.stub:
            await self.connect()

        try:
            request = ai_analysis_pb2.StrategyRequest(
                regime=regime,
                symbols=symbols
            )
            response = await self.stub.GetStrategy(request, timeout=30.0)

            return {
                'strategy': response.strategy,
                'confidence': response.confidence
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                # Retry logic or circuit breaker
                raise ConnectionError(f"Service unavailable: {self.host}")
            raise

    async def close(self):
        """Close connection."""
        if self.channel:
            await self.channel.close()
            logger.info("AI Analysis client closed")
```

**Usage in service**:
```python
class MarketRegimeService:
    def __init__(self):
        self.ai_client = AIAnalysisClient()

    async def initialize(self):
        await self.ai_client.connect()

    async def shutdown(self):
        await self.ai_client.close()

    async def analyze(self, regime: str):
        strategy = await self.ai_client.get_strategy(regime, ['AAPL'])
        return strategy
```

---

## Redpanda Communication

### Producer (Publishing Events)

```python
from shared.utils.redpanda_client import RedpandaClient
import json
from datetime import datetime

class MarketRegimeService:
    async def publish_regime_change(self, regime: dict):
        """Publish regime change event."""
        event = {
            'regime': regime['regime'],
            'confidence': regime['confidence'],
            'timestamp': datetime.now().isoformat(),
            'source': 'market-regime-service'
        }

        await self.redpanda.publish('regime-change', event)
```

### Consumer (Receiving Events)

**Only for Notification Service (Phase 2)**:
```python
from shared.utils.redpanda_client import RedpandaClient

class NotificationService:
    async def start_consumer(self):
        """Start consuming events."""
        consumer = await self.redpanda.create_consumer(
            topics=['regime-change', 'order-filled'],
            group_id='notification-service'
        )

        async for message in consumer:
            topic = message.topic
            data = message.value

            if topic == 'regime-change':
                await self.broadcast_all(data)
            elif topic == 'order-filled':
                await self.send_to_user(data['user_id'], data)
```

---

## Redis Caching

### Basic Pattern

```python
from shared.utils.redis_client import RedisClient
import json

class MarketRegimeService:
    async def get_with_cache(self, key: str, fetch_func, ttl: int = 3600):
        """Get data with Redis caching."""
        # 1. Try cache
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)

        # 2. Fetch from source
        data = await fetch_func()

        # 3. Cache result
        await self.redis.setex(key, ttl, json.dumps(data))

        return data
```

### Tier 1-2 Shared Caching

```python
# Market Regime (shared across all users)
cache_key = "market:regime:current"
ttl = 21600  # 6 hours

# Sector Strategies (shared across all users)
cache_key = f"sector:strategies:{sector}"
ttl = 21600  # 6 hours

# User-specific
cache_key = f"user:{user_id}:portfolio"
ttl = 3600  # 1 hour
```

---

## Database Connection

### PostgreSQL/TimescaleDB

**shared/utils/postgres_client.py**:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql+asyncpg://user:pass@localhost/bloasis'
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=0,
    echo=False
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session
```

**Usage**:
```python
from shared.utils.postgres_client import get_session
from sqlalchemy import select
from shared.models.user import User

class PortfolioService:
    async def get_user_portfolio(self, user_id: str):
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            return user
```

---

## Logging

### Structured Logging

**shared/utils/logging.py**:
```python
import logging
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """JSON structured logging."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'service': record.name,
            'message': record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms

        return json.dumps(log_data)


def setup_logging():
    """Setup structured logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler]
    )
```

**Usage**:
```python
import logging

logger = logging.getLogger(__name__)

# Simple log
logger.info("Regime classified")

# Structured log with extras
logger.info("Strategy generated", extra={
    'user_id': user_id,
    'regime': regime,
    'duration_ms': 1500
})
```

---

## Graceful Shutdown

```python
import signal
import asyncio

class MarketRegimeService:
    def __init__(self):
        self.shutdown_event = asyncio.Event()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutdown initiated")

        # 1. Stop accepting new requests
        self.shutdown_event.set()

        # 2. Wait for ongoing requests (with timeout)
        await asyncio.sleep(5)

        # 3. Close connections
        await self.redpanda.stop()
        await self.redis.close()

        logger.info("Shutdown complete")


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal."""
    logger.info("SIGTERM received")
    # Trigger shutdown
    asyncio.create_task(service.shutdown())


# Register signal handler
signal.signal(signal.SIGTERM, handle_sigterm)
```

---

## Service Deployment Checklist

### Before Implementation Complete

- [ ] gRPC service implemented (src/service.py)
- [ ] Proto HTTP annotations verified
- [ ] gRPC Health Check implemented (grpc.health.v1)
- [ ] No HTTP endpoints (Kong handles HTTP-to-gRPC transcoding)
- [ ] Pydantic config.py created and validated (no http_port)
- [ ] Environment variables validated (.env.example)
- [ ] Logging configured (structured logging)
- [ ] Graceful shutdown implemented

### Testing

- [ ] Unit tests (80%+ coverage)
- [ ] Integration tests (gRPC client)
- [ ] Mock external APIs
- [ ] Error handling tested

### Deployment Ready

- [ ] Added to root docker-compose.yml
- [ ] Consul service registration
- [ ] Kong routing configured (if external)

### Operations

- [ ] Monitoring metrics exposed
- [ ] Error tracking configured
- [ ] Performance profiling
- [ ] Load testing

---

## Core Principles

1. **Initialization/Shutdown**: All external connections managed in initialize()/shutdown()
2. **Error Propagation**: Explicitly handle gRPC errors
3. **Logging**: Use structured logging (JSON)
4. **Caching**: Leverage Redis aggressively (Tier 1-2 shared)
5. **Events**: Publish events via Redpanda (decoupling)
6. **Type Safety**: Type hints required
7. **Testing**: Use mocks, 80%+ coverage

---

**Reference Documents**:
- `.claude/skills/grpc-implementation.md`: gRPC patterns
- `.claude/skills/code-guidelines.md`: Coding style
- `.claude/skills/testing-standards.md`: Testing guide
