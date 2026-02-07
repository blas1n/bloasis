#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

echo "🛑 Stopping BLOASIS services..."

# Stop all profiles
docker-compose --profile full down

echo "✅ All services stopped."
