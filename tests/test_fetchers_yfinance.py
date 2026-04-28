"""Tests for yfinance-backed fetchers (mocked)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bloasis.data.cache import ParquetCache
from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
from bloasis.data.fetchers.yfinance_screener import (
    YfFundamentalsFetcher,
    _quote_to_row,
    _to_float,
    _to_str,
)

# ---------------------------------------------------------------------------
# YfOhlcvFetcher
# ---------------------------------------------------------------------------


def _ohlcv_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "Open": [10.0, 11, 12, 13, 14],
            "High": [11, 12, 13, 14, 15],
            "Low": [9, 10, 11, 12, 13],
            "Close": [10.5, 11.5, 12.5, 13.5, 14.5],
            "Volume": [1000.0, 1100, 1200, 1300, 1400],
        },
        index=idx,
    )


def _patch_ticker(df: pd.DataFrame) -> object:
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker
    return patch.dict("sys.modules", {"yfinance": fake_yf})


def test_ohlcv_fetch_returns_normalized_columns() -> None:
    df = _ohlcv_df()
    with _patch_ticker(df):
        fetcher = YfOhlcvFetcher()
        out = fetcher.fetch("AAPL", date(2024, 1, 1), date(2024, 1, 5))
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 5


def test_ohlcv_empty_dataframe_raises() -> None:
    with _patch_ticker(pd.DataFrame()):
        fetcher = YfOhlcvFetcher()
        with pytest.raises(ValueError, match="no OHLCV data"):
            fetcher.fetch("BOGUS", date(2024, 1, 1), date(2024, 1, 5))


def test_ohlcv_empty_symbol_raises() -> None:
    fetcher = YfOhlcvFetcher()
    with pytest.raises(ValueError, match="non-empty"):
        fetcher.fetch("", date(2024, 1, 1), date(2024, 1, 2))


def test_ohlcv_start_after_end_raises() -> None:
    fetcher = YfOhlcvFetcher()
    with pytest.raises(ValueError, match="start"):
        fetcher.fetch("AAPL", date(2024, 1, 5), date(2024, 1, 1))


def test_ohlcv_uses_cache_on_warm_call(tmp_path: Path) -> None:
    df = _ohlcv_df()
    cache = ParquetCache(tmp_path, namespace="ohlcv")

    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker

    with patch.dict("sys.modules", {"yfinance": fake_yf}):
        fetcher = YfOhlcvFetcher(cache=cache)
        out1 = fetcher.fetch("AAPL", date(2024, 1, 1), date(2024, 1, 5))
        out2 = fetcher.fetch("AAPL", date(2024, 1, 1), date(2024, 1, 5))
    # parquet drops index freq; values must match.
    pd.testing.assert_frame_equal(out1, out2, check_freq=False)
    # network call only happened once
    assert fake_ticker.history.call_count == 1


def test_ohlcv_caret_symbol_keyed_safely(tmp_path: Path) -> None:
    df = _ohlcv_df()
    cache = ParquetCache(tmp_path, namespace="ohlcv")

    fake_ticker = MagicMock()
    fake_ticker.history.return_value = df
    fake_yf = MagicMock()
    fake_yf.Ticker.return_value = fake_ticker

    with patch.dict("sys.modules", {"yfinance": fake_yf}):
        fetcher = YfOhlcvFetcher(cache=cache)
        fetcher.fetch("^VIX", date(2024, 1, 1), date(2024, 1, 5))

    # ^ replaced with IDX_, no path issues
    cached_files = list((tmp_path / "parquet" / "ohlcv").glob("*.parquet"))
    assert cached_files
    assert all("^" not in p.name for p in cached_files)


# ---------------------------------------------------------------------------
# YfMarketContextFetcher
# ---------------------------------------------------------------------------


def test_market_context_returns_vix_and_spy() -> None:
    # Concrete OhlcvFetcher impls return lowercase columns by contract.
    df = _ohlcv_df()
    df.columns = [c.lower() for c in df.columns]
    fake_ohlcv = MagicMock()
    fake_ohlcv.fetch.return_value = df

    fetcher = YfMarketContextFetcher(ohlcv=fake_ohlcv)
    ctx = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 5))

    assert (ctx.vix == df["close"]).all()
    assert (ctx.spy_close == df["close"]).all()
    # one fetch for VIX, one for SPY
    assert fake_ohlcv.fetch.call_count == 2
    symbols = [c.args[0] for c in fake_ohlcv.fetch.call_args_list]
    assert "^VIX" in symbols
    assert "SPY" in symbols


# ---------------------------------------------------------------------------
# YfFundamentalsFetcher helpers
# ---------------------------------------------------------------------------


def test_to_float_handles_junk() -> None:
    assert _to_float(None) is None
    assert _to_float("not-a-number") is None
    assert _to_float(float("nan")) is None
    assert _to_float(float("inf")) is None
    assert _to_float(3.14) == 3.14
    assert _to_float("2.5") == 2.5


def test_to_str_strips_and_nullifies() -> None:
    assert _to_str(None) is None
    assert _to_str("") is None
    assert _to_str("  ") is None
    assert _to_str("Tech") == "Tech"


def test_quote_to_row_maps_fields() -> None:
    quote = {
        "symbol": "aapl",
        "marketCap": 3.0e12,
        "trailingPE": 28.5,
        "priceToBook": 50.0,
        "averageDailyVolume3Month": 50_000_000,
        "regularMarketPrice": 200.0,
        "profitMargins": 0.25,
        "returnOnEquity": 1.5,
        "debtToEquity": 1.2,
        "currentRatio": 1.0,
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    now = datetime.now(tz=UTC)
    row = _quote_to_row(quote, fetched_at=now)
    assert row is not None
    assert row.symbol == "AAPL"
    assert row.market_cap == 3.0e12
    assert row.pe_ratio_ttm == 28.5
    # dollar volume = avg_vol * price = 50M * 200 = 1e10
    assert row.dollar_volume_avg == pytest.approx(1.0e10)
    assert row.sector == "Technology"


def test_quote_to_row_missing_symbol_returns_none() -> None:
    now = datetime.now(tz=UTC)
    assert _quote_to_row({}, fetched_at=now) is None


# ---------------------------------------------------------------------------
# YfFundamentalsFetcher.fetch_bulk — mocked Screener
# ---------------------------------------------------------------------------


def test_fetch_bulk_paginates_and_stops_on_empty() -> None:
    fake_screener_class = MagicMock()
    fake_screener_instance = MagicMock()
    fake_screener_class.return_value = fake_screener_instance

    quotes_p1 = [
        {"symbol": "A", "marketCap": 1e12, "trailingPE": 20, "sector": "X"} for _ in range(250)
    ]
    quotes_p2 = [{"symbol": "B", "marketCap": 5e11, "trailingPE": 25, "sector": "Y"}]

    responses = iter(
        [
            {"quotes": quotes_p1},
            {"quotes": quotes_p2},
        ]
    )
    type(fake_screener_instance).response = property(lambda _self: next(responses))

    fake_module = MagicMock()
    fake_module.EquityQuery = MagicMock()
    fake_module.Screener = fake_screener_class

    with patch.dict("sys.modules", {"yfinance": fake_module}):
        fetcher = YfFundamentalsFetcher()
        rows = fetcher.fetch_bulk(max_count=1000)

    assert len(rows) == 251  # 250 from p1 + 1 from p2 (then empty stops loop)
    assert rows[0].symbol == "A"
    assert rows[-1].symbol == "B"


def test_fetch_bulk_respects_max_count() -> None:
    fake_screener_class = MagicMock()
    fake_screener_instance = MagicMock()
    fake_screener_class.return_value = fake_screener_instance
    quotes = [{"symbol": f"S{i}", "marketCap": 1e10, "sector": "X"} for i in range(250)]
    fake_screener_instance.response = {"quotes": quotes}

    fake_module = MagicMock()
    fake_module.EquityQuery = MagicMock()
    fake_module.Screener = fake_screener_class

    with patch.dict("sys.modules", {"yfinance": fake_module}):
        fetcher = YfFundamentalsFetcher()
        rows = fetcher.fetch_bulk(max_count=10)

    assert len(rows) == 10
