#!/bin/bash
# =============================================================================
# Envoy Gateway Setup Script for BLOASIS
# =============================================================================
# This script validates, checks status, and tests the Envoy gateway configuration.
#
# Usage:
#   ./scripts/envoy-setup.sh [command]
#
# Commands:
#   validate    Validate Envoy configuration file (YAML syntax + structure)
#   status      Show Envoy status: clusters, listeners, and recent stats
#   test        Test routes via the proxy with health checks
#   help        Show this help message
#
# Environment Variables:
#   ENVOY_ADMIN_URL   Envoy Admin API URL (default: http://localhost:9901)
#   ENVOY_PROXY_URL   Envoy Proxy URL     (default: http://localhost:8000)
#   ENVOY_CONFIG_FILE Envoy config file   (default: infra/envoy/envoy.yaml)
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENVOY_ADMIN_URL="${ENVOY_ADMIN_URL:-http://localhost:9901}"
ENVOY_PROXY_URL="${ENVOY_PROXY_URL:-http://localhost:8000}"
ENVOY_CONFIG_FILE="${ENVOY_CONFIG_FILE:-$PROJECT_ROOT/infra/envoy/envoy.yaml}"

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo -e "\n${BLUE}==============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==============================================================================${NC}\n"
}

print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }

check_envoy_running() {
    print_info "Checking if Envoy is running..."

    if ! curl -s "$ENVOY_ADMIN_URL/ready" > /dev/null 2>&1; then
        print_error "Envoy Admin API is not accessible at $ENVOY_ADMIN_URL"
        print_info "Please ensure Envoy is running and ENVOY_ADMIN_URL is correct"
        print_info "Start with: docker compose up envoy"
        exit 1
    fi

    print_success "Envoy Admin API is accessible"
}

check_config_file() {
    if [[ ! -f "$ENVOY_CONFIG_FILE" ]]; then
        print_error "Configuration file not found: $ENVOY_CONFIG_FILE"
        print_info "Expected at: infra/envoy/envoy.yaml"
        exit 1
    fi

    print_success "Configuration file found: $ENVOY_CONFIG_FILE"
}

# =============================================================================
# Main Commands
# =============================================================================

cmd_validate() {
    print_header "Validating Envoy Configuration"

    check_config_file

    print_info "Validating YAML syntax..."

    if command -v yq &> /dev/null; then
        if yq e '.' "$ENVOY_CONFIG_FILE" > /dev/null 2>&1; then
            print_success "YAML syntax is valid"
        else
            print_error "YAML syntax validation failed"
            yq e '.' "$ENVOY_CONFIG_FILE"
            exit 1
        fi
    elif command -v python3 &> /dev/null; then
        if python3 -c "import yaml; yaml.safe_load(open('$ENVOY_CONFIG_FILE'))" 2>/dev/null; then
            print_success "YAML syntax is valid (via Python)"
        else
            print_error "YAML syntax validation failed"
            python3 -c "import yaml; yaml.safe_load(open('$ENVOY_CONFIG_FILE'))"
            exit 1
        fi
    else
        print_warning "Neither yq nor python3 available — skipping YAML syntax check"
    fi

    print_info "Checking configuration structure..."

    # Required top-level sections
    local required_sections=("admin" "static_resources")
    for section in "${required_sections[@]}"; do
        if grep -q "^${section}:" "$ENVOY_CONFIG_FILE"; then
            print_success "Found '$section' section"
        else
            print_error "Missing required section: $section"
            exit 1
        fi
    done

    # Check listeners and clusters
    if grep -q "listeners:" "$ENVOY_CONFIG_FILE"; then
        print_success "Found listeners"
    else
        print_error "No listeners defined"
        exit 1
    fi

    if grep -q "clusters:" "$ENVOY_CONFIG_FILE"; then
        local cluster_count
        cluster_count=$(grep -c "^    - name:" "$ENVOY_CONFIG_FILE" 2>/dev/null || echo "0")
        print_success "Found clusters section ($cluster_count clusters)"
    else
        print_error "No clusters defined"
        exit 1
    fi

    # Check for gRPC-JSON transcoder
    if grep -q "grpc_json_transcoder" "$ENVOY_CONFIG_FILE"; then
        print_success "gRPC-JSON transcoder filter configured"
    else
        print_warning "grpc_json_transcoder filter not found (REST transcoding may not work)"
    fi

    # Check proto descriptor
    if grep -q "proto_descriptor:" "$ENVOY_CONFIG_FILE"; then
        local proto_path
        proto_path=$(grep "proto_descriptor:" "$ENVOY_CONFIG_FILE" | awk '{print $2}' | tr -d '"')
        print_success "Proto descriptor configured: $proto_path"
    else
        print_warning "No proto_descriptor configured — gRPC-JSON transcoding will not work"
    fi

    # Check CORS filter
    if grep -q "envoy.filters.http.cors" "$ENVOY_CONFIG_FILE"; then
        print_success "CORS filter configured"
    else
        print_warning "CORS filter not found"
    fi

    # Check proto.pb file exists
    local proto_pb="$PROJECT_ROOT/infra/envoy/proto.pb"
    if [[ -f "$proto_pb" ]]; then
        print_success "Proto descriptor binary found: $proto_pb"
    else
        print_warning "Proto descriptor binary missing: $proto_pb"
        print_info "Generate with: make proto-generate"
    fi

    print_header "Validation Complete"
    print_success "Configuration appears valid"
}

