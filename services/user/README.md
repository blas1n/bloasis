# BLOASIS User Service

User profile, trading preferences, and broker configuration management service.

## Overview

The User Service manages:
- User account CRUD operations
- User trading preferences (risk profile, position sizing, sectors)
- Password hashing with bcrypt
- Credential validation for Auth Service
- Broker configuration (Alpaca API keys) with Fernet encryption
- Broker connection status check (via Executor Service)

## Architecture

- **gRPC only** - Envoy Gateway handles HTTP-to-gRPC transcoding
- **PostgreSQL** - User data + encrypted broker credentials
- **Redis** - Preferences caching (1-hour TTL)
- **bcrypt** - Password hashing
- **Fernet** - Symmetric encryption for broker API keys at rest
- **Executor Client** - gRPC client for broker status check

## API

### gRPC Methods

| Method | Description | HTTP (via Envoy) |
|--------|-------------|-----------------|
| `GetUser` | Get user by ID | `GET /v1/users/{user_id}` |
| `CreateUser` | Create new user | `POST /v1/users` |
| `ValidateCredentials` | Validate email/password | Internal only |
| `GetUserPreferences` | Get user preferences | `GET /v1/users/{user_id}/preferences` |
| `UpdateUserPreferences` | Update preferences | `PATCH /v1/users/{user_id}/preferences` |
| `StartTrading` | Start AI auto-trading | `POST /v1/users/{user_id}/trading/start` |
| `StopTrading` | Stop AI auto-trading | `POST /v1/users/{user_id}/trading/stop` |
| `GetTradingStatus` | Get trading status | `GET /v1/users/{user_id}/trading/status` |
| `GetBrokerConfig` | Get broker credentials | Internal only (Executor) |
| `UpdateBrokerConfig` | Save broker credentials | `PATCH /v1/settings/broker` |
| `GetBrokerStatus` | Check broker connection | `GET /v1/settings/broker/status` |

### Broker Configuration

Alpaca API keys are stored encrypted in the `user_data.broker_config` table using Fernet symmetric encryption.

**Save credentials (frontend)**:
```bash
PATCH /v1/settings/broker
{
  "alpacaApiKey": "PKXXXX...",
  "alpacaSecretKey": "xxxxx...",
  "paper": true
}
```

**Check connection status**:
```bash
GET /v1/settings/broker/status
# Response:
{
  "configured": true,
  "connected": true,
  "equity": 100000.0,
  "cash": 50000.0
}
```

The status check calls Executor Service `GetAccount` to verify the keys work with Alpaca.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | 50052 | gRPC server port |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `REDIS_HOST` / `REDIS_PORT` | redis:6379 | Redis for caching |
| `PREFERENCES_CACHE_TTL` | 3600 | Cache TTL in seconds |
| `CREDENTIAL_ENCRYPTION_KEY` | - | Fernet key for encrypting broker credentials |
| `EXECUTOR_HOST` / `EXECUTOR_PORT` | executor:50060 | Executor Service for broker status |

Generate encryption key:
```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

## Development

```bash
# Install dependencies
cd services/user
uv pip install -e ".[dev]"

# Run tests
pytest --cov --cov-fail-under=80

# Lint check
ruff check src/
```

## Database Schema

```sql
-- user_data.users
CREATE TABLE user_data.users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- user_data.user_preferences
CREATE TABLE user_data.user_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(user_id),
    risk_profile VARCHAR(50),
    max_portfolio_risk DECIMAL(5,4),
    max_position_size DECIMAL(5,4),
    preferred_sectors TEXT[],
    enable_notifications BOOLEAN,
    updated_at TIMESTAMPTZ
);

-- user_data.broker_config (global settings - Phase 1)
CREATE TABLE user_data.broker_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Security

- Passwords are hashed with bcrypt (salt rounds: 12)
- Broker API keys are encrypted with Fernet (AES-128-CBC) at rest
- `CREDENTIAL_ENCRYPTION_KEY` must be kept secret and backed up
- API keys and secrets are never logged
- Input validation on all endpoints
- Financial values use Decimal for precision
