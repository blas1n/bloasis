---
description: REST API rules for BLOASIS FastAPI monolith
---

# REST API Rules

## Architecture: FastAPI Monolith

**BLOASIS uses a single FastAPI process. No gRPC, no message brokers.**

### API Design

- RESTful endpoints under `/v1/` prefix
- JWT authentication on all endpoints except `/v1/auth/*` and `/health`
- CamelCase JSON responses (via CamelJSONResponse)
- Pydantic request validation

### Error Handling

```python
from fastapi import HTTPException

# Return appropriate HTTP status codes
raise HTTPException(status_code=404, detail="Resource not found")
raise HTTPException(status_code=401, detail="Invalid token")
raise HTTPException(status_code=403, detail="Access denied")
```

### External API Calls

Use `httpx` for external HTTP calls (e.g., Alpaca API):

```python
import httpx

async with httpx.AsyncClient() as client:
    resp = await client.post(url, json=payload, timeout=30)
```
