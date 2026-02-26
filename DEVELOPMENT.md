# BLOASIS Development Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [buf](https://buf.build/)

### Architecture Overview

```
Frontend (Next.js) → Envoy Gateway (REST→gRPC) → Backend Services (gRPC)
                                               ↓
                                    Redpanda, PostgreSQL/TimescaleDB
```

Envoy Gateway is **required** for frontend-backend communication. It translates REST calls to gRPC.

---

## Starting the Full Stack

### 1. Generate Proto Files

```bash
make proto-generate
```

### 2. Start Infrastructure

```bash
docker-compose -f deploy/docker-compose.yml up -d
docker-compose -f deploy/docker-compose.yml ps
```

Expected services:
- **PostgreSQL** (port 5432)
- **Redpanda** (port 9092)
- **Envoy Gateway** (port 8000)

### 3. Run Database Migrations

```bash
uv run python -m alembic upgrade head
```

### 4. Start Backend Services

```bash
# Each service in a separate terminal
cd services/market-regime && uv run python -m src.main
cd services/strategy      && uv run python -m src.main
cd services/portfolio     && uv run python -m src.main
# ... etc
```

### 5. Start Frontend

```bash
cd frontend
npm run dev
```

Visit: **http://localhost:3000**

---

## Service Ports

| Service | Port | Type |
|---------|------|------|
| Frontend | 3000 | HTTP (dev) |
| Envoy Gateway | 8000 | HTTP/REST (external) |
| market-regime | 50051 | gRPC |
| user | 50052 | gRPC |
| market-data | 50053 | gRPC |
| classification | 50054 | gRPC |
| strategy | 50055 | gRPC |
| auth | 50056 | gRPC |
| portfolio | 50057 | gRPC |
| backtesting | 50058 | gRPC |
| risk-committee | 50059 | gRPC |
| executor | 50060 | gRPC |
| PostgreSQL | 5432 | TCP |
| Redpanda | 9092 | Kafka |

---

## Development Workflow

### Commands

```bash
make proto-generate  # Regenerate proto files after .proto changes
make lint            # ruff check shared/ services/
make test            # pytest with 80% coverage gate
make check           # lint + proto-lint + test (run before commit)
```

### Adding a New Service

Use the `/service` skill in Claude Code to scaffold a new service with the standard structure.

### Modifying Proto Files

```bash
# 1. Edit shared/proto/*.proto
# 2. Regenerate
make proto-generate
# 3. Update service implementation
```

---

## Troubleshooting

### gRPC Health Check

```bash
# Check any service
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check  # market-regime
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check  # user
```

### Envoy Gateway Issues

```bash
# Check Envoy admin
curl http://localhost:8001/clusters

# Verify proto descriptor was generated
ls infra/envoy/proto.pb
make proto-generate  # regenerate if missing
```

### Database Connection Failed

```bash
docker-compose -f deploy/docker-compose.yml ps postgres
psql -h localhost -U postgres -d bloasis -c "SELECT 1;"
docker-compose -f deploy/docker-compose.yml restart postgres
```

### Redpanda Issues

```bash
rpk topic list
rpk topic create regime-change --partitions 3
```

### Module Import Errors

Services use `uv` and `PYTHONPATH` — never `pip install` or `requirements.txt`.

```bash
# Install dependencies for a service
cd services/market-regime
uv sync

# Run with correct PYTHONPATH
uv run python -m src.main
```

---

## Quick Health Check

```bash
#!/bin/bash
echo "=== BLOASIS Health Check ==="

echo -n "Envoy Gateway: "
curl -s http://localhost:8000/ > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "Frontend: "
curl -s http://localhost:3000 > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "PostgreSQL: "
pg_isready -h localhost -p 5432 > /dev/null 2>&1 && echo "OK" || echo "DOWN"

echo -n "Market Regime (gRPC): "
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check > /dev/null 2>&1 && echo "OK" || echo "DOWN"
```

---

## Additional Resources

- **Architecture rules**: `.claude/rules/`
- **Proto definitions**: `shared/proto/`
- **Envoy config**: `infra/envoy/`
- **Database schema**: `infra/postgres/`
