# BLOASIS Database Migrations

This directory contains Alembic database migrations for the BLOASIS trading platform.

## Purpose

Alembic manages database schema versioning and migrations for PostgreSQL/TimescaleDB. It enables:

- Version control for database schema changes
- Safe rollback capability
- Team collaboration on schema changes
- Automated migration execution in CI/CD

## Prerequisites

1. Set the `DATABASE_URL` environment variable:
   ```bash
   # In .env file or environment
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bloasis
   ```

2. Ensure PostgreSQL/TimescaleDB is running

## Common Commands

### Create a New Migration

```bash
# Auto-generate migration from model changes (requires target_metadata)
alembic revision --autogenerate -m "add users table"

# Create empty migration for manual SQL
alembic revision -m "add custom index"
```

### Apply Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply next migration only
alembic upgrade +1

# Apply to specific revision
alembic upgrade abc123
```

### Rollback Migrations

```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123

# Rollback all migrations
alembic downgrade base
```

### View Migration Status

```bash
# Show current revision
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic history --verbose
```

## Directory Structure

```
alembic/
├── env.py              # Migration environment configuration
├── script.py.mako      # Migration file template
├── versions/           # Migration files
│   └── xxx_description.py
└── README.md           # This file
```

## Configuration

- **alembic.ini**: Main configuration file (in project root)
- **env.py**: Python configuration for async SQLAlchemy 2.0

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection URL | `postgresql+asyncpg://user:pass@host:5432/db` |

## Best Practices

1. **Always test migrations locally** before applying to production
2. **Use descriptive migration names**: `add_users_table`, not `update`
3. **Keep migrations atomic**: One logical change per migration
4. **Include rollback logic**: Implement both `upgrade()` and `downgrade()`
5. **Never edit applied migrations**: Create new migrations instead
6. **Back up production database** before running migrations

## Async Support

This configuration uses `postgresql+asyncpg://` driver for async SQLAlchemy 2.0 compatibility. The `env.py` is configured to run migrations asynchronously.

## Troubleshooting

### "DATABASE_URL not set" error
Set the environment variable or create a `.env` file with `DATABASE_URL`.

### Connection refused
Ensure PostgreSQL is running and accessible at the configured host/port.

### Migration conflicts
If multiple developers create migrations, use:
```bash
alembic merge heads -m "merge migrations"
```
