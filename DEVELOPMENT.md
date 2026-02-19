# BLOASIS Development Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for frontend)
- Python 3.11+ (for backend services)

### Architecture Overview

```
Frontend (Next.js) → Envoy Gateway → Backend Services (gRPC)
                                  ↓
                            Redpanda, PostgreSQL, Redis
```

**Important**: Envoy Gateway is **required** for frontend-backend communication. It translates REST calls to gRPC.

---

## 🚀 Starting the Full Stack

### 1. Start Infrastructure Services

```bash
# Start PostgreSQL, Redis, Redpanda, Envoy Gateway
docker-compose up -d

# Verify services are running
docker-compose ps
```

Expected services:
- **PostgreSQL** (port 5432) - Database
- **Redis** (port 6379) - Cache
- **Redpanda** (port 9092) - Event streaming
- **Envoy Gateway** (port 8000) - API Gateway

### 2. Run Database Migrations

```bash
cd /workspace
python -m alembic upgrade head
```

### 3. Start Backend Services

**Option A: VSCode (Recommended)**
1. Open VSCode Debug panel (`Ctrl+Shift+D`)
2. Select **"Full Stack (All Services)"**
3. Press `F5`

**Option B: Manual**
```bash
# Each service in a separate terminal
cd services/user && python -m src.main
cd services/portfolio && python -m src.main
cd services/executor && python -m src.main
cd services/notification && python -m src.main
# ... etc
```

### 4. Start Frontend

```bash
cd frontend
npm run dev
```

Visit: **http://localhost:3000**

---

## 🔧 Troubleshooting

### "Envoy Gateway unavailable" Error

**Symptom**: Frontend shows "Cannot connect to Envoy Gateway" errors

**Solution**:
```bash
# Check if Envoy is running
curl http://localhost:8000/health

# If not running, start infrastructure
docker-compose up -d

# Verify Envoy routes are configured
curl http://localhost:8000/v1/users/demo-user/preferences
```

### Backend Services Not Responding

**Check service status**:
```bash
# gRPC health check for User Service (port 50052)
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check

# Portfolio Service (port 50057)
grpcurl -plaintext localhost:50057 grpc.health.v1.Health/Check
```

### Module Import Errors

**Symptom**: `ModuleNotFoundError: No module named 'sse_starlette'`

**Solution**:
```bash
# Install dependencies
python -m pip install sse-starlette fastapi uvicorn grpcio googleapis-common-protos

# Or install all at once
pip install -r requirements.txt  # if exists
```

### Database Connection Failed

**Solution**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
psql -h localhost -U postgres -d bloasis -c "SELECT 1;"

# Restart if needed
docker-compose restart postgres
```

---

## 📊 Service Ports

| Service | Port | Type | Description |
|---------|------|------|-------------|
| Frontend | 3000 | HTTP | Next.js dev server |
| Envoy Gateway | 8000 | HTTP/REST | API Gateway |
| User Service | 50052 | gRPC | User management |
| Portfolio Service | 50057 | gRPC | Portfolio tracking |
| Executor Service | 50060 | gRPC | Trade execution |
| Notification Service | 8080 | HTTP/SSE | Real-time notifications |
| PostgreSQL | 5432 | TCP | Database |
| Redis | 6379 | TCP | Cache |
| Redpanda | 9092 | Kafka | Event streaming |

---

## 🎯 Development Workflow

### 1. UI Development (Frontend Only)

Currently returns **503 errors** when Envoy is not running - this is intentional to make backend dependency explicit.

**To develop frontend with mock data**, create a local API mock server or use MSW (Mock Service Worker).

### 2. Backend Development

```bash
# Run specific service
cd services/user
python -m src.main

# Run with debugger
# Use VSCode launch config: "Backend: User Service"
```

### 3. Full Stack Development

Run everything with VSCode **"Full Stack (All Services)"** configuration.

---

## 🔍 Checking System Status

### Quick Health Check Script

```bash
#!/bin/bash
echo "=== BLOASIS Health Check ==="

echo -n "Envoy Gateway: "
curl -s http://localhost:8000/health > /dev/null && echo "✅ OK" || echo "❌ DOWN"

echo -n "Frontend: "
curl -s http://localhost:3000 > /dev/null && echo "✅ OK" || echo "❌ DOWN"

echo -n "PostgreSQL: "
pg_isready -h localhost -p 5432 > /dev/null && echo "✅ OK" || echo "❌ DOWN"

echo -n "Redis: "
redis-cli ping > /dev/null && echo "✅ OK" || echo "❌ DOWN"

echo -n "User Service (gRPC): "
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check > /dev/null 2>&1 && echo "✅ OK" || echo "❌ DOWN"
```

---

## 📚 Additional Resources

- **Architecture**: See `/workspace/CLAUDE.md`
- **API Documentation**: Envoy Admin API at `http://localhost:8001`
- **Proto Definitions**: `/workspace/shared/proto/`
- **Database Schema**: `/workspace/infra/postgres/`

---

## 🆘 Common Issues

### Issue: "trading_enabled column does not exist"
**Solution**: Run database migrations
```bash
python -m alembic upgrade head
```

### Issue: SSE connection fails
**Solution**: Check Notification Service is running on port 8080
```bash
curl http://localhost:8080/health
```

### Issue: Redpanda consumer errors
**Solution**: Create required topics
```bash
rpk topic list
rpk topic create trading-control-events --partitions 3
```

---

**Need Help?** Check logs in VSCode Debug Console or service output for detailed error messages.
