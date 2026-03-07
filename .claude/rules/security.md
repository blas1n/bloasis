# Security Rules

## CRITICAL: Financial Platform Security

**This is a trading platform handling real money. Security is non-negotiable.**

### 1. Environment Variables

**NEVER commit secrets to git.**

**ALWAYS use .env files (gitignored) + Pydantic Settings in `app/config.py`:**

```python
# Correct — Pydantic Settings validates at startup
from app.config import settings
api_key = settings.llm_api_key

# Wrong
ANTHROPIC_API_KEY = "sk-1234567890"  # NEVER hardcode!
```

**Provide .env.example:**

```bash
# .env.example (committed)
LLM_API_KEY=your_api_key_here
JWT_SECRET_KEY=your_secret_here

# .env (gitignored, actual secrets)
LLM_API_KEY=sk-real-key-here
```

### 2. API Keys in Logs

**NEVER log API keys or secrets.**

```python
# Correct
logger.info("Calling Claude API", extra={"key_length": len(api_key)})

# Wrong
logger.info(f"Using API key: {api_key}")  # NO!
```

### 3. SQL Injection Prevention

**ALWAYS use SQLAlchemy ORM via repositories. No raw SQL.**

```python
# Correct — repository with ORM
user = await self.user_repo.find_by_email(email)

# Wrong
query = f"SELECT * FROM users WHERE id = {user_id}"  # NO! SQL injection
```

### 4. Input Validation

**Validate ALL user inputs via Pydantic models:**

```python
from pydantic import BaseModel, validator

class OrderRequest(BaseModel):
    symbol: str
    qty: Decimal
    side: Literal["buy", "sell"]

    @validator('symbol')
    def validate_symbol(cls, v):
        if not v.isalnum() or len(v) > 10:
            raise ValueError(f'Invalid symbol: {v}')
        return v.upper()
```

### 5. Authentication

**All endpoints except `/v1/auth/*` and `/health` require JWT auth.**

```python
# FastAPI dependency injection for auth
from app.dependencies import get_current_user

@router.get("/v1/users/{user_id}/preferences")
async def get_preferences(
    user_id: uuid.UUID,
    current_user = Depends(get_current_user),
):
    verify_user_access(current_user, user_id)
    ...
```

### 6. Rate Limiting

**Prevent abuse with slowapi rate limits:**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/v1/auth/tokens")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...
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
- Alpaca: paper trading by default

### 9. Error Messages

**NEVER expose internal details in error messages:**

```python
# Correct (API response)
raise HTTPException(status_code=400, detail="Invalid request")

# Correct (logs)
logger.error("Database connection failed", exc_info=True)

# Wrong (API response)
raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")  # Exposes internals!
```

### 10. Dependency Security

**Keep dependencies updated:**

```bash
# Check for vulnerabilities
uv run pip-audit

# Update dependencies
uv lock --upgrade
```

## Verification Checklist

Before every commit:
- [ ] No hardcoded secrets
- [ ] .env.example provided
- [ ] No API keys in logs
- [ ] ORM queries only (no raw SQL)
- [ ] Input validation via Pydantic
- [ ] Decimal used for money
- [ ] No internal errors exposed
- [ ] JWT auth on all protected endpoints
