---
context: review
description: Code review mode - verifying quality and compliance
---

# Review Context

You are reviewing code for BLOASIS. Ensure adherence to standards and architecture.

## Review Checklist

### 1. Architecture Compliance

Verify against `.claude/rules/architecture.md`:

- [ ] gRPC used for internal communication (not HTTP)
- [ ] Redpanda used for events (not Redis Pub/Sub)
- [ ] Python 3.11+ (no other languages in Phase 1)
- [ ] Type hints on all public functions
- [ ] Shared code in `shared/` (not duplicated)
- [ ] No direct service imports
- [ ] Decimal used for money (not float)
- [ ] Proto HTTP annotations present

**Check:**
```bash
# Verify gRPC usage
grep -r "import requests\|import httpx" services/*/src/ | grep -v test

# Verify Redpanda usage
grep -r "redis.*publish" services/*/src/

# Verify type hints
grep -r "^async def.*->" services/*/src/
```

### 2. Code Quality

Check `services/CLAUDE.md` and `.claude/rules/`:

- [ ] Async/await used consistently
- [ ] Error handling for gRPC calls
- [ ] Structured logging (JSON format)
- [ ] Environment variables (no hardcoded secrets)
- [ ] Input validation (Pydantic)
- [ ] Connection pooling (DB, gRPC)

**Check:**
```python
# Good
async def get_regime(user_id: str) -> Dict[str, any]:
    try:
        response = await stub.GetStrategy(request)
    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()}")
        raise

# Bad
def get_regime(user_id):  # Missing async, type hints
    response = stub.GetStrategy(request)  # Missing error handling
```

### 3. Testing

Verify `.claude/rules/testing.md`:

- [ ] Unit tests present
- [ ] Coverage ≥ 80%
- [ ] External APIs mocked
- [ ] Integration tests (if cross-service)
- [ ] Error cases tested

**Run:**
```bash
pytest services/*/tests/ --cov=src --cov-fail-under=80
```

### 4. Security

Check `.claude/rules/security.md`:

- [ ] No hardcoded API keys
- [ ] .env.example provided
- [ ] No secrets in logs
- [ ] Parameterized SQL queries
- [ ] Input validation implemented
- [ ] Decimal for financial calculations

**Check:**
```bash
# Search for hardcoded secrets
grep -r "sk-\|api_key\s*=\s*\"" services/*/src/ | grep -v ".env"

# Verify Decimal usage
grep -r "float.*price\|float.*amount" services/*/src/
```

### 5. gRPC Implementation

Verify `services/CLAUDE.md` and `.claude/rules/grpc.md`:

- [ ] .proto file has HTTP annotations
- [ ] Service implements gRPC only
- [ ] Error handling for all RPC methods
- [ ] Timeout set on client calls
- [ ] Channel reuse (not per-request)

**Check:**
```protobuf
// Required
option (google.api.http) = {
  get: "/v1/resource"
};

// Missing - reject
rpc GetResource(...) returns (...);  // No HTTP annotation
```

### 6. Performance

- [ ] Async operations parallelized
- [ ] Redis caching used (Tier 1-2)
- [ ] Database connection pooling
- [ ] No blocking operations

**Check:**
```python
# Good - parallel
regime, sectors, symbols = await asyncio.gather(
    get_regime(),
    get_sectors(),
    get_symbols()
)

# Bad - sequential
regime = await get_regime()
sectors = await get_sectors()
symbols = await get_symbols()
```

## Review Response Format

### Approve

```
✅ APPROVED

All checks passed:
- Architecture compliance
- Code quality standards
- Test coverage (85%)
- Security requirements
- Performance optimized

No issues found.
```

### Request Changes

```
❌ CHANGES REQUESTED

Issues found:

1. Architecture violation (HIGH)
   - Using HTTP instead of gRPC
   - Location: src/clients/ai_analysis.py:45
   - Fix: Replace httpx with gRPC client

2. Missing tests (HIGH)
   - Coverage: 65% (threshold: 80%)
   - Missing: src/service.py lines 78-95
   - Fix: Add unit tests for error cases

3. Security issue (CRITICAL)
   - Hardcoded API key
   - Location: src/main.py:12
   - Fix: Load from environment variable

4. Performance issue (MEDIUM)
   - Sequential API calls
   - Location: src/service.py:120-125
   - Fix: Use asyncio.gather()

Cannot approve until resolved.
```

## Common Issues

### Anti-patterns to Catch

1. **HTTP between services**
   ```python
   # Bad
   response = httpx.get('http://ai-analysis:8080/strategy')

   # Good
   response = await grpc_client.get_strategy()
   ```

2. **Float for money**
   ```python
   # Bad
   total = 150.25 * 10

   # Good
   from decimal import Decimal
   total = Decimal('150.25') * Decimal('10')
   ```

3. **Missing error handling**
   ```python
   # Bad
   await stub.GetStrategy(request)

   # Good
   try:
       await stub.GetStrategy(request)
   except grpc.RpcError as e:
       if e.code() == grpc.StatusCode.UNAVAILABLE:
           # Handle
           pass
   ```

4. **Missing type hints**
   ```python
   # Bad
   async def get_regime(user_id):
       pass

   # Good
   async def get_regime(user_id: str) -> Dict[str, any]:
       pass
   ```

## Final Verification

Before approving:
- [ ] Run `/deploy <service>` checklist
- [ ] All automated checks pass
- [ ] No critical or high severity issues
- [ ] Code follows BLOASIS patterns
