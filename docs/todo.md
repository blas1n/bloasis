# TODO

## Deferred Items

### 1. Registration Endpoint
- `POST /v1/auth/register` — Currently only token issuance is implemented; needs registration flow
- Email validation, password hashing, duplicate checks, etc.

### 2. Prometheus Metrics / Observability
- Add `/metrics` endpoint (prometheus-fastapi-instrumentator)
- Track request latency, error rate, LLM call count/cost
- Configure Grafana dashboard
