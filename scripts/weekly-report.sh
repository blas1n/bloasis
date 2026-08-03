#!/usr/bin/env bash
# Bloasis weekly status report — pushed to Telegram for mobile.
#
# Fires from launchd `com.bloasis.report.plist` (Mon 09:30 KST, after the daily
# paper-rotate + mentions-track jobs). Measures both tracks on the local Mac
# Mini (only place with Alpaca creds + bloasis.db) and sends the Markdown
# report to Telegram so it's readable from the phone.
#
# Requires in .env:
#   ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET  (paper account read)
#   TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID           (delivery)

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p logs

[ -f .env ] || { echo "ERROR: .env not found in $PROJECT_DIR" >&2; exit 1; }
# `set -a` exports everything sourced from .env until `set +a`.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

REPORT_FILE="logs/weekly-report-$(date +%Y%m%d).md"

# 1) measure -> report text (also saved locally as archive)
if ! REPORT="$(uv run python scripts/measure_bloasis.py 2>report.err)"; then
  REPORT="⚠️ Bloasis weekly report FAILED: $(tail -3 report.err | tr '\n' ' ')"
fi
rm -f report.err
printf '%s\n' "$REPORT" > "$REPORT_FILE"

# 2) push to Telegram (chunk to Telegram's 4096-char sendMessage limit)
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
  # Split on line boundaries, cap ~3500 chars per chunk to stay under the
  # 4096-char sendMessage limit even after URL-encoding overhead.
  printf '%s\n' "$REPORT" | awk '
    { buf = buf $0 "\n";
      if (length(buf) > 3500) { printf "%s\x1e", buf; buf="" } }
    END { if (length(buf)) printf "%s", buf }' | while IFS= read -r -d $'\x1e' chunk || [ -n "$chunk" ]; do
    curl -s -X POST "$API" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=${chunk}" \
      --data-urlencode "parse_mode=Markdown" \
      --data-urlencode "disable_web_page_preview=true" >/dev/null || true
  done
  echo "pushed report to Telegram chat ${TELEGRAM_CHAT_ID}"
else
  echo "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — report only in $REPORT_FILE" >&2
fi

echo "report: $PROJECT_DIR/$REPORT_FILE"
