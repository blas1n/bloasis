"""Tests for the social-post mention pipeline (PR55).

Two layers:
  schema — social_posts + social_post_mentions tables
  pure compute — classify each event by mention timing relative to the
    US trading session, which determines whether the impact lives in
    the open gap (out-of-hours catalyst) or in the day's intraday
    range (in-hours catalyst). Critical for measuring what's HFT-only
    vs retail-feasible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from bloasis.analysis.mention_timing import (
    MentionTiming,
    classify_mention_timing,
    entry_open_date,
)
from bloasis.storage import (
    create_all,
    get_engine,
    social_post_mentions,
    social_posts,
    writers,
)


@pytest.fixture
def engine(tmp_path: Path):
    eng = get_engine(tmp_path / "social.db")
    create_all(eng)
    return eng


# ---------------------------------------------------------------------------
# Schema — social_posts + social_post_mentions
# ---------------------------------------------------------------------------


def test_social_tables_created(engine) -> None:
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"social_posts", "social_post_mentions"} <= names


def test_upsert_social_post_idempotent(engine) -> None:
    """Same post_id twice does NOT duplicate — supports running the
    fetcher every 5 minutes without growing the table."""
    writers.upsert_social_post(
        engine,
        post_id="truth:116684114421950130",
        source="truth_social",
        posted_at=datetime(2026, 6, 3, 3, 44, tzinfo=UTC),
        content="EPA boss made criminal referrals…",
        url="https://truthsocial.com/@realDonaldTrump/116684114421950130",
    )
    writers.upsert_social_post(
        engine,
        post_id="truth:116684114421950130",
        source="truth_social",
        posted_at=datetime(2026, 6, 3, 3, 44, tzinfo=UTC),
        content="EPA boss made criminal referrals…",
        url="https://truthsocial.com/@realDonaldTrump/116684114421950130",
    )
    with engine.connect() as conn:
        rows = conn.execute(select(social_posts)).fetchall()
    assert len(rows) == 1


def test_write_mention_links_to_post(engine) -> None:
    writers.upsert_social_post(
        engine,
        post_id="truth:42",
        source="truth_social",
        posted_at=datetime(2026, 5, 8, 18, 0, tzinfo=UTC),
        content="Everyone should buy Dell computers!",
        url="https://truthsocial.com/p/42",
    )
    writers.write_mention(
        engine,
        post_id="truth:42",
        ticker="DELL",
        sentiment="positive",
        confidence=0.95,
        extractor_version=1,
    )
    with engine.connect() as conn:
        rows = conn.execute(select(social_post_mentions)).fetchall()
    assert len(rows) == 1
    assert rows[0].ticker == "DELL"
    assert rows[0].sentiment == "positive"
    assert rows[0].confidence == pytest.approx(0.95)


def test_mark_post_extracted(engine) -> None:
    """After LLM extraction, mentions_extracted_at is set so the batch
    job doesn't re-process the same post."""
    writers.upsert_social_post(
        engine,
        post_id="truth:99",
        source="truth_social",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        content="x",
        url="x",
    )
    writers.mark_post_extracted(engine, post_id="truth:99", extractor_version=1)
    with engine.connect() as conn:
        row = conn.execute(
            select(social_posts).where(social_posts.c.post_id == "truth:99")
        ).fetchone()
    assert row is not None
    assert row.mentions_extracted_at is not None
    assert row.extractor_version == 1


# ---------------------------------------------------------------------------
# Mention timing — classify each event vs US trading session
# ---------------------------------------------------------------------------


def test_classify_in_hours_session() -> None:
    # 2026-06-03 (Wed) 15:30 UTC = 11:30 ET (EDT) — middle of US session.
    ts = datetime(2026, 6, 3, 15, 30, tzinfo=UTC)
    assert classify_mention_timing(ts) is MentionTiming.IN_HOURS


def test_classify_after_hours_same_day() -> None:
    # 2026-06-03 (Wed) 21:30 UTC = 17:30 ET — after 16:00 ET close.
    ts = datetime(2026, 6, 3, 21, 30, tzinfo=UTC)
    assert classify_mention_timing(ts) is MentionTiming.AFTER_HOURS


def test_classify_overnight_before_open() -> None:
    # 2026-06-03 (Wed) 12:00 UTC = 08:00 ET — before 09:30 ET open.
    ts = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
    assert classify_mention_timing(ts) is MentionTiming.OVERNIGHT


def test_classify_weekend() -> None:
    # 2026-05-30 = Sat. Any time on Sat or Sun.
    ts = datetime(2026, 5, 30, 17, 0, tzinfo=UTC)
    assert classify_mention_timing(ts) is MentionTiming.WEEKEND
    ts2 = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    assert classify_mention_timing(ts2) is MentionTiming.WEEKEND


# ---------------------------------------------------------------------------
# Entry open date — first tradable open at-or-after the mention
# ---------------------------------------------------------------------------


def test_entry_open_date_in_hours_uses_next_day() -> None:
    # Mention during Wed session → entry at Thu open (we model as
    # next-day open, mirroring the backtester / live cron).
    ts = datetime(2026, 6, 3, 15, 30, tzinfo=UTC)  # Wed in-hours
    assert entry_open_date(ts).isoformat() == "2026-06-04"


def test_entry_open_date_after_hours_uses_next_session() -> None:
    ts = datetime(2026, 6, 3, 21, 30, tzinfo=UTC)  # Wed 17:30 ET, after close
    assert entry_open_date(ts).isoformat() == "2026-06-04"


def test_entry_open_date_overnight_uses_same_day() -> None:
    # Wed 12:00 UTC = Wed 08:00 ET, before 09:30 ET open → entry is
    # the SAME day's open (Wed 09:30 ET).
    ts = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
    assert entry_open_date(ts).isoformat() == "2026-06-03"


def test_entry_open_date_weekend_rolls_to_monday() -> None:
    # Sat 2026-05-30 → Mon 2026-06-01
    ts = datetime(2026, 5, 30, 17, 0, tzinfo=UTC)
    assert entry_open_date(ts).isoformat() == "2026-06-01"
    # Sun 2026-05-31 → Mon 2026-06-01
    ts2 = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    assert entry_open_date(ts2).isoformat() == "2026-06-01"


def test_entry_open_date_friday_after_close_rolls_to_monday() -> None:
    # Fri 2026-05-29 22:00 UTC = 18:00 ET (after close) → Mon 2026-06-01
    ts = datetime(2026, 5, 29, 22, 0, tzinfo=UTC)
    assert entry_open_date(ts).isoformat() == "2026-06-01"
