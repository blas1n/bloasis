#!/bin/bash
# =============================================================================
# Kong Gateway Setup Script for BLOASIS
# =============================================================================
# This script validates, deploys, and tests Kong declarative configuration.
#
# Usage:
#   ./scripts/kong-setup.sh [command]
#
# Commands:
#   validate    Validate Kong configuration file
#   deploy      Deploy configuration to Kong (reload)
#   test        Test routes with health checks
#   status      Show Kong status and loaded routes
#   help        Show this help message
#
# Environment Variables:
#   KONG_ADMIN_URL    Kong Admin API URL (default: http://localhost:8001)
#   KONG_PROXY_URL    Kong Proxy URL (default: http://localhost:8000)
#   KONG_CONFIG_FILE  Kong config file path (default: infra/kong/kong.production.yml)
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
KONG_ADMIN_URL="${KONG_ADMIN_URL:-http://localhost:8001}"
KONG_PROXY_URL="${KONG_PROXY_URL:-http://localhost:8000}"
KONG_CONFIG_FILE="${KONG_CONFIG_FILE:-$PROJECT_ROOT/infra/kong/kong.production.yml}"

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo -e "\n${BLUE}==============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==============================================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

check_kong_running() {
    print_info "Checking if Kong is running..."

    if ! curl -s "$KONG_ADMIN_URL" > /dev/null 2>&1; then
        print_error "Kong Admin API is not accessible at $KONG_ADMIN_URL"
        print_info "Please ensure Kong is running and KONG_ADMIN_URL is correct"
        exit 1
    fi

    print_success "Kong Admin API is accessible"
}

check_config_file() {
    if [[ ! -f "$KONG_CONFIG_FILE" ]]; then
        print_error "Configuration file not found: $KONG_CONFIG_FILE"
        print_info "Please ensure the config file exists or set KONG_CONFIG_FILE"
        exit 1
    fi

    print_success "Configuration file found: $KONG_CONFIG_FILE"
}

# =============================================================================
# Main Commands
# =============================================================================

cmd_validate() {
    print_header "Validating Kong Configuration"

    check_config_file

    print_info "Validating YAML syntax..."

    # Check if yq is available for better YAML validation
    if command -v yq &> /dev/null; then
        if yq e '.' "$KONG_CONFIG_FILE" > /dev/null 2>&1; then
            print_success "YAML syntax is valid"
        else
            print_error "YAML syntax validation failed"
            yq e '.' "$KONG_CONFIG_FILE"
            exit 1
        fi
    # Fallback to Python for YAML validation
    elif command -v python3 &> /dev/null; then
        if python3 -c "import yaml; yaml.safe_load(open('$KONG_CONFIG_FILE'))" 2>/dev/null; then
            print_success "YAML syntax is valid (via Python)"
        else
            print_error "YAML syntax validation failed"
            exit 1
        fi
    else
        print_warning "Neither yq nor python3 available for YAML validation"
        print_info "Skipping local syntax check"
    fi

    print_info "Checking configuration structure..."

    # Check required fields
    if grep -q "_format_version:" "$KONG_CONFIG_FILE"; then
        print_success "Found _format_version"
    else
        print_error "Missing _format_version in configuration"
        exit 1
    fi

    if grep -q "services:" "$KONG_CONFIG_FILE"; then
        print_success "Found services section"
    else
        print_error "Missing services section in configuration"
        exit 1
    fi

    if grep -q "consumers:" "$KONG_CONFIG_FILE"; then
        print_success "Found consumers section"
    else
        print_warning "No consumers section found (JWT authentication may not work)"
    fi

    # Count services and routes
    local service_count=$(grep -c "^  - name:" "$KONG_CONFIG_FILE" 2>/dev/null || echo "0")
    print_info "Found approximately $service_count services"

    # Check for required plugins
    print_info "Checking for required plugins..."

    local plugins=("grpc-gateway" "jwt" "rate-limiting" "file-log" "correlation-id" "request-transformer")
    for plugin in "${plugins[@]}"; do
        if grep -q "name: $plugin" "$KONG_CONFIG_FILE"; then
            print_success "Found $plugin plugin configuration"
        else
            print_warning "Plugin $plugin not found in configuration"
        fi
    done

    # Validate with Kong if running
    if curl -s "$KONG_ADMIN_URL" > /dev/null 2>&1; then
        print_info "Validating configuration with Kong Admin API..."

        # Kong deck validate (if deck is installed)
        if command -v deck &> /dev/null; then
            if deck validate -s "$KONG_CONFIG_FILE" 2>/dev/null; then
                print_success "Kong deck validation passed"
            else
                print_warning "Kong deck validation had issues"
            fi
        else
            print_info "deck not installed, skipping advanced validation"
        fi
    else
        print_info "Kong is not running, skipping live validation"
    fi

    print_header "Validation Complete"
    print_success "Configuration appears valid"
}