cmd_status() {
    print_header "Envoy Gateway Status"

    check_envoy_running

    # Server info
    print_info "Envoy Server Info:"
    local server_info
    server_info=$(curl -s "$ENVOY_ADMIN_URL/server_info" 2>/dev/null)
    if [[ -n "$server_info" ]]; then
        echo "$server_info" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"  Version:  {d.get('version', 'unknown')}\")
    print(f\"  State:    {d.get('state', 'unknown')}\")
    print(f\"  Hot restart version: {d.get('hot_restart_version', 'unknown')}\")
except Exception:
    print('  (could not parse server info)')
" 2>/dev/null || echo "  (python3 not available for parsing)"
    fi

    # Listeners
    print_info "\nActive Listeners:"
    curl -s "$ENVOY_ADMIN_URL/listeners" 2>/dev/null | tr ',' '\n' | grep -o '"[^"]*::[^"]*"' | while read -r listener; do
        echo "  - $listener"
    done || echo "  (none)"

    # Clusters
    print_info "\nCluster Health:"
    curl -s "$ENVOY_ADMIN_URL/clusters" 2>/dev/null | grep "health_flags" | while read -r line; do
        echo "  $line"
    done || echo "  (none)"

    # Stats summary (request counts)
    print_info "\nRequest Stats (downstream):"
    curl -s "$ENVOY_ADMIN_URL/stats" 2>/dev/null | grep -E "^http\.ingress_http\.(rq_total|rq_2xx|rq_4xx|rq_5xx)" | while read -r stat; do
        echo "  $stat"
    done || echo "  (none)"

    print_header "Status Complete"
}

cmd_test() {
    print_header "Testing Envoy Routes"

    check_envoy_running

    local total_tests=0
    local passed_tests=0

    # Test admin /ready endpoint
    print_info "Testing Envoy admin /ready..."
    local ready_response
    ready_response=$(curl -s -o /dev/null -w "%{http_code}" "$ENVOY_ADMIN_URL/ready" 2>/dev/null)
    ((total_tests++))
    if [[ "$ready_response" == "200" ]]; then
        print_success "Envoy admin /ready returned HTTP 200"
        ((passed_tests++))
    else
        print_warning "Envoy admin /ready returned HTTP $ready_response"
    fi

    # Test each service route (expect 200 or gRPC error, not 404)
    local routes=(
        "/v1/market-regime/current"
        "/v1/market-data/AAPL/ohlcv"
        "/v1/strategy/picks"
        "/v1/portfolio/test"
        "/v1/auth/login"
        "/v1/users/test"
        "/v1/classification/sector"
        "/v1/risk/committee"
    )

    print_info "\nTesting proxy routes (checking for routing, not backend availability)..."
    for route in "${routes[@]}"; do
        local response
        response=$(curl -s -o /dev/null -w "%{http_code}" "$ENVOY_PROXY_URL$route" 2>/dev/null)
        ((total_tests++))

        # 404 means no route match; anything else means Envoy routed the request
        if [[ "$response" != "404" ]]; then
            print_success "$route → HTTP $response (route matched)"
            ((passed_tests++))
        else
            print_warning "$route → HTTP 404 (no route match — check envoy.yaml)"
        fi
    done

    # Test CORS headers
    print_info "\nTesting CORS headers..."
    local cors_headers
    cors_headers=$(curl -s -I -X OPTIONS "$ENVOY_PROXY_URL/v1/market-regime/current" \
        -H "Origin: http://localhost:3000" \
        -H "Access-Control-Request-Method: GET" 2>/dev/null)
    ((total_tests++))

    if echo "$cors_headers" | grep -qi "access-control-allow-origin"; then
        print_success "CORS headers present"
        ((passed_tests++))
    else
        print_warning "CORS headers not found (check Envoy cors filter config)"
    fi

    print_header "Test Results"
    echo -e "Passed: ${GREEN}$passed_tests${NC}/$total_tests tests"

    if [[ $passed_tests -eq $total_tests ]]; then
        print_success "All tests passed!"
    else
        print_warning "Some tests did not pass (backends may not be running — route matching is what matters)"
    fi
}

cmd_help() {
    echo "Envoy Gateway Setup Script for BLOASIS"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  validate    Validate Envoy configuration file (YAML syntax + structure)"
    echo "  status      Show Envoy status: server info, clusters, listeners, stats"
    echo "  test        Test routes via the proxy and verify CORS headers"
    echo "  help        Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  ENVOY_ADMIN_URL    Envoy Admin API URL (default: http://localhost:9901)"
    echo "  ENVOY_PROXY_URL    Envoy Proxy URL     (default: http://localhost:8000)"
    echo "  ENVOY_CONFIG_FILE  Envoy config file   (default: infra/envoy/envoy.yaml)"
    echo ""
    echo "Examples:"
    echo "  $0 validate                                  # Validate configuration"
    echo "  $0 status                                    # Show Envoy status"
    echo "  $0 test                                      # Test routes"
    echo "  ENVOY_ADMIN_URL=http://envoy:9901 $0 status  # Custom Envoy URL"
    echo ""
    echo "Reload configuration:"
    echo "  Envoy static config requires a container restart to reload:"
    echo "  docker compose restart envoy"
    echo ""
    echo "Prerequisites:"
    echo "  - Envoy container running (accessible via ENVOY_ADMIN_URL)"
    echo "  - Proto descriptor generated: make proto-generate"
    echo "  - yq or python3 for YAML validation"
}

# =============================================================================
# Main Entry Point
# =============================================================================

main() {
    local command="${1:-help}"

    case "$command" in
        validate)
            cmd_validate
            ;;
        status)
            cmd_status
            ;;
        test)
            cmd_test
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            print_error "Unknown command: $command"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
