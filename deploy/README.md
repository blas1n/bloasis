# BLOASIS Production Deployment

Docker Compose deployment for Mac Mini (Apple Silicon).

## Prerequisites

- Docker 24.0+
- Docker Compose 2.20+
- 16GB RAM minimum (32GB recommended)

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Set required values

# 2. Deploy
./scripts/deploy.sh --build

# 3. Check status
./scripts/health-check.sh
```

## Deployment Profiles

```bash
# Core services only (default)
./scripts/deploy.sh

# With monitoring (Prometheus + Grafana)
./scripts/deploy.sh --monitoring

# Full stack (includes frontend)
./scripts/deploy.sh --full

# Force rebuild
./scripts/deploy.sh --build
```

## Scripts

| Script | Description |
|--------|-------------|
| `deploy.sh` | Build and start services |
| `stop.sh` | Stop all services |
| `restart.sh [service]` | Restart all or specific service |
| `logs.sh [service] [lines]` | View logs |
| `backup.sh` | Backup PostgreSQL database |
| `health-check.sh` | Check service status |

## Port Reference

### External Access

| Service | Port | URL |
|---------|------|-----|
| Kong API | 8000 | http://localhost:8000 |
| Consul UI | 8500 | http://localhost:8500 |
| Grafana | 3001 | http://localhost:3001 |
| Frontend | 3000 | http://localhost:3000 |
| WebSocket | 8080 | ws://localhost:8080 |

### gRPC Services (Internal)

| Service | Port |
|---------|------|
| market-regime | 50051 |
| user | 50052 |
| market-data | 50053 |
| classification | 50054 |
| strategy | 50055 |
| auth | 50056 |
| portfolio | 50057 |
| backtesting | 50058 |
| risk-committee | 50059 |
| executor | 50060 |

## Required Environment Variables

```bash
POSTGRES_PASSWORD=<strong-password>
ALPACA_API_KEY=<your-key>
ALPACA_SECRET_KEY=<your-secret>
CLAUDE_API_KEY=<your-anthropic-key>
```

See `.env.example` for full list.

## Troubleshooting

```bash
# View logs
./scripts/logs.sh market-regime

# Restart service
./scripts/restart.sh market-regime

# Check resource usage
docker stats

# Clean up
docker system prune -a
```

## Backup

```bash
# Create backup
./scripts/backup.sh

# Restore
docker compose exec -T postgres psql -U postgres bloasis < backups/bloasis_YYYYMMDD.sql
```
