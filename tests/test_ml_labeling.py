"""Tests for `bloasis.ml.labeling` — forward-return label computation.

Covers the pure helper (`compute_forward_returns`) and the storage-aware
batch labeler (`label_unlabeled_features`). The CLI smoke is in
`test_cli_label_features.py`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from bloasis.ml.labeling import (
    DEFAULT_LOOKBACKS,
    compute_forward_returns,
    label_unlabeled_features,
)
from bloasis.storage import create_all, feature_log, get_engine


def _close_series(start: str, prices: list[float]) -> pd.Series:
    """Build a daily-frequency close series."""
    idx = pd.bdate_range(start, periods=len(prices), freq="B")
    return pd.Series(prices, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# compute_forward_returns — pure helper
# ---------------------------------------------------------------------------


def test_forward_returns_happy_path() -> None:
    """Linear price growth → forward returns are simple ratios."""
    # 100 bars: prices 100, 101, 102, ..., 199
    prices = [100.0 + i for i in range(100)]
    close = _close_series("2024-01-01", prices)
    t = close.index[10]  # price at t = 110
    out = compute_forward_returns(close, t, lookbacks=[5, 20, 60])
    # close[t+5] = 115, return = (115 - 110) / 110 = 0.04545...
    assert out[5] == pytest.approx((115 - 110) / 110)
    assert out[20] == pytest.approx((130 - 110) / 110)
    assert out[60] == pytest.approx((170 - 110) / 110)


def test_forward_returns_default_lookbacks() -> None:
    """`DEFAULT_LOOKBACKS = [5, 20, 60]`."""
    assert tuple(DEFAULT_LOOKBACKS) == (5, 20, 60)


def test_forward_returns_insufficient_history_nan() -> None:
    """Not enough forward bars → NaN for that horizon, others may still resolve."""
    close = _close_series("2024-01-01", [100.0 + i for i in range(15)])
    t = close.index[5]
    out = compute_forward_returns(close, t, lookbacks=[5, 20, 60])
    # 5 bars forward exist (close[10] = 110)
    assert out[5] == pytest.approx((110 - 105) / 105)
    # 20, 60 bars forward don't exist
    assert math.isnan(out[20])
    assert math.isnan(out[60])


def test_forward_returns_zero_base_returns_nan() -> None:
    close = _close_series("2024-01-01", [0.0] + [100.0] * 100)
    t = close.index[0]  # base price 0 → undefined return
    out = compute_forward_returns(close, t, lookbacks=[5])
    assert math.isnan(out[5])


def test_forward_returns_nan_in_forward_bar_returns_nan() -> None:
    prices = [100.0 + i for i in range(20)]
    prices[10] = float("nan")  # corrupted forward bar
    close = _close_series("2024-01-01", prices)
    t = close.index[5]
    out = compute_forward_returns(close, t, lookbacks=[5])
    assert math.isnan(out[5])


def test_forward_returns_timestamp_not_in_index_uses_nearest_preceding() -> None:
    """`t` between two trading days → use the most recent <= t (preceding)."""
    close = _close_series("2024-01-01", [100.0 + i for i in range(20)])
    # t falls on a Saturday (between Friday & Monday in bdate_range)
    last_friday = close.index[3]
    t = last_friday + timedelta(hours=12)  # Friday afternoon, still Friday's bar
    out = compute_forward_returns(close, t, lookbacks=[5])
    # base = close[Friday] = 103, top = close[Friday + 5 trading days]
    base = float(close.loc[last_friday])
    top = float(close.iloc[3 + 5])
    assert out[5] == pytest.approx((top - base) / base)


def test_forward_returns_t_before_index_returns_all_nan() -> None:
    close = _close_series("2024-06-01", [100.0 + i for i in range(20)])
    t = pd.Timestamp("2024-01-01")
    out = compute_forward_returns(close, t, lookbacks=[5, 20, 60])
    for lb in (5, 20, 60):
        assert math.isnan(out[lb])


def test_forward_returns_empty_lookbacks_returns_empty_dict() -> None:
    close = _close_series("2024-01-01", [100.0] * 30)
    out = compute_forward_returns(close, close.index[0], lookbacks=[])
    assert out == {}


def test_forward_returns_negative_lookback_raises() -> None:
    close = _close_series("2024-01-01", [100.0] * 30)
    with pytest.raises(ValueError, match="lookback"):
        compute_forward_returns(close, close.index[0], lookbacks=[-5])


# ---------------------------------------------------------------------------
# label_unlabeled_features — DB-aware batch labeler
# ---------------------------------------------------------------------------


def _seed_feature_log_row(
    engine,
    *,
    timestamp: datetime,
    symbol: str,
    run_id: int | None = None,
    feature_version: int = 2,
) -> None:
    """Insert a minimal feature_log row with NULL labels."""
    from sqlalchemy import insert

    with engine.begin() as conn:
        conn.execute(
            insert(feature_log).values(
                timestamp=timestamp,
                symbol=symbol,
                run_id=run_id,
                feature_version=feature_version,
                created_at=datetime.now(tz=UTC),
            )
        )


def _make_engine(tmp_path) -> object:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "label.db"
    engine = get_engine(db_path)
    create_all(engine)
    return engine


def test_label_unlabeled_features_fills_all_horizons(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """End-to-end: seed 1 row, call labeler, assert label columns + filled_at."""
    engine = _make_engine(tmp_path)
    t = datetime(2024, 1, 5, tzinfo=UTC)
    _seed_feature_log_row(engine, timestamp=t, symbol="AAA", run_id=1)

    # Synthetic OHLCV providers: single symbol with simple price series.
    close = _close_series("2024-01-01", [100.0 + i for i in range(120)])

    def fake_ohlcv(symbol: str) -> pd.Series | None:
        return close if symbol == "AAA" else None

    n = label_unlabeled_features(engine, ohlcv_provider=fake_ohlcv)
    assert n == 1

    with engine.connect() as conn:
        row = conn.execute(select(feature_log).where(feature_log.c.symbol == "AAA")).first()
    assert row is not None
    assert row.label_filled_at is not None
    # 5d return: t maps to close.index[2] (Jan 1=Mon, t=Jan 5=Fri → idx 4),
    # but bdate_range starts Jan 1 (Mon), so index[0]=Mon Jan 1, [4]=Fri Jan 5 = 104.
    # forward 5 = idx[9] = 109. Return = (109 - 104) / 104.
    assert row.forward_return_5d == pytest.approx((109 - 104) / 104, abs=1e-9)


def test_label_unlabeled_features_skips_already_labeled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = _make_engine(tmp_path)
    t = datetime(2024, 1, 5, tzinfo=UTC)
    _seed_feature_log_row(engine, timestamp=t, symbol="AAA", run_id=1)

    close = _close_series("2024-01-01", [100.0 + i for i in range(120)])

    def fake_ohlcv(symbol: str) -> pd.Series | None:
        return close

    label_unlabeled_features(engine, ohlcv_provider=fake_ohlcv)
    # Second pass should be a no-op
    n = label_unlabeled_features(engine, ohlcv_provider=fake_ohlcv)
    assert n == 0


def test_label_unlabeled_features_marks_filled_when_all_horizons_nan(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """No forward data at all → labels stay NULL but `label_filled_at`
    should still be set so we don't re-attempt forever. The labeler
    returns the row count it processed, regardless of NaN outcome."""
    engine = _make_engine(tmp_path)
    t = datetime(2024, 12, 1, tzinfo=UTC)  # near end of synthetic series
    _seed_feature_log_row(engine, timestamp=t, symbol="BBB", run_id=1)

    short_close = _close_series("2024-11-25", [100.0 + i for i in range(3)])  # only 3 bars

    def fake_ohlcv(symbol: str) -> pd.Series | None:
        return short_close

    n = label_unlabeled_features(engine, ohlcv_provider=fake_ohlcv)
    assert n == 1
    with engine.connect() as conn:
        row = conn.execute(select(feature_log).where(feature_log.c.symbol == "BBB")).first()
    assert row is not None
    assert row.label_filled_at is not None
    assert row.forward_return_5d is None
    assert row.forward_return_20d is None
    assert row.forward_return_60d is None


def test_label_unlabeled_features_skips_missing_ohlcv_provider(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """If ohlcv_provider returns None for a symbol (cache miss), skip
    the row — don't mark filled. Re-run after cache fetch will pick it up."""
    engine = _make_engine(tmp_path)
    t = datetime(2024, 1, 5, tzinfo=UTC)
    _seed_feature_log_row(engine, timestamp=t, symbol="MISSING", run_id=1)

    def empty_provider(symbol: str) -> pd.Series | None:
        return None

    n = label_unlabeled_features(engine, ohlcv_provider=empty_provider)
    assert n == 0
    with engine.connect() as conn:
        row = conn.execute(select(feature_log).where(feature_log.c.symbol == "MISSING")).first()
    assert row is not None
    assert row.label_filled_at is None  # still pending


def test_label_unlabeled_features_groups_by_symbol(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Multiple rows with same symbol → one provider call, all rows labeled."""
    engine = _make_engine(tmp_path)
    for day in (5, 6, 7, 8):
        _seed_feature_log_row(
            engine,
            timestamp=datetime(2024, 1, day, tzinfo=UTC),
            symbol="ZZZ",
            run_id=1,
        )

    close = _close_series("2024-01-01", [100.0 + i for i in range(120)])
    call_count = {"n": 0}

    def counting_provider(symbol: str) -> pd.Series | None:
        call_count["n"] += 1
        return close

    n = label_unlabeled_features(engine, ohlcv_provider=counting_provider)
    assert n == 4
    assert call_count["n"] == 1, "provider should be called once per unique symbol"
