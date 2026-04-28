#!/usr/bin/env bash
# Install the TA-Lib C library on Debian/Ubuntu systems.
#
# Uses upstream's prebuilt .deb release (ta-lib >= 0.6) which is required
# on modern GCC. The legacy 0.4.0 source build fails on GCC 14+ due to
# implicit-int errors, so we don't bother with it.
#
# Usage (CI / devcontainer):
#   sudo bash scripts/install-talib.sh
#
# Idempotent: skips install if /usr/lib/libta-lib.so already exists.

set -euo pipefail

TA_LIB_VERSION="${TA_LIB_VERSION:-0.6.4}"

if [[ -f /usr/lib/libta-lib.so || -f /usr/lib/x86_64-linux-gnu/libta-lib.so ]]; then
    echo "TA-Lib already installed."
    exit 0
fi

ARCH=$(dpkg --print-architecture)
DEB_URL="https://github.com/ta-lib/ta-lib/releases/download/v${TA_LIB_VERSION}/ta-lib_${TA_LIB_VERSION}_${ARCH}.deb"
WORKDIR="$(mktemp -d)"

echo "Fetching TA-Lib ${TA_LIB_VERSION} (${ARCH}) .deb..."
cd "$WORKDIR"
wget -q "$DEB_URL" -O ta-lib.deb

echo "Installing..."
# `dpkg -i` will pull in libc6 deps automatically on modern Ubuntu — no
# extra apt-get install needed. Use --no-triggers to keep things quick.
dpkg -i ta-lib.deb || apt-get install -y -f --no-install-recommends

cd /
rm -rf "$WORKDIR"

echo "TA-Lib ${TA_LIB_VERSION} installed."
