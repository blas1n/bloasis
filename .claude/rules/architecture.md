---
description: Architecture rules and critical design decisions for BLOASIS
---

# Architecture Rules

## CRITICAL: Core Architectural Decisions

These decisions are final. Do NOT deviate without explicit approval.

### 1. FastAPI Monolith (Single Process)

**All backend code lives in `app/`. No microservices, no gRPC, no message brokers.**

```python
# Correct — direct function call
result = await portfolio_svc.record_trade(user_id, order_details)

# Wrong — no gRPC, no message brokers
from services.portfolio.src.service import PortfolioService  # NO!
await producer.send('trade_executed', event)  # NO!
```

### 2. Python-Only Backend

**All backend MUST be Python 3.11+.**

### 3. Repository Pattern Required

**All database access MUST go through `app/repositories/` using SQLAlchemy ORM.**

```python
# Correct — repository handles DB queries
user = await self.user_repo.find_by_email(email)

# Wrong — raw SQL in service layer
result = await session.execute(text("SELECT ..."))  # NO!
```

### 4. Pure Core Layer

**`app/core/` MUST have NO I/O (no DB, no Redis, no HTTP calls).**

### 5. Type Hints Required

**ALL public functions MUST have type hints.**

### 6. Decimal for Money

**NEVER use float for financial calculations.**

### 7. Tier 1-2-3 Caching

**Market Regime and Sector Candidates are shared across ALL users (Tier 1).**

### 8. JWT Authentication

**All endpoints except `/v1/auth/*` and `/health` require JWT auth via `get_current_user`.**

### 9. Python Path Configuration

**NEVER use sys.path.insert(). Use PYTHONPATH.**

### 10. No Service-Level Dockerfiles

**Docker configuration is at root level only.**

### 11. Dependency Management

**Use pyproject.toml + uv only. No requirements.txt.**

### 12. Environment Variable Validation

**Use Pydantic Settings in `app/config.py`. No hardcoded secrets.**

### 13. Dependency Injection

**Services receive dependencies via FastAPI's Depends system. Never create service instances inside methods.**

### 14. Git Commit Rules

**NEVER include Co-Authored-By in commit messages.**

Format: `type(scope): short description`
