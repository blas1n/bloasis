#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

exec "$@"
