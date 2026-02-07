# BLOASIS User Service

User profile and trading preferences management service.

## Overview

The User Service manages:
- User account CRUD operations
- User trading preferences (risk profile, position sizing, sectors)
- Password hashing with bcrypt
- Credential validation for Auth Service

## Architecture

- **gRPC only** - Kong Gateway handles HTTP-to-gRPC transcoding
- **PostgreSQL** - User data persistence
- **Redis** - Preferences caching (1-hour TTL)
- **bcrypt** - Password hashing

## API

### gRPC Methods

| Method | Description | HTTP (via Kong) |
|--------|-------------|-----------------|
| `GetUser` | Get user by ID | `GET /v1/users/{user_id}` |
| `CreateUser` | Create new user | `POST /v1/users` |
| `ValidateCredentials` | Validate email/password | Internal only |
| `GetUserPreferences` | Get user preferences | `GET /v1/users/{user_id}/preferences` |
| `UpdateUserPreferences` | Update preferences | `PATCH /v1/users/{user_id}/preferences` |

### User Preferences

```json
{
  "user_id": "uuid",
  "risk_profile": "conservative|moderate|aggressive",
  "max_portfolio_risk": "0.20",
  "max_position_size": "0.10",
  "preferred_sectors": ["Technology", "Healthcare"],
  "enable_notifications": true
}
```

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `GRPC_PORT`: gRPC server port (default: 50052)
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_HOST/PORT`: Redis for caching
- `PREFERENCES_CACHE_TTL`: Cache TTL in seconds (default: 3600)

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
```

## Security

- Passwords are hashed with bcrypt (salt rounds: 12)
- API keys and secrets are never logged
- Input validation on all endpoints
- Financial values use Decimal for precision
