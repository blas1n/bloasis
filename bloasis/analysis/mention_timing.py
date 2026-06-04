"""Classify a social-post timestamp relative to the US trading session.

For an event study of mentions, WHEN the post was published determines
where its price impact lives:

  IN_HOURS    — published during a US session. Some intraday impact
                already visible in that day's bar; entry modeled as
                next-day open (matches our backtester / live cron).
  AFTER_HOURS — published the same calendar day, after 16:00 ET close.
                Whole reaction compresses into the next session's gap.
  OVERNIGHT   — published before that day's 09:30 ET open (e.g. early
                morning ET). Entry is the SAME day's open.
  WEEKEND     — Saturday or Sunday (any hour). Entry is Monday open.
                3-day weekend gap structurally larger than overnight.

The bucket is what lets us split "gap" (HFT-captured) from "intraday
+ forward" (retail-feasible) in the downstream event study.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# US regular session hours in ET.
_SESSION_OPEN_HOUR = 9
_SESSION_OPEN_MINUTE = 30
_SESSION_CLOSE_HOUR = 16  # 16:00:00 ET


class MentionTiming(StrEnum):
    IN_HOURS = "in_hours"
    AFTER_HOURS = "after_hours"
    OVERNIGHT = "overnight"
    WEEKEND = "weekend"


def _in_session(et_dt: datetime) -> bool:
    """09:30 ET (inclusive) to 16:00 ET (exclusive) on a weekday."""
    h, m = et_dt.hour, et_dt.minute
    if h < _SESSION_OPEN_HOUR or (h == _SESSION_OPEN_HOUR and m < _SESSION_OPEN_MINUTE):
        return False
    return h < _SESSION_CLOSE_HOUR


def classify_mention_timing(ts_utc: datetime) -> MentionTiming:
    """Bucket a UTC timestamp by its position relative to the US session.

    Naive datetimes are treated as UTC. SQLite strips tzinfo on
    round-trip, and treating naive-as-system-tz would silently shift
    every bucket on a non-UTC host (e.g. KST). Writers always store
    UTC, so the assumption is safe and matches what the persisted data
    actually represents.
    """
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=UTC)
    et = ts_utc.astimezone(_ET)
    if et.weekday() >= 5:  # Sat=5, Sun=6
        return MentionTiming.WEEKEND
    if _in_session(et):
        return MentionTiming.IN_HOURS
    # weekday but outside the session
    # before 09:30 ET → overnight; at/after 16:00 ET → after-hours
    h, m = et.hour, et.minute
    if h < _SESSION_OPEN_HOUR or (h == _SESSION_OPEN_HOUR and m < _SESSION_OPEN_MINUTE):
        return MentionTiming.OVERNIGHT
    return MentionTiming.AFTER_HOURS


def _next_business_day(d: date) -> date:
    """Next Mon-Fri after ``d`` (does NOT account for US holidays — yfinance
    bars naturally drop those, the event study tolerates a 1-day shift).
    """
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def entry_open_date(ts_utc: datetime) -> date:
    """The trading day whose OPEN we model as the entry for this mention.

    Rules (mirrors the bloasis live cron's next-open execution model):

      OVERNIGHT  → same day's open
      IN_HOURS   → next day's open
      AFTER_HOURS → next day's open
      WEEKEND    → next Monday's open (handled by _next_business_day)
    """
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=UTC)
    timing = classify_mention_timing(ts_utc)
    et = ts_utc.astimezone(_ET)
    if timing is MentionTiming.OVERNIGHT:
        return et.date()
    # IN_HOURS, AFTER_HOURS, WEEKEND all resolve to the next business day
    # relative to the ET calendar date the post landed on.
    return _next_business_day(et.date())
