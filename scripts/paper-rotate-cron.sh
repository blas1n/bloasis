#!/bin/bash
# bloasis paper trading daily rotation — invoked by launchd
# (~/Library/LaunchAgents/dev.bloasis.paper-rotate.plist).
#
# Runs once per weekday morning KST (after US market close), generating
# fresh signals from latest close prices and submitting orders to the
# Alpaca paper account. Persists session/orders/equity_snapshots via
# the PR45-47 paper-trading layer.
#
# Edit SESSION_NAME / UNIVERSE / CONFIG as the smoke phase progresses.

set -euo pipefail

REPO=/Users/blasin/Works/bloasis/main
# 2026-09-29: switched from a hard-coded 50-name list to the SP500
# universe the edgar-rolling2 backtest measured. On 50 names the top
# decile was 4 stocks (~8% invested) and the held set never changed
# between annual 10-K filings, so the paper session could not test the
# backtest claim. New session name = clean equity series for the new
# universe; the old session was closed.
SESSION_NAME="edgar-rolling2-sp500-paper-2026-09"
CONFIG="configs/edgar-rolling2.yaml"
UNIVERSE="sp500"

cd "$REPO"

# Load secrets from .env (bloasis CLI doesn't auto-load).
# `set -a` exports every var sourced from .env until `set +a`.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# launchd's PATH is minimal; ensure uv + brew bins are discoverable.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Stamp every log line with KST timestamp for easier grepping later.
echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') paper-rotate START ====="

# Defensive: cancel any pending orders from a previous run that haven't
# filled yet. Without this, retries / weekend tests / mid-day re-runs
# stack BUYs and the next market open multiplies position size by N.
# The strategy submits a fresh batch every rotation; old pending orders
# don't represent the current signal anyway.
uv run python -c "
from dotenv import load_dotenv
load_dotenv()
from bloasis.broker import AlpacaBrokerAdapter
from alpaca.trading.requests import GetOrdersRequest
b = AlpacaBrokerAdapter(mode='paper')
orders = b._client.get_orders(filter=GetOrdersRequest(status='open'))
for o in orders:
    print(f'cancel pending: {o.symbol} {o.side} ({o.client_order_id})')
    b._client.cancel_order_by_id(o.id)
if orders:
    print(f'cancelled {len(orders)} stale orders before rotation')
"

uv run bloasis trade paper \
  --universe "$UNIVERSE" \
  -c "$CONFIG" \
  --session "$SESSION_NAME"

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') paper-rotate END   ====="
