"""Tests for the mention forward-tracking layer (PR57).

PR56 measured a +1.32% pooled excess on negative + out-of-hours Trump
mentions retrospectively. This module records FUTURE predictions and
settles them once horizon bars are available, so the +1.32% claim can
be falsified prospectively rather than re-backtested forever.

  mention_predictions table — one row per (post_id, ticker, version, horizon)
  upsert_mention_prediction  — idempotent insert keyed by composite PK
  settle_mention_prediction  — fill realized_fwd/baseline/excess + settled_at
  list_unsettled_mention_predictions — ripe rows (entry_date + h ≤ today, not settled)
  list_untracked_mentions    — neg + AH/overnight mentions with no prediction row yet
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from bloasis.storage import (
    create_all,
    get_engine,
    mention_predictions,
    writers,
)
from bloasis.storage.readers import (
    list_unsettled_mention_predictions,
    list_untracked_mentions,
)


@pytest.fixture
def engine(tmp_path: Path):
    eng = get_engine(tmp_path / "track.db")
    create_all(eng)
    return eng


def _seed_post_mention(
    engine,
    *,
    post_id: str,
    ticker: str,
    sentiment: str,
    posted_at: datetime,
    extractor_version: int = 3,
) -> None:
    writers.upsert_social_post(
        engine,
        post_id=post_id,
        source="truth_social",
        posted_at=posted_at,
        content=f"test post about {ticker}",
        url=None,
    )
    writers.write_mention(
        engine,
        post_id=post_id,
        ticker=ticker,
        sentiment=sentiment,
        confidence=0.9,
        extractor_version=extractor_version,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_mention_predictions_table_created(engine) -> None:
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "mention_predictions" in names


def test_mention_predictions_composite_pk_per_horizon(engine) -> None:
    """Same mention can have predictions at multiple horizons coexist."""
    posted_at = datetime(2026, 6, 4, 1, 0, tzinfo=UTC)  # overnight ET
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 4),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=10,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 4),
        baseline_at_pred=0.012,
        predicted_excess=0.013,
    )
    with engine.connect() as conn:
        rows = conn.execute(select(mention_predictions)).fetchall()
    assert len(rows) == 2
    assert {r.horizon_days for r in rows} == {5, 10}


# ---------------------------------------------------------------------------
# upsert_mention_prediction — idempotent
# ---------------------------------------------------------------------------


def test_upsert_mention_prediction_idempotent(engine) -> None:
    """Same (post, ticker, version, horizon) twice → still one row."""
    posted_at = datetime(2026, 6, 4, 1, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    kwargs = dict(
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 4),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    writers.upsert_mention_prediction(engine, **kwargs)
    writers.upsert_mention_prediction(engine, **kwargs)
    with engine.connect() as conn:
        n = conn.execute(select(mention_predictions)).fetchall()
    assert len(n) == 1


# ---------------------------------------------------------------------------
# settle_mention_prediction — fills realized fields
# ---------------------------------------------------------------------------


def test_settle_mention_prediction_writes_realized(engine) -> None:
    posted_at = datetime(2026, 6, 4, 1, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 4),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    writers.settle_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.022,
        realized_baseline=0.005,
        realized_excess=0.017,
    )
    with engine.connect() as conn:
        row = conn.execute(select(mention_predictions)).fetchone()
    assert row is not None
    assert row.realized_fwd == pytest.approx(0.022)
    assert row.realized_baseline == pytest.approx(0.005)
    assert row.realized_excess == pytest.approx(0.017)
    assert row.settled_at is not None


def test_settle_mention_prediction_is_idempotent(engine) -> None:
    """Settling twice keeps the LAST values + settled_at, no error."""
    posted_at = datetime(2026, 6, 4, 1, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 4),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    writers.settle_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.022,
        realized_baseline=0.005,
        realized_excess=0.017,
    )
    writers.settle_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.030,
        realized_baseline=0.005,
        realized_excess=0.025,
    )
    with engine.connect() as conn:
        rows = conn.execute(select(mention_predictions)).fetchall()
    assert len(rows) == 1
    assert rows[0].realized_excess == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def test_list_unsettled_predictions_filters_by_ripeness(engine) -> None:
    """Only predictions where entry_date + horizon_days ≤ today AND
    settled_at IS NULL should appear."""
    posted_at = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    _seed_post_mention(
        engine, post_id="truth:2", ticker="META", sentiment="negative", posted_at=posted_at
    )
    # Ripe — entry 2026-05-26 + 5d = 2026-05-31, today=2026-06-04 → ripe.
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 5, 26),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    # Not ripe — entry 2026-06-30 + 5d in the future.
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:2",
        ticker="META",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 30),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    rows = list_unsettled_mention_predictions(engine, as_of=date(2026, 6, 4))
    assert len(rows) == 1
    assert rows[0].post_id == "truth:1"


def test_list_unsettled_predictions_excludes_already_settled(engine) -> None:
    posted_at = datetime(2026, 5, 1, 1, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 5, 1),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    writers.settle_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.022,
        realized_baseline=0.005,
        realized_excess=0.017,
    )
    rows = list_unsettled_mention_predictions(engine, as_of=date(2026, 6, 4))
    assert rows == []


def test_list_untracked_mentions_negative_oot_only(engine) -> None:
    """Only NEW (no row in mention_predictions yet) NEGATIVE + AH/overnight
    mentions should be returned. in_hours and weekend skip; positive/neutral skip."""
    # negative + overnight (06:00 UTC = 02:00 ET pre-market)
    overnight_ts = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
    _seed_post_mention(
        engine,
        post_id="truth:overnight",
        ticker="AMZN",
        sentiment="negative",
        posted_at=overnight_ts,
    )
    # negative + after-hours (22:00 UTC = 18:00 ET, after 16:00 close)
    after_hours_ts = datetime(2026, 6, 2, 22, 0, tzinfo=UTC)
    _seed_post_mention(
        engine,
        post_id="truth:after",
        ticker="META",
        sentiment="negative",
        posted_at=after_hours_ts,
    )
    # negative + IN-hours (15:00 UTC = 11:00 ET, during session)
    in_hours_ts = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)
    _seed_post_mention(
        engine,
        post_id="truth:in",
        ticker="NVDA",
        sentiment="negative",
        posted_at=in_hours_ts,
    )
    # positive + overnight (should NOT be tracked — positive cell is loss-making)
    positive_ts = datetime(2026, 6, 1, 7, 0, tzinfo=UTC)
    _seed_post_mention(
        engine,
        post_id="truth:pos",
        ticker="AAPL",
        sentiment="positive",
        posted_at=positive_ts,
    )

    rows = list_untracked_mentions(engine, extractor_version=3, horizon_days=5)
    post_ids = {r.post_id for r in rows}
    assert post_ids == {"truth:overnight", "truth:after"}


def test_list_untracked_excludes_already_predicted(engine) -> None:
    posted_at = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
    _seed_post_mention(
        engine, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    # initially untracked
    assert len(list_untracked_mentions(engine, extractor_version=3, horizon_days=5)) == 1
    writers.upsert_mention_prediction(
        engine,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 6, 1),
        baseline_at_pred=0.006,
        predicted_excess=0.013,
    )
    # now hidden
    assert list_untracked_mentions(engine, extractor_version=3, horizon_days=5) == []


# ---------------------------------------------------------------------------
# CLI smoke — mentions-track-report on empty + populated DB
# ---------------------------------------------------------------------------


def test_mentions_track_report_handles_empty(tmp_path: Path, monkeypatch) -> None:
    """Empty DB: command exits 0 (typer.Exit(0)) without crashing."""
    from typer.testing import CliRunner

    from bloasis.cli import app
    from bloasis.storage import create_all

    db = tmp_path / "track.db"
    create_all(get_engine(db))
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db))
    res = CliRunner().invoke(app, ["research", "mentions-track-report"])
    assert res.exit_code == 0
    assert "no predictions yet" in res.stdout


def test_mentions_track_report_aggregates_settled_rows(tmp_path: Path, monkeypatch) -> None:
    """Populated DB: report prints buckets + combined row with realized excess."""
    from typer.testing import CliRunner

    from bloasis.cli import app
    from bloasis.storage import create_all

    db = tmp_path / "track.db"
    eng = get_engine(db)
    create_all(eng)
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db))

    # One overnight + one after_hours, both settled.
    posted_at = datetime(2026, 5, 1, 6, 0, tzinfo=UTC)
    _seed_post_mention(
        eng, post_id="truth:1", ticker="AMZN", sentiment="negative", posted_at=posted_at
    )
    _seed_post_mention(
        eng, post_id="truth:2", ticker="META", sentiment="negative", posted_at=posted_at
    )
    writers.upsert_mention_prediction(
        eng,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="overnight",
        entry_date=date(2026, 5, 1),
        baseline_at_pred=0.006,
        predicted_excess=0.0132,
    )
    writers.upsert_mention_prediction(
        eng,
        post_id="truth:2",
        ticker="META",
        extractor_version=3,
        horizon_days=5,
        posted_at=posted_at,
        sentiment="negative",
        timing_bucket="after_hours",
        entry_date=date(2026, 5, 1),
        baseline_at_pred=0.006,
        predicted_excess=0.0132,
    )
    writers.settle_mention_prediction(
        eng,
        post_id="truth:1",
        ticker="AMZN",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.022,
        realized_baseline=0.005,
        realized_excess=0.017,
    )
    writers.settle_mention_prediction(
        eng,
        post_id="truth:2",
        ticker="META",
        extractor_version=3,
        horizon_days=5,
        realized_fwd=0.020,
        realized_baseline=0.006,
        realized_excess=0.014,
    )
    res = CliRunner().invoke(app, ["research", "mentions-track-report"])
    assert res.exit_code == 0
    # Rich may truncate column text — assert prefixes that survive truncation.
    assert "after_hou" in res.stdout
    assert "overnight" in res.stdout
    assert "combined" in res.stdout
    # We seeded predicted = +1.32%, realized excess ≈ +1.55% pooled.
    assert "+1.32%" in res.stdout
    assert "+1.55%" in res.stdout