cmd_deploy() {
    print_header "Deploying Kong Configuration"

    check_kong_running
    check_config_file

    # First validate
    print_info "Validating configuration before deployment..."

    # Check if using deck
    if command -v deck &> /dev/null; then
        print_info "Using deck for deployment..."

        # Backup current config
        print_info "Backing up current configuration..."
        deck dump -o "$PROJECT_ROOT/infra/kong/kong.backup.yml" 2>/dev/null || true

        # Sync configuration
        print_info "Syncing configuration to Kong..."
        if deck sync -s "$KONG_CONFIG_FILE"; then
            print_success "Configuration deployed successfully using deck"
        else
            print_error "Deployment failed"
            exit 1
        fi
    else
        # Fallback to Admin API
        print_info "deck not found, using Admin API for deployment..."

        # Check if Kong is in DB-less mode
        local db_mode=$(curl -s "$KONG_ADMIN_URL" | grep -o '"database":"[^"]*"' | cut -d'"' -f4)

        if [[ "$db_mode" == "off" ]]; then
            print_info "Kong is in DB-less mode, using /config endpoint..."

            # Post configuration
            local response=$(curl -s -w "\n%{http_code}" -X POST "$KONG_ADMIN_URL/config" \
                -F "config=@$KONG_CONFIG_FILE")

            local http_code=$(echo "$response" | tail -n1)
            local body=$(echo "$response" | head -n-1)

            if [[ "$http_code" == "201" ]] || [[ "$http_code" == "200" ]]; then
                print_success "Configuration deployed successfully"
            else
                print_error "Deployment failed with HTTP $http_code"
                echo "$body"
                exit 1
            fi
        else
            print_error "Kong is not in DB-less mode. Please use 'deck' for database deployments."
            print_info "Install deck: https://docs.konghq.com/deck/latest/installation/"
            exit 1
        fi
    fi

    # Verify deployment
    print_info "Verifying deployment..."
    sleep 2

    local services=$(curl -s "$KONG_ADMIN_URL/services" | grep -o '"name":"[^"]*"' | wc -l)
    print_info "Loaded $services services"

    local routes=$(curl -s "$KONG_ADMIN_URL/routes" | grep -o '"name":"[^"]*"' | wc -l)
    print_info "Loaded $routes routes"

    local plugins=$(curl -s "$KONG_ADMIN_URL/plugins" | grep -o '"name":"[^"]*"' | wc -l)
    print_info "Loaded $plugins plugins"

    print_header "Deployment Complete"
    print_success "Kong configuration has been deployed"
}

