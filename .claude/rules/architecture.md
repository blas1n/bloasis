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
- Data models → `shared/models/`
- Utilities → `shared/utils/`

**NEVER duplicate code between services.**

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

**Why**: Kong requires them for gRPC-to-REST transcoding.

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
