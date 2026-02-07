#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

SERVICE=$1
LINES=${2:-100}

if [ -z "$SERVICE" ]; then
    echo "📋 Showing last $LINES lines of all services..."
    docker-compose logs --tail=$LINES -f
else
    echo "📋 Showing last $LINES lines of $SERVICE..."
    docker-compose logs --tail=$LINES -f $SERVICE
fi
