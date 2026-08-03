# Operational scripts

Helper scripts that don't ship as part of the bloasis CLI but make it
easier to run the package against real services on a daily cadence.

## `paper-rotate-cron.sh`

Daily paper-trading rotation entry point — invoked by launchd on the
host machine.

### What it does

1. Sources `.env` (so `bloasis` picks up `ALPACA_PAPER_API_KEY` /
   `ALPACA_PAPER_API_SECRET`).
2. Cancels any pending Alpaca paper orders left over from a previous
   run (idempotent — keeps the strategy from compounding when the
   wrapper is invoked twice in a window).
3. Calls `bloasis trade paper -s … -c … --session …` against the
   universe defined in `SYMBOLS` array.

### Setup on a fresh host

The launchd plist lives in `~/Library/LaunchAgents/`, not in the repo
— it's host-specific config (paths, schedule). The repo template:

```bash
# ~/Library/LaunchAgents/dev.bloasis.paper-rotate.plist
# (sample — adjust REPO path + schedule + log path for your host)
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.bloasis.paper-rotate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/blasin/Works/bloasis/main/scripts/paper-rotate-cron.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Mon-Fri 08:00 KST = 23:00 UTC = 18:00 EST / 19:00 EDT.
             2-3 hours after US market close so yfinance has settled
             today's bar regardless of DST regime. -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/blasin/Works/bloasis/main/logs/paper-rotate.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/blasin/Works/bloasis/main/logs/paper-rotate.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Then:

```bash
mkdir -p ~/Works/bloasis/main/logs
launchctl load ~/Library/LaunchAgents/dev.bloasis.paper-rotate.plist
launchctl list | grep bloasis        # verify registration
launchctl start dev.bloasis.paper-rotate  # one-shot test (optional)
tail -f ~/Works/bloasis/main/logs/paper-rotate.log
```

### Editing the universe

Edit `SYMBOLS` array at the top of `paper-rotate-cron.sh`. Keep
`SESSION_NAME` stable across edits so the equity curve in
`paper_equity_snapshots` continues across symbol changes — analysis
treats one session as one continuous strategy run.

## `mentions-track-cron.sh` (PR57)

Daily forward-tracking job for the mention event-study signal.

### What it does

1. `bloasis research mentions-fetch` — pulls new Truth Social posts.
2. `bloasis research mentions-extract --after 2024-01-01 --limit 1000`
   — runs the hybrid extractor (deterministic NER + Ollama sentiment)
   on un-stamped posts.
3. `bloasis research mentions-track --horizon 5 --extractor-version 3`
   — writes prediction rows for new negative + out-of-hours mentions,
   settles ripe predictions with realized fwd/baseline/excess.

All three steps are idempotent — safe to run twice / cron-overlap.
Designed as the prospective falsification feed for PR56's +1.32%
retrospective claim.

### Setup

Same launchd pattern as paper-rotate. Sample plist
(`~/Library/LaunchAgents/dev.bloasis.mentions-track.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.bloasis.mentions-track</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/blasin/Works/bloasis/main/scripts/mentions-track-cron.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Mon-Fri 09:00 KST — 1h after paper-rotate so the Ollama
             load doesn't collide with the Alpaca fetcher. -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/blasin/Works/bloasis/main/logs/mentions-track.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/blasin/Works/bloasis/main/logs/mentions-track.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Then:

```bash
launchctl load ~/Library/LaunchAgents/dev.bloasis.mentions-track.plist
launchctl start dev.bloasis.mentions-track  # one-shot smoke
tail -f ~/Works/bloasis/main/logs/mentions-track.log
```

### Reading the report

```bash
uv run bloasis research mentions-track-report
```

Predicted vs realized excess per bucket + combined. Sustained negative
realized excess after ~3 months → PR56 edge falsified. Comparable
positive → edge replicates forward.

## `weekly-report.sh` (PR61)

Monday-morning consolidated brief pushed to Telegram so the phone shows
paper + mention state without needing SSH into the Mac Mini.

### What it does

1. `scripts/measure_bloasis.py` — reads Alpaca paper API + local
   `bloasis.db` + `logs/mentions-track.log`, prints Markdown (equity /
   vol / Sharpe, FIFO round-trips, open positions, mention-tracker
   extraction counts, forward-prediction realized vs predicted, last 7
   cron runs).
2. `scripts/weekly-report.sh` — sources `.env`, calls the measurer,
   saves `logs/weekly-report-YYYYMMDD.md`, and pushes the report to
   Telegram in ≤3500-char chunks (sendMessage 4096-char limit).
3. `com.bloasis.report.plist` — launchd, Mon 09:30 KST (1h after
   `mentions-track`, 1h30m after `paper-rotate`, so today's data is fresh).

### Setup

Add to `.env` (already gitignored) — see `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=<@BotFather token>
TELEGRAM_CHAT_ID=<your chat_id from getUpdates>
```

Then create `~/Library/LaunchAgents/com.bloasis.report.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.bloasis.report</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/blasin/Works/bloasis/main/scripts/weekly-report.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>1</integer>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>30</integer>
    </dict>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>/Users/blasin/Works/bloasis/main/logs/launchd.report.out.log</string>
    <key>StandardErrorPath</key><string>/Users/blasin/Works/bloasis/main/logs/launchd.report.err.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.bloasis.report.plist
launchctl list | grep bloasis          # verify registration
bash scripts/weekly-report.sh          # one-shot smoke test to phone
```

### Note

Report is *sent* to Telegram, not stored there — telegram is a delivery
channel, not the archive. Archived Markdown lives in
`logs/weekly-report-*.md`.