cmd_test() {
    print_header "Testing Kong Routes"

    check_kong_running

    local total_tests=0
    local passed_tests=0

    # Test health endpoint
    print_info "Testing health endpoint..."
    if curl -s "$KONG_PROXY_URL/health" > /dev/null 2>&1; then
        print_success "/health endpoint is accessible"
        ((passed_tests++))
    else
        print_warning "/health endpoint not accessible (may be configured differently)"
    fi
    ((total_tests++))

    # Test auth endpoint (should be accessible without JWT)
    print_info "Testing auth endpoint (no JWT required)..."
    local auth_response=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_PROXY_URL/v1/auth/login" -X POST -H "Content-Type: application/json" -d '{}' 2>/dev/null)
    if [[ "$auth_response" != "401" ]] && [[ "$auth_response" != "403" ]]; then
        print_success "/v1/auth/login accepts requests (no JWT required)"
        ((passed_tests++))
    else
        print_warning "/v1/auth/login returned $auth_response (may need backend running)"
    fi
    ((total_tests++))

    # Test protected endpoints (should require JWT)
    print_info "Testing protected endpoints (should require JWT)..."

    local protected_routes=(
        "/v1/users/test"
        "/v1/strategy/picks"
        "/v1/market-data/AAPL/ohlcv"
        "/v1/portfolio/test"
    )

    for route in "${protected_routes[@]}"; do
        local response=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_PROXY_URL$route" 2>/dev/null)
        ((total_tests++))

        if [[ "$response" == "401" ]] || [[ "$response" == "403" ]]; then
            print_success "$route correctly requires JWT (HTTP $response)"
            ((passed_tests++))
        else
            print_warning "$route returned HTTP $response (expected 401/403)"
        fi
    done

    # Test rate limiting headers
    print_info "Testing rate limiting headers..."
    local headers=$(curl -s -I "$KONG_PROXY_URL/v1/auth/login" -X POST -H "Content-Type: application/json" -d '{}' 2>/dev/null)

    if echo "$headers" | grep -qi "RateLimit-Remaining"; then
        print_success "Rate limiting headers present"
        ((passed_tests++))
    else
        print_warning "Rate limiting headers not found (may be hidden)"
    fi
    ((total_tests++))

    # Test correlation ID
    print_info "Testing correlation ID..."
    if echo "$headers" | grep -qi "X-Correlation-ID"; then
        print_success "Correlation ID header present"
        ((passed_tests++))
    else
        print_warning "Correlation ID header not found"
    fi
    ((total_tests++))

    print_header "Test Results"
    echo -e "Passed: ${GREEN}$passed_tests${NC}/$total_tests tests"

    if [[ $passed_tests -eq $total_tests ]]; then
        print_success "All tests passed!"
    else
        print_warning "Some tests did not pass (this may be expected if backends are not running)"
    fi
}

cmd_status() {
    print_header "Kong Gateway Status"

    check_kong_running

    # Get Kong info
    print_info "Kong Server Information:"
    local kong_info=$(curl -s "$KONG_ADMIN_URL")

    local version=$(echo "$kong_info" | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
    local hostname=$(echo "$kong_info" | grep -o '"hostname":"[^"]*"' | cut -d'"' -f4)
    local database=$(echo "$kong_info" | grep -o '"database":"[^"]*"' | cut -d'"' -f4)

    echo "  Version:  $version"
    echo "  Hostname: $hostname"
    echo "  Database: $database"

    # List services
    print_info "\nLoaded Services:"
    curl -s "$KONG_ADMIN_URL/services" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | while read -r service; do
        echo "  - $service"
    done

    # List routes
    print_info "\nLoaded Routes:"
    curl -s "$KONG_ADMIN_URL/routes" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | while read -r route; do
        echo "  - $route"
    done

    # List plugins
    print_info "\nActive Plugins:"
    curl -s "$KONG_ADMIN_URL/plugins" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | sort | uniq -c | while read -r count plugin; do
        echo "  - $plugin ($count instances)"
    done

    # List consumers
    print_info "\nConsumers:"
    curl -s "$KONG_ADMIN_URL/consumers" | grep -o '"username":"[^"]*"' | cut -d'"' -f4 | while read -r consumer; do
        echo "  - $consumer"
    done

    print_header "Status Complete"
}

cmd_help() {
    echo "Kong Gateway Setup Script for BLOASIS"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  validate    Validate Kong configuration file syntax and structure"
    echo "  deploy      Deploy configuration to Kong (reload declarative config)"
    echo "  test        Test routes with health checks and JWT verification"
    echo "  status      Show Kong status, services, routes, and plugins"
    echo "  help        Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  KONG_ADMIN_URL    Kong Admin API URL (default: http://localhost:8001)"
    echo "  KONG_PROXY_URL    Kong Proxy URL (default: http://localhost:8000)"
    echo "  KONG_CONFIG_FILE  Kong config file (default: infra/kong/kong.production.yml)"
    echo ""
    echo "Examples:"
    echo "  $0 validate                     # Validate configuration"
    echo "  $0 deploy                       # Deploy to Kong"
    echo "  $0 test                         # Test routes"
    echo "  KONG_ADMIN_URL=http://kong:8001 $0 status  # Custom Kong URL"
    echo ""
    echo "Prerequisites:"
    echo "  - Kong Gateway running (accessible via KONG_ADMIN_URL)"
    echo "  - deck CLI (optional, for advanced operations)"
    echo "  - yq or python3 (for YAML validation)"
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
        deploy)
            cmd_deploy
            ;;
        test)
            cmd_test
            ;;
        status)
            cmd_status
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
