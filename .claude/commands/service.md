---
name: service
description: Create a new microservice with standard structure
---

# Service Command

Generate a new microservice with all boilerplate code and configuration.

## Usage

```
/service <service-name> <grpc-port>
```

## Example

```
/service market-regime 50051
```

## What This Does

1. **Creates service directory** with standard structure
2. **Generates boilerplate** (main.py, service.py, models.py)
3. **Creates .proto file** with HTTP annotations
4. **Sets up tests** directory
5. **Adds Dockerfile** and requirements.txt
6. **Creates .env.example**

## Generated Structure

```
services/market-regime/
├── src/
│   ├── __init__.py
│   ├── main.py          # FastAPI + gRPC server
│   ├── service.py       # gRPC service implementation
│   ├── models.py        # Service-specific models
│   ├── clients/         # gRPC clients (empty)
│   └── utils/           # Service utilities (empty)
├── tests/
│   ├── __init__.py
│   ├── test_service.py
│   └── test_integration.py
├── proto -> ../../shared/proto  # Symlink
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Generated Files

### src/main.py

```python
import asyncio
import grpc
from concurrent import futures
from shared.proto import {service}_pb2_grpc
from .service import {Service}Service

async def serve_grpc():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    {service}_pb2_grpc.add_{Service}ServiceServicer_to_server(
        {Service}Service(), server
    )
    server.add_insecure_port(f'[::]:{port}')
    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve_grpc())
```

### src/service.py

```python
import grpc
from shared.proto import {service}_pb2, {service}_pb2_grpc

class {Service}Service({service}_pb2_grpc.{Service}ServiceServicer):
    async def initialize(self):
        # Initialize dependencies
        pass

    async def shutdown(self):
        # Cleanup resources
        pass
```

### shared/proto/{service}.proto

```protobuf
syntax = "proto3";
package bloasis.{service};

import "google/api/annotations.proto";

service {Service}Service {
  rpc Get{Resource}(Get{Resource}Request) returns (Get{Resource}Response) {
    option (google.api.http) = {
      get: "/v1/{service}/{resource}"
    };
  }
}
```

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["python", "-m", "src.main"]
```

### .env.example

```bash
SERVICE_NAME={service}
GRPC_PORT={port}
REDIS_HOST=redis
REDPANDA_BROKERS=redpanda:9092
LOG_LEVEL=INFO
```

## Next Steps

After generation:

1. **Implement business logic** in src/service.py
2. **Write tests** in tests/
3. **Update .proto** with actual RPC methods
4. **Add to docker-compose.yml**
5. **Configure Envoy routing** (if external)

## Reference

See [services/CLAUDE.md](../../services/CLAUDE.md) for detailed implementation guide.
