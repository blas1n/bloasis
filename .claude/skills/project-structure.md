---
name: project-structure
description: BLOASIS project folder structure and naming conventions
---

# Project Structure Skill

## Root Structure

```
bloasis/
├── services/           # Backend microservices (Python/FastAPI + gRPC)
├── frontend/           # Frontend (TypeScript/React)
├── shared/             # Shared code (.proto, models, utils)
├── infra/              # Infrastructure configs (Kong, Consul, Docker)
├── tests/              # Integration and E2E tests
├── .devcontainer/      # DevContainer setup
├── .claude/            # Claude skills and config
└── docker-compose.yml  # Local development
```

## Service Structure

Each service in `services/` follows this pattern:

```
services/market-regime/
├── src/
│   ├── main.py         # FastAPI + gRPC server
│   ├── service.py      # gRPC service implementation
│   ├── models.py       # Service-specific models (Pydantic + SQLAlchemy)
│   ├── clients/        # gRPC clients for other services
│   └── utils/          # Service utilities
├── tests/
│   ├── test_service.py
│   └── test_integration.py
├── proto/              # Symlink to ../../shared/proto
├── Dockerfile
├── .env.example
└── pyproject.toml      # uv-based dependencies
```

## Shared Structure

```
shared/
├── proto/              # gRPC .proto definitions
│   ├── market_regime.proto
│   ├── ai_analysis.proto
│   └── common.proto    # Shared message types
├── utils/              # Shared utilities
│   ├── redpanda_client.py
│   ├── redis_client.py
│   ├── postgres_client.py
│   └── logging.py
├── tests/              # Tests for shared code
├── __init__.py
├── CLAUDE.md           # Development guide
└── pyproject.toml      # uv-based dependencies
```

**Note**: Models are NOT shared. Each service maintains its own models in `src/models.py` to preserve MSA independence.

## Proto Files

All .proto files must include HTTP annotations for Kong transcoding:

```protobuf
syntax = "proto3";
import "google/api/annotations.proto";

service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}
```

## Naming Conventions

**Python**:
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions: `snake_case()`
- Constants: `UPPER_SNAKE_CASE`

**TypeScript**:
- Components: `PascalCase.tsx`
- Utilities: `camelCase.ts`
- Interfaces: `PascalCase` (with `I` prefix)

**Proto**: `snake_case.proto`

**Directories**:
- Backend services: `kebab-case/`
- Frontend components: `PascalCase/`

## Import Order

**Python**:
```python
# 1. Standard library
# 2. Third-party
# 3. Local application
```

**TypeScript**:
```typescript
// 1. React/Next.js
// 2. Third-party
// 3. Local application
```

## Critical Rules

1. **Services communicate only via**:
   - gRPC (request-response)
   - Redpanda (events)

2. **Proto symlinks**:
   - Use `ln -s ../../shared/proto proto` in each service
   - Never duplicate .proto files

3. **Shared code**:
   - Cross-service utilities → `shared/utils/`
   - Models are NOT shared (each service has own `src/models.py`)
   - Never direct imports between services

4. **HTTP annotations required**:
   - All .proto services need HTTP annotations
   - Kong requires them for gRPC-to-REST transcoding
