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
