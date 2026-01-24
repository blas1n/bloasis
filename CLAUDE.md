# Claude Development Guide for BLOASIS

## Project Overview

BLOASIS is an AI-powered multi-asset trading platform combining LLMs and Reinforcement Learning.

**Core Technologies**:
- Backend: Python 3.11+ (FastAPI), gRPC internal communication
- AI/ML: FinGPT (financial analysis), Claude Sonnet 4 (complex reasoning), LangGraph (multi-agent)
- Backtesting: VectorBT, FinRL
- Infrastructure: Kong Gateway (gRPC-to-REST), Redpanda (messaging), PostgreSQL/TimescaleDB
- Frontend: TypeScript (React/Next.js)

## Architecture Principles

### 1. MSA Communication
- **Internal**: gRPC only (10x faster than HTTP)
- **External**: Kong transcodes gRPC → REST
- **.proto files**: Include HTTP annotations for Kong

### 2. Event Messaging
- **Redpanda** (not RabbitMQ or Redis Pub/Sub)
- Backend services publish events
- Notification Service consumes and broadcasts via WebSocket

### 3. AI Architecture
- **FinGPT**: Financial domain analysis (cheap, specialized)
  - Market regime, sector analysis, sentiment
- **Claude**: Complex reasoning (expensive, general)
  - Technical synthesis, risk assessment, final decisions
- **LangGraph**: Multi-agent orchestration with conditional branching

### 4. Cost Optimization
- **Hybrid 3-Tier**: Shared analysis (Tier 1-2) + User customization (Tier 3)
- Reduces API costs by 93%

## Key Implementation Patterns

### gRPC Service with HTTP Annotations
```protobuf
service MarketRegimeService {
  rpc GetCurrentRegime(RegimeRequest) returns (RegimeResponse) {
    option (google.api.http) = {
      get: "/v1/market-regime/current"
    };
  }
}
```

### Redpanda Event Publishing
```python
from aiokafka import AIOKafkaProducer

producer = AIOKafkaProducer(bootstrap_servers='redpanda:9092')
await producer.send('regime-change', event_data)
```

### LangGraph Multi-Agent
```python
from langgraph.graph import StateGraph

workflow = StateGraph(AnalysisState)
workflow.add_node("macro", macro_strategist)  # FinGPT
workflow.add_node("technical", technical_analyst)  # Claude
workflow.add_conditional_edges("risk", should_adjust, {
    "approve": END,
    "adjust": "technical"
})
```

## Critical Design Decisions

1. **gRPC Internal Communication**: 10x performance vs HTTP (10-50ms vs 100-500ms)
2. **Redpanda from Phase 1**: Avoids migration cost, message durability
3. **Notification Service Pattern**: Backend doesn't handle WebSocket, only publishes to Redpanda
4. **FinGPT + Claude Division**: Cost optimization via role specialization

---

**Note**: Detailed folder structure, testing guidelines, and development standards are defined in Claude skills.
