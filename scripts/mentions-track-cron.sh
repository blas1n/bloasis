#!/bin/bash
# bloasis mention forward-tracking daily job — invoked by launchd
# (~/Library/LaunchAgents/dev.bloasis.mentions-track.plist).
#
# Two passes per run, both idempotent:
#   1. mentions-fetch  — pulls new Truth Social posts into social_posts
#   2. mentions-extract — runs hybrid extractor over un-stamped posts
#                         (deterministic NER + LLM sentiment via Ollama)
#   3. mentions-track  — for any negative + AH/overnight mention with
#                        no prediction row yet, writes one. Then settles
#                        any prediction whose entry_date + horizon is
#                        past with realized fwd/baseline/excess.
#
# Re-running is a no-op on already-handled rows; safe to invoke twice.
# Output is the falsification feed for PR56's retrospective +1.32% claim.

set -euo pipefail

REPO=/Users/blasin/Works/bloasis/main
cd "$REPO"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') mentions-track START ====="

# Step 1: fetch new Truth Social archive (idempotent on post_id).
uv run bloasis research mentions-fetch

# Step 2: extract mentions on un-stamped posts. --after 2024-01-01
# keeps the LLM bill bounded to the same window as PR56's measurement.
# Local Ollama (llama3.2:3b) is free; this is the only LLM step.
uv run bloasis research mentions-extract \
  --limit 1000 \
  --after 2024-01-01

# Step 3: predict + settle pass. horizon=5 + extractor_version=3 match
# the PR56 retrospective. predicted_excess defaults to +1.32% (PR56
# pooled neg+OOT). Adjust only when re-baselining against a new study.
uv run bloasis research mentions-track \
  --horizon 5 \
  --extractor-version 3

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') mentions-track END   ====="
