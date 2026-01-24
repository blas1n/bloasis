---
always: true
---

# Security Rules

## CRITICAL: Financial Platform Security

**This is a trading platform handling real money. Security is non-negotiable.**

### 1. Environment Variables

**NEVER commit secrets to git.**

**ALWAYS use .env files (gitignored):**

```python
# Correct
import os
from dotenv import load_dotenv

load_dotenv()
FINGPT_API_KEY = os.getenv('FINGPT_API_KEY')

if not FINGPT_API_KEY:
    raise ValueError("FINGPT_API_KEY not set")

# Wrong
FINGPT_API_KEY = "sk-1234567890"  # NEVER hardcode!
```

**Provide .env.example:**

```bash
# .env.example (committed)
FINGPT_API_KEY=your_api_key_here
CLAUDE_API_KEY=your_api_key_here

# .env (gitignored, actual secrets)
FINGPT_API_KEY=sk-real-key-here
CLAUDE_API_KEY=sk-real-key-here
```

### 2. API Keys in Logs

**NEVER log API keys or secrets.**

```python
# Correct
logger.info("Calling FinGPT API", extra={"key_length": len(api_key)})

# Wrong
logger.info(f"Using API key: {api_key}")  # NO!
```

### 3. SQL Injection Prevention

**ALWAYS use parameterized queries.**

```python
# Correct
from sqlalchemy import select
result = await session.execute(
    select(User).where(User.id == user_id)
)

# Wrong
query = f"SELECT * FROM users WHERE id = {user_id}"  # NO! SQL injection
```

### 4. Input Validation

**Validate ALL user inputs:**

```python
from pydantic import BaseModel, validator

class StrategyRequest(BaseModel):
    user_id: str
    symbols: List[str]

    @validator('symbols')
    def validate_symbols(cls, v):
        if len(v) > 50:
            raise ValueError('Too many symbols')
        for symbol in v:
            if not symbol.isalnum() or len(symbol) > 10:
                raise ValueError(f'Invalid symbol: {symbol}')
        return v
```

### 5. Authentication (Phase 2)

**All external endpoints MUST require authentication.**

**Kong JWT verification:**

```yaml
# Kong config (Phase 2)
plugins:
  - name: jwt
    config:
      key_claim_name: sub
```

**Backend trusts Kong:**

```python
# Backend receives authenticated user_id from Kong header
user_id = request.headers.get('X-User-Id')
```

### 6. Rate Limiting

**Prevent abuse with rate limits:**

```yaml
# Kong config
plugins:
  - name: rate-limiting
    config:
      minute: 60
      policy: local
```

### 7. Financial Data Precision

**Use Decimal for all financial calculations:**

```python
from decimal import Decimal, ROUND_HALF_UP

# Correct
price = Decimal('150.25')
quantity = Decimal('10')
total = (price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

# Wrong
total = 150.25 * 10  # Float precision errors!
```

### 8. Secure Defaults

**Principle of least privilege:**

- Database users: minimal permissions
- API keys: read-only where possible
- Service accounts: scoped to specific resources

### 9. Error Messages

**NEVER expose internal details in error messages:**

```python
# Correct (external API)
return {"error": "Invalid request"}

# Correct (logs)
logger.error("Database connection failed", exc_info=True)

# Wrong (external API)
return {"error": f"Database error: {str(e)}"}  # Exposes internals!
```

### 10. Dependency Security

**Keep dependencies updated:**

```bash
# Check for vulnerabilities
pip-audit

# Update dependencies
pip install --upgrade -r requirements.txt
```

## Verification Checklist

Before every commit:
- [ ] No hardcoded secrets
- [ ] .env.example provided
- [ ] No API keys in logs
- [ ] Parameterized SQL queries
- [ ] Input validation implemented
- [ ] Decimal used for money
- [ ] No internal errors exposed
- [ ] Rate limiting configured (if external endpoint)

## Security Incident Response

If a security issue is discovered:
1. **DO NOT commit the fix immediately** (reveals vulnerability)
2. Notify team privately
3. Prepare patch in private branch
4. Deploy fix to production first
5. Then commit to public repo
