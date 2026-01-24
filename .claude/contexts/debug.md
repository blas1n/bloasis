---
context: debug
description: Debugging mode - diagnosing and fixing issues
---

# Debug Context

You are debugging issues in BLOASIS. Systematic diagnosis is key.

## Debugging Workflow

### 1. Gather Information

**What to collect**:
- Error message (full traceback)
- Service logs
- Input that caused error
- Expected vs actual behavior

**Commands**:
```bash
# Service logs
docker-compose logs -f <service>

# Specific time range
docker-compose logs --since 30m <service>

# Follow logs
docker-compose logs -f <service> | grep ERROR
```

### 2. Reproduce Locally

**Steps**:
1. Isolate the failing component
2. Create minimal reproduction case
3. Run in debugger

**Example**:
```python
# Reproduce in test
@pytest.mark.asyncio
async def test_failing_case():
    service = MarketRegimeService()
    # Trigger the error
    result = await service.get_current_regime()
```

### 3. Common Issue Categories

#### gRPC Errors

**UNAVAILABLE** (Service not running):
```bash
# Check if service is up
docker-compose ps

# Check service logs
docker-compose logs <service>

# Restart service
docker-compose restart <service>
```

**DEADLINE_EXCEEDED** (Timeout):
```python
# Increase timeout
response = await stub.GetStrategy(request, timeout=60.0)  # 60 seconds

# Or check for blocking operations
grep -r "time.sleep" services/*/src/
```

**INVALID_ARGUMENT** (Bad request):
```python
# Add input validation
class StrategyRequest(BaseModel):
    user_id: str
    symbols: List[str]

    @validator('symbols')
    def validate_symbols(cls, v):
        if not v:
            raise ValueError('symbols cannot be empty')
        return v
```

#### Redpanda Issues

**Connection refused**:
```bash
# Check Redpanda status
docker-compose ps redpanda

# Check logs
docker-compose logs redpanda

# Verify port
netstat -an | grep 9092
```

**Consumer not receiving messages**:
```python
# Verify topic exists
from aiokafka.admin import AIOKafkaAdminClient

admin = AIOKafkaAdminClient(bootstrap_servers='redpanda:9092')
await admin.start()
topics = await admin.list_topics()
print(topics)  # Check if your topic is listed
```

#### Redis Issues

**Connection timeout**:
```bash
# Check Redis status
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping
```

**Cache not working**:
```python
# Verify TTL
await redis.ttl('market:regime:current')  # Should return seconds remaining

# Check key exists
await redis.exists('market:regime:current')  # Should return 1 if exists
```

#### Database Issues

**Connection pool exhausted**:
```python
# Increase pool size
engine = create_async_engine(
    DATABASE_URL,
    pool_size=50,  # Increase from 20
    max_overflow=10
)
```

**Slow queries**:
```python
# Enable query logging
engine = create_async_engine(
    DATABASE_URL,
    echo=True  # Log all queries
)
```

### 4. Debugging Tools

#### Python Debugger

```python
import pdb; pdb.set_trace()  # Breakpoint

# Or async version
import ipdb; await ipdb.set_trace()
```

#### Logging

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add debug logs
logger.debug("Request received", extra={
    'user_id': user_id,
    'request': request.dict()
})
```

#### gRPC Debugging

```bash
# Test gRPC endpoint directly
grpcurl -plaintext -d '{"user_id": "test"}' \
  localhost:50051 \
  bloasis.market_regime.MarketRegimeService/GetCurrentRegime

# List available services
grpcurl -plaintext localhost:50051 list

# Describe service
grpcurl -plaintext localhost:50051 describe bloasis.market_regime.MarketRegimeService
```

#### Docker Debugging

```bash
# Enter container
docker-compose exec <service> /bin/bash

# Check environment variables
docker-compose exec <service> env

# Check file system
docker-compose exec <service> ls -la /app
```

### 5. Performance Debugging

#### Find Slow Operations

```python
import time

async def timed_operation():
    start = time.time()
    result = await expensive_operation()
    duration = (time.time() - start) * 1000
    logger.warning(f"Slow operation: {duration}ms")
    return result
```

#### Profile Code

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run code
await service.analyze()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumtime')
stats.print_stats(20)  # Top 20 slowest
```

### 6. Memory Debugging

```python
import tracemalloc

# Start tracking
tracemalloc.start()

# Run code
await service.analyze()

# Get stats
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

## Issue Resolution Pattern

### 1. Identify Root Cause

- [ ] Read full error traceback
- [ ] Check service logs
- [ ] Verify configuration
- [ ] Test in isolation

### 2. Fix

- [ ] Implement fix
- [ ] Add test to prevent regression
- [ ] Verify fix locally
- [ ] Check for similar issues elsewhere

### 3. Prevent Recurrence

- [ ] Add validation
- [ ] Improve error messages
- [ ] Add monitoring
- [ ] Document solution

## Example Debugging Session

```
Issue: Market Regime Service returning stale data

1. Gather info:
   - Expected: Fresh regime (< 5 min old)
   - Actual: 2 hour old regime
   - Error: None

2. Hypothesis: Redis cache not expiring

3. Investigation:
   ```bash
   docker-compose exec redis redis-cli
   > TTL market:regime:current
   (integer) -1  # Never expires!
   ```

4. Root cause: Missing TTL in cache set

5. Fix:
   ```python
   # Before (bug)
   await redis.set('market:regime:current', data)

   # After (fixed)
   await redis.setex('market:regime:current', 21600, data)  # 6 hours
   ```

6. Test:
   ```python
   @pytest.mark.asyncio
   async def test_cache_expiration():
       await service.cache_regime(data)
       ttl = await redis.ttl('market:regime:current')
       assert ttl > 0  # Has expiration
       assert ttl <= 21600  # Within 6 hours
   ```

7. Deploy:
   - Add test
   - Fix code
   - Verify TTL in production
```

## When Stuck

1. **Review architecture docs** - Am I following the design?
2. **Check similar code** - How do other services handle this?
3. **Read logs carefully** - Error message might be misleading
4. **Ask for help** - Describe what you've tried
