"""Tests for `bloasis.data.fetchers.yfinance_earnings`.

Network-free: patches `yfinance.Ticker.get_earnings_dates`. Verifies the
column rename, NaN row drop, tz normalization, and parquet cache hit.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from bloasis.data.cache import ParquetCache
from bloasis.data.fetchers.yfinance_earnings import EARNINGS_COLUMNS, YfEarningsFetcher


def _fake_earnings_frame() -> pd.DataFrame:
    idx = pd.to_datetime(
        [
            "2024-08-01 16:30:00-04:00",
            "2024-05-02 16:31:00-04:00",
            "2025-05-01 16:30:00-04:00",  # future row, no reported_eps
        ]
    )
    return pd.DataFrame(
        {
            "EPS Estimate": [1.35, 1.50, 1.63],
            "Reported EPS": [1.40, 1.53, float("nan")],
            "Surprise(%)": [3.99, 1.97, float("nan")],
        },
        index=idx,
    )


def test_fetch_returns_canonical_columns_and_drops_future_rows() -> None:
    fetcher = YfEarningsFetcher(cache=None)
    fake = _fake_earnings_frame()
    with patch(
        "yfinance.Ticker",
        return_value=MagicMock(get_earnings_dates=MagicMock(return_value=fake)),
    ):
        df = fetcher.fetch("AAPL")
    assert list(df.columns) == list(EARNINGS_COLUMNS)
    # Future row (NaN reported_eps) dropped
    assert len(df) == 2
    # Index normalized to naive UTC
    assert df.index.tz is None
    # Sorted ascending by date
    assert df.index.is_monotonic_increasing
    assert df["surprise_pct"].iloc[-1] == 3.99


def test_fetch_handles_empty_frame() -> None:
    fetcher = YfEarningsFetcher(cache=None)
    with patch(
        "yfinance.Ticker",
        return_value=MagicMock(get_earnings_dates=MagicMock(return_value=pd.DataFrame())),
    ):
        df = fetcher.fetch("EMPTY")
    assert df.empty
    assert list(df.columns) == list(EARNINGS_COLUMNS)


def test_fetch_handles_missing_columns_gracefully() -> None:
    fetcher = YfEarningsFetcher(cache=None)
    fake = pd.DataFrame(
        {"Reported EPS": [1.0]},
        index=pd.to_datetime(["2024-08-01"]),
    )
    with patch(
        "yfinance.Ticker",
        return_value=MagicMock(get_earnings_dates=MagicMock(return_value=fake)),
    ):
        df = fetcher.fetch("AAPL")
    assert "eps_estimate" in df.columns
    assert pd.isna(df["eps_estimate"].iloc[0])


def test_fetch_uses_parquet_cache(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path, namespace="earnings")
    fetcher = YfEarningsFetcher(cache=cache)
    fake = _fake_earnings_frame()
    with patch(
        "yfinance.Ticker",
        return_value=MagicMock(get_earnings_dates=MagicMock(return_value=fake)),
    ) as m:
        df1 = fetcher.fetch("AAPL")
        df2 = fetcher.fetch("AAPL")  # cache hit, no second yfinance call
    pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))
    assert m.call_count == 1


def test_fetch_raises_on_yfinance_error() -> None:
    fetcher = YfEarningsFetcher(cache=None)
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.side_effect = RuntimeError("delisted")
    with patch("yfinance.Ticker", return_value=mock_ticker):
        try:
            fetcher.fetch("DELISTED")
        except ValueError as exc:
            assert "no earnings data" in str(exc)
        else:  # pragma: no cover - sanity
            raise AssertionError("expected ValueError")


def test_fetch_rejects_empty_symbol() -> None:
    fetcher = YfEarningsFetcher(cache=None)
    try:
        fetcher.fetch("")
    except ValueError as exc:
        assert "symbol" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
