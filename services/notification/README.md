# Notification Service

Real-time WebSocket notification service for BLOASIS trading platform.

## Overview

The Notification Service consumes events from Redpanda and broadcasts them to connected WebSocket clients. It handles both broadcast messages (sent to all users) and targeted messages (sent to specific users).

## Features

- **WebSocket Server**: FastAPI-based WebSocket endpoint for real-time notifications
- **Event Consumption**: Consumes from 4 Redpanda topics
- **Broadcast Messages**: Regime changes and market alerts sent to all connected users
- **Targeted Messages**: Risk alerts and execution events sent to specific users
- **Thread-Safe**: Uses asyncio.Lock for safe concurrent connection management

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Redpanda      │────▶│  Notification    │────▶│  WebSocket      │
│   (Events)      │     │  Service         │     │  Clients        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │ EventHandlers │
                        └──────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌────────────┐      ┌─────────────┐
            │ Broadcast  │      │ User-Target │
            │ (All)      │      │ (Specific)  │
            └────────────┘      └─────────────┘
```

## Topics Consumed

| Topic | Event Type | Routing |
|-------|------------|---------|
| `regime-events` | `regime_change` | Broadcast to all |
| `alert-events` | `market_alert` | Broadcast to all |
| `risk-events` | `risk_alert` | Send to specific user |
| `execution-events` | `order_executed` | Send to specific user |

## Message Format

All WebSocket messages follow this format:

```json
{
  "type": "regime_change",
  "data": {
    "new_regime": "bull",
    "previous_regime": "sideways",
    "confidence": 0.85,
    "timestamp": "2025-01-29T10:00:00Z"
  }
}
```

### Message Types

- `regime_change`: Market regime has changed
- `market_alert`: Market-wide alert (e.g., volatility spike)
- `risk_alert`: User-specific risk warning
- `order_executed`: Order execution notification

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | `notification` | Service identifier |
| `WS_HOST` | `0.0.0.0` | WebSocket server host |
| `WS_PORT` | `8000` | WebSocket server port |
| `REDPANDA_BROKERS` | `redpanda:9092` | Redpanda broker addresses |
| `LOG_LEVEL` | `INFO` | Logging level |

## API Endpoints

### WebSocket

```
GET /ws?user_id=<user_id>
```

Connect to receive real-time notifications. The `user_id` query parameter is required for message routing.

### Health Check

```
GET /health
```

Returns service health status:

```json
{
  "status": "healthy",
  "service": "notification",
  "connections": 42,
  "consumer_running": true
}
```

## Development

### Install Dependencies

```bash
cd services/notification
uv pip install -e ".[dev]"
```

### Run Tests

```bash
pytest --cov=src --cov-fail-under=80
```

### Lint Check

```bash
ruff check src/ tests/
```

### Run Locally

```bash
python -m src.main
```

## Client Integration

See `/workspace/frontend/lib/websocket.ts` for the frontend WebSocket client implementation.

Example client usage:

```typescript
import { wsClient } from '@/lib/websocket';

// Connect
wsClient.connect('user-123');

// Subscribe to events
wsClient.subscribe('regime_change', (data) => {
  console.log('Regime changed:', data);
});

wsClient.subscribe('order_executed', (data) => {
  console.log('Order executed:', data);
});

// Disconnect when done
wsClient.disconnect();
```

## Dependencies

- FastAPI: WebSocket server
- uvicorn: ASGI server
- aiokafka: Redpanda consumer (via shared EventConsumer)
- pydantic-settings: Configuration management

## Related Services

- **Market Regime Service**: Publishes `regime_change` events
- **Risk Committee Service**: Publishes `risk_alert` events
- **Executor Service**: Publishes `order_executed` events
