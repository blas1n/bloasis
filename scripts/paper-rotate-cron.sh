#!/bin/bash
# bloasis paper trading daily rotation — invoked by launchd
# (~/Library/LaunchAgents/dev.bloasis.paper-rotate.plist).
#
# Runs once per weekday morning KST (after US market close), generating
# fresh signals from latest close prices and submitting orders to the
# Alpaca paper account. Persists session/orders/equity_snapshots via
# the PR45-47 paper-trading layer.
#
# Edit SESSION_NAME / SYMBOLS / CONFIG as the smoke phase progresses.

set -euo pipefail

REPO=/Users/blasin/Works/bloasis/main
SESSION_NAME="edgar-rolling2-paper-2026-05"
CONFIG="configs/edgar-rolling2.yaml"

# Top 50 SP500 by market cap (as of 2024-12-31). Wider than top 20
# because top decile of 20 with EDGAR-eligible filter (≥ 2 prior 10-Ks)
# was producing only 1 buyable name; 50 should give 3-5 holdings for
# meaningful diversification + friction sample size.
#
# Edit when expanding the universe — keep DB-resident session NAME the
# same so equity continuity is preserved across symbol changes.
SYMBOLS=(
  NVDA AAPL MSFT GOOGL AMZN META BRK-B AVGO TSLA JPM
  WMT LLY V MA ORCL XOM COST NFLX JNJ HD
  PG BAC ABBV CRM CVX KO TMUS WFC CSCO MRK
  ADBE PEP MCD ABT TMO LIN ACN AMD GE BX
  IBM PM AXP CAT QCOM DIS T VZ INTC NOW
)

cd "$REPO"

# Load secrets from .env (bloasis CLI doesn't auto-load).
# `set -a` exports every var sourced from .env until `set +a`.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Build -s SYM args
SYM_ARGS=()
for sym in "${SYMBOLS[@]}"; do
  SYM_ARGS+=(-s "$sym")
done

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
  "${SYM_ARGS[@]}" \
  -c "$CONFIG" \
  --session "$SESSION_NAME"

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') paper-rotate END   ====="
