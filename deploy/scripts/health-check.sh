#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

echo "🏥 BLOASIS Health Check"
echo "========================"

# Function to check container health
check_service() {
    local service=$1
    local status=$(docker-compose ps $service --format json 2>/dev/null | jq -r '.[0].Health // .[0].State' 2>/dev/null)

    if [ -z "$status" ] || [ "$status" = "null" ]; then
        status=$(docker-compose ps $service --format "{{.Status}}" 2>/dev/null | head -1)
    fi

    if [[ "$status" == *"healthy"* ]] || [[ "$status" == *"Up"* ]]; then
        echo "  ✅ $service: running"
    elif [[ "$status" == *"starting"* ]]; then
        echo "  ⏳ $service: starting"
    else
        echo "  ❌ $service: $status"
    fi
}

# Infrastructure
echo ""
echo "Infrastructure:"
for svc in postgres redis redpanda consul kong; do
    check_service $svc
done

# Microservices
echo ""
echo "Microservices:"
for svc in market-regime user market-data classification strategy auth portfolio backtesting risk-committee executor notification; do
    check_service $svc
done

# Optional services (monitoring profile)
echo ""
echo "Monitoring (if enabled):"
for svc in prometheus grafana; do
    check_service $svc
done

# Frontend (full profile)
echo ""
echo "Frontend (if enabled):"
check_service frontend

echo ""
echo "========================"
echo "Done."
