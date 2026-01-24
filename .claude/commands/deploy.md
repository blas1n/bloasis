---
name: deploy
description: Service deployment verification checklist
---

# Deploy Command

Verify service is ready for deployment.

## Usage

```
/deploy <service-name>
```

## What This Does

Run comprehensive deployment readiness checks:

1. **Implementation verification**
2. **Test coverage**
3. **Configuration validation**
4. **Security audit**
5. **Performance checks**

## Verification Checklist

### 1. Implementation Complete

- [ ] gRPC service implemented (src/service.py)
- [ ] Proto HTTP annotations present
- [ ] Health/Ready endpoints implemented
- [ ] Graceful shutdown implemented
- [ ] Logging configured (structured JSON)
- [ ] Error handling for all RPC methods

**Check:**
```bash
# Verify proto annotations
grep -r "google.api.http" shared/proto/{service}.proto

# Verify health endpoints
grep -r "@app.get(\"/health\")" services/{service}/src/main.py
```

### 2. Testing

- [ ] Unit tests (≥ 80% coverage)
- [ ] Integration tests written
- [ ] External APIs mocked
- [ ] Error cases tested
- [ ] All tests passing

**Check:**
```bash
pytest services/{service}/tests/ --cov=src --cov-fail-under=80
```

### 3. Configuration

- [ ] .env.example provided
- [ ] Environment variables validated
- [ ] No hardcoded secrets
- [ ] Dockerfile present
- [ ] requirements.txt complete

**Check:**
```bash
# Verify .env.example exists
ls services/{service}/.env.example

# Check for hardcoded secrets
grep -r "sk-" services/{service}/src/ | grep -v ".env"  # Should be empty
```

### 4. Security

- [ ] API keys loaded from environment
- [ ] SQL queries parameterized
- [ ] Input validation implemented
- [ ] No secrets in logs
- [ ] Decimal used for money

**Check:**
```bash
# Check for float money calculations
grep -r "float.*price\|float.*amount" services/{service}/src/  # Should be empty

# Verify Decimal usage
grep -r "from decimal import Decimal" services/{service}/src/
```

### 5. Performance

- [ ] Connection pooling configured
- [ ] Redis caching implemented (Tier 1-2)
- [ ] gRPC keepalive configured
- [ ] Async operations parallelized

**Check:**
```bash
# Verify async usage
grep -r "async def" services/{service}/src/ | wc -l

# Check for blocking operations
grep -r "time.sleep\|requests\." services/{service}/src/ | grep -v test
```

### 6. Docker Integration

- [ ] Added to docker-compose.yml
- [ ] Service port exposed
- [ ] Environment variables mapped
- [ ] Dependencies declared

**Check:**
```bash
# Verify service in docker-compose
grep -A 10 "{service}:" docker-compose.yml
```

### 7. Kong Gateway (if external)

- [ ] Route configured in kong.yml
- [ ] gRPC-gateway plugin enabled
- [ ] Rate limiting configured
- [ ] Proto file mounted

**Check:**
```bash
# Verify Kong routing
grep -A 10 "{service}" infra/kong/kong.yml
```

### 8. Monitoring

- [ ] Structured logging implemented
- [ ] Metrics exposed (if needed)
- [ ] Error tracking configured

## Example Output

```bash
$ /deploy market-regime

Verifying deployment readiness for market-regime...

✓ Implementation
  ✓ gRPC service implemented
  ✓ Proto HTTP annotations present
  ✓ Health endpoints present
  ✓ Graceful shutdown implemented

✓ Testing
  ✓ Coverage: 93% (threshold: 80%)
  ✓ All tests passing (24 passed)
  ✓ External APIs mocked

✓ Configuration
  ✓ .env.example present
  ✓ No hardcoded secrets
  ✓ Dockerfile present

✓ Security
  ✓ Environment variables validated
  ✓ Decimal used for money
  ✗ Missing input validation for symbol field

✗ Performance
  ✗ Missing connection pooling for database

✗ Docker
  ✗ Not added to docker-compose.yml

Summary: 5/8 categories passed
Action required before deployment.
```

## Manual Verification

After automated checks, manually verify:

1. **Test service locally**
   ```bash
   docker-compose up market-regime
   grpcurl -plaintext localhost:50051 list
   ```

2. **Check logs**
   ```bash
   docker-compose logs -f market-regime
   ```

3. **Test gRPC endpoint**
   ```bash
   grpcurl -plaintext -d '{"user_id": "test"}' \
     localhost:50051 bloasis.market_regime.MarketRegimeService/GetCurrentRegime
   ```

4. **Verify Kong transcoding** (if external)
   ```bash
   curl http://localhost:8000/v1/market-regime/current
   ```

## Deployment

Once all checks pass:

```bash
# Build image
docker-compose build market-regime

# Deploy
docker-compose up -d market-regime

# Verify health
curl http://localhost:8080/health
```
