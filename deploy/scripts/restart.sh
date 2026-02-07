#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

SERVICE=$1

if [ -z "$SERVICE" ]; then
    echo "🔄 Restarting all services..."
    docker-compose restart
else
    echo "🔄 Restarting $SERVICE..."
    docker-compose restart $SERVICE
fi

echo "✅ Restart complete."
