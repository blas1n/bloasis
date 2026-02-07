#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

echo "🚀 BLOASIS Deployment Starting..."

# Check .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Copy .env.example to .env and configure it."
    exit 1
fi

# Parse arguments
PROFILE=""
BUILD=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --monitoring)
            PROFILE="--profile monitoring"
            shift
            ;;
        --full)
            PROFILE="--profile full"
            shift
            ;;
        --build)
            BUILD="--build"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Generate proto files if needed
echo "📦 Checking proto files..."
if [ ! -d "../shared/generated" ] || [ -z "$(ls -A ../shared/generated 2>/dev/null)" ]; then
    echo "Generating proto files..."
    cd .. && buf generate && cd deploy
fi

# Build and start
echo "🔨 Building and starting services..."
docker-compose $PROFILE up -d $BUILD

echo "⏳ Waiting for services to be healthy..."
sleep 15

# Health check
./scripts/health-check.sh

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Services:"
echo "  - API Gateway: http://localhost:8000"
echo "  - Consul UI:   http://localhost:8500"
if [[ "$PROFILE" == *"monitoring"* ]] || [[ "$PROFILE" == *"full"* ]]; then
    echo "  - Grafana:     http://localhost:3001"
    echo "  - Prometheus:  http://localhost:9090"
fi
if [[ "$PROFILE" == *"full"* ]]; then
    echo "  - Frontend:    http://localhost:3000"
fi
