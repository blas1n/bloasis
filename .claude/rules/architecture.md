---
always: true
---

# Architecture Rules

## CRITICAL: Core Architectural Decisions

These decisions are final. Do NOT deviate without explicit approval.

### 1. Redpanda for Messaging (Phase 1)

**ALWAYS use Redpanda, NOT Redis Pub/Sub or RabbitMQ.**

**Why**: Message durability, offset management, no migration needed in Phase 2.

```python
# Correct
from aiokafka import AIOKafkaProducer
producer = AIOKafkaProducer(bootstrap_servers='redpanda:9092')

# Wrong - Do NOT use
import redis
redis_client.publish('channel', message)  # NO!
```

### 2. Python-Only Backend (Phase 1)

**All backend services MUST be Python 3.11+.**

**No TypeScript, Go, or Java in Phase 1.**

**Why**: AI/ML focus (80% of project), single language stack.

### 3. Type Hints Required

**ALL public functions MUST have type hints.**

```python
# Correct
async def get_regime(user_id: str) -> Dict[str, any]:
    pass

# Wrong
async def get_regime(user_id):  # NO!
    pass
```

### 4. Shared Code Location

**Cross-service code goes in `shared/`:**

- `.proto` files → `shared/proto/`
- Data models → Each service's `src/models.py` (MSA independence)
- Utilities → `shared/utils/`

**NEVER share models between services:**

- Sharing models increases coupling between services
- Each service maintains its own Pydantic/SQLAlchemy models
- Services communicate via gRPC proto messages only
- This preserves service independence and allows independent deployment

**NEVER duplicate code between services** (except models).

### 5. Service Independence

Services MUST communicate ONLY via:
- gRPC (request-response)
- Redpanda (events)

**No direct imports between services:**

```python
# Wrong
from services.market_regime.src.service import MarketRegimeService  # NO!

# Correct
from .clients.market_regime_client import MarketRegimeClient
regime = await client.get_current_regime()
```

### 6. Decimal for Money

**NEVER use float for financial calculations.**

```python
# Correct
from decimal import Decimal
price = Decimal('150.25')
quantity = Decimal('10')

# Wrong
price = 150.25  # NO! Float precision issues
```

### 7. Tier 1-2 Shared Caching

**Market Regime and Sector Strategies are shared across ALL users.**

```python
# Correct (shared)
cache_key = "market:regime:current"  # All users
ttl = 21600  # 6 hours

# Correct (user-specific)
cache_key = f"user:{user_id}:portfolio"  # Per-user
```

### 8. Proto HTTP Annotations

**ALL .proto services MUST have HTTP annotations.**

**Why**: Envoy Gateway requires them for gRPC-to-REST transcoding.

```protobuf
// Correct
service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}

// Wrong - missing annotations
service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse);  // NO!
}
```

### 8.1. gRPC-Only Services

**Services MUST expose gRPC only. NO HTTP endpoints.**

**Why**: Envoy Gateway handles HTTP-to-gRPC transcoding. Services don't need HTTP.

```python
# Correct - gRPC only with gRPC Health Check
import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

server = grpc.aio.server()
market_regime_pb2_grpc.add_MarketRegimeServiceServicer_to_server(servicer, server)

# Add gRPC health check
health_servicer = health.HealthServicer()
health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

# Wrong - Do NOT use FastAPI/HTTP
from fastapi import FastAPI
app = FastAPI()  # NO!

@app.get("/health")  # NO! Use gRPC health check instead
async def health():
    return {"status": "healthy"}
```

**Health checks use gRPC Health Checking Protocol (grpc.health.v1)**:
- Kubernetes/Docker can use `grpc_health_probe`
- No HTTP /health or /ready endpoints needed

### 9. Python Path Configuration

**NEVER use sys.path.insert() for imports.**

**ALWAYS use PYTHONPATH environment variable or editable install.**

Why: sys.path manipulation breaks depending on execution location, and IDE auto-completion becomes unstable.

```python
# Wrong - sys.path manipulation (NO!)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

# Correct - PYTHONPATH is already set
from shared.generated import market_regime_pb2
from shared.utils import PostgresClient
```

**PYTHONPATH configuration locations:**
- Development: `.devcontainer/Dockerfile` or `devcontainer.json`
- Testing: `pyproject.toml` `[tool.pytest.ini_options]`
- Production: During Docker image build

### 10. Dockerfile Management

**NEVER create service-level Dockerfiles.**

**Docker configuration is managed at root level only:**
- `.devcontainer/docker-compose.yml` (development)
- `docker-compose.yml` (production, to be added)

Why: Centralized management ensures consistency, optimizes build context.

### 10.1. Dependency Management

**NEVER create requirements.txt in services.**

**Use pyproject.toml + uv only:**

```toml
# services/market-regime/pyproject.toml
[project]
dependencies = [
    "fastapi>=0.100.0",
    "grpcio>=1.60.0",
    "pydantic-settings>=2.0.0",
]
```

Why: Single source of truth for dependencies, uv is faster and more reliable.

### 11. Environment Variable Validation

**ALWAYS validate required environment variables at startup.**

```python
# Correct - Pydantic-based validation
from pydantic_settings import BaseSettings

class ServiceConfig(BaseSettings):
    service_name: str
    grpc_port: int = 50051
    redis_host: str
    database_url: str

    class Config:
        env_file = ".env"

config = ServiceConfig()  # Auto-validation at startup
```

### 12. Proto Generated Files Management

**NEVER commit generated proto files to git.**

**Proto generated files are auto-generated at build time:**
- `shared/generated/` directory is included in `.gitignore`
- CI/CD runs `buf generate`
- Local development runs `make proto-generate`

```gitignore
# .gitignore
shared/generated/
```

## Verification Checklist

Before implementing ANY service:
- [ ] Uses Redpanda (not Redis Pub/Sub)
- [ ] Python 3.11+ (not other languages)
- [ ] Type hints on all functions
- [ ] Shared code in `shared/`
- [ ] No direct service imports
- [ ] Decimal for money
- [ ] Proto HTTP annotations
- [ ] Follows Tier 1-2 caching strategy
- [ ] No sys.path.insert() (use PYTHONPATH)
- [ ] No service-level Dockerfile
- [ ] No requirements.txt (use pyproject.toml + uv)
- [ ] Pydantic config.py for env validation (no http_port)
- [ ] gRPC-only (no FastAPI/HTTP endpoints)
- [ ] gRPC Health Check implemented (grpc.health.v1)
- [ ] Proto generated files not committed

### 13. Git Commit Rules

**NEVER include Co-Authored-By in commit messages.**

Commit message format:
```
type(scope): short description

- bullet points for details
- no Co-Authored-By line
```

Example:
```bash
git commit -m "feat(market-data): add OHLCV caching

- Add Redis caching with 5min TTL
- Implement cache invalidation on sync"
```
