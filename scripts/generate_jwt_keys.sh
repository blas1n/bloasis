#!/bin/bash
# Generate RSA key pair for JWT signing (RS256 algorithm)
#
# This script generates:
# - Private key for signing tokens (Auth Service only)
# - Public key for verifying tokens (Envoy Gateway and other services)
#
# Usage:
#   ./scripts/generate_jwt_keys.sh
#   ./scripts/generate_jwt_keys.sh --force  # Overwrite existing keys

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
KEYS_DIR="$PROJECT_ROOT/infra/keys"
PRIVATE_KEY="$KEYS_DIR/jwt-private.pem"
PUBLIC_KEY="$KEYS_DIR/jwt-public.pem"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if keys already exist
if [[ -f "$PRIVATE_KEY" || -f "$PUBLIC_KEY" ]]; then
    if [[ "$1" != "--force" ]]; then
        echo -e "${YELLOW}Warning: JWT keys already exist in $KEYS_DIR${NC}"
        echo "Use --force to overwrite existing keys."
        exit 1
    fi
    echo -e "${YELLOW}Overwriting existing keys...${NC}"
fi

# Create keys directory if it doesn't exist
mkdir -p "$KEYS_DIR"

echo "Generating RSA-2048 key pair for JWT signing..."

# Generate private key
openssl genrsa -out "$PRIVATE_KEY" 2048 2>/dev/null

# Extract public key from private key
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY" 2>/dev/null

# Set restrictive permissions on private key
chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"

echo -e "${GREEN}JWT keys generated successfully!${NC}"
echo ""
echo "Keys location:"
echo "  Private key: $PRIVATE_KEY"
echo "  Public key:  $PUBLIC_KEY"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo "  - Both keys are gitignored and should be generated per environment"
echo "  - NEVER commit private or public keys to git"
echo "  - In production, use secure secrets management (Vault, AWS Secrets Manager, etc.)"
echo ""
echo "Environment variables to set:"
echo "  JWT_PRIVATE_KEY_PATH=$PRIVATE_KEY"
echo "  JWT_PUBLIC_KEY_PATH=$PUBLIC_KEY"
echo "  JWT_ALGORITHM=RS256"
