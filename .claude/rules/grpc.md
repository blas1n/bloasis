---
always: true
---

# gRPC Communication Rules

## CRITICAL: Internal MSA Communication

**ALWAYS use gRPC for internal service-to-service communication.**

**NEVER use HTTP/REST between backend services.**

### Why

- gRPC is 10x faster than HTTP (10-50ms vs 100-500ms)
- This is a core architectural decision
- Performance is critical for trading algorithms

### Implementation

1. **All .proto files MUST include HTTP annotations** (for Kong transcoding)
2. **Backend services implement gRPC only** (not HTTP)
3. **Kong Gateway handles REST for external clients** (automatic transcoding)

### Example

```protobuf
service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}
```

### Error Handling

**ALWAYS handle gRPC errors explicitly:**

```python
try:
    response = await stub.GetStrategy(request)
except grpc.RpcError as e:
    if e.code() == grpc.StatusCode.UNAVAILABLE:
        # Service unavailable
        pass
    elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
        # Timeout
        pass
    raise
```

### Verification

Before committing any service:
- [ ] Uses gRPC for inter-service calls
- [ ] .proto has HTTP annotations
- [ ] Handles gRPC errors
- [ ] No HTTP client imports (requests, httpx) for internal calls
