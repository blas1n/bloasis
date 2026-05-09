"""Tests for `bloasis.data.fetchers.yfinance_financials`.

Network-free: patches `yfinance.Ticker` to return synthetic annual
income / cashflow / balance frames. Verifies the canonical-field merge
across statements + tz normalization + cache.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from bloasis.data.cache import ParquetCache
from bloasis.data.fetchers.yfinance_financials import (
    CANONICAL_FIELDS,
    YfFinancialsFetcher,
)


def _fake_statements() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cols = pd.to_datetime(["2024-09-30", "2023-09-30", "2022-09-30", "2021-09-30", "2020-09-30"])
    income = pd.DataFrame(
        {c: [400e9, 320e9, 130e9] for c in cols},
        index=["Total Revenue", "EBITDA", "Net Income"],
    )
    cashflow = pd.DataFrame(
        {c: [110e9] for c in cols},
        index=["Free Cash Flow"],
    )
    balance = pd.DataFrame(
        {c: [99e9, 56e9] for c in cols},
        index=["Total Debt", "Stockholders Equity"],
    )
    return income, cashflow, balance


def _make_ticker() -> MagicMock:
    income, cashflow, balance = _fake_statements()
    ticker = MagicMock()
    ticker.income_stmt = income
    ticker.cashflow = cashflow
    ticker.balance_sheet = balance
    return ticker


def test_fetch_returns_canonical_fields_per_year() -> None:
    fetcher = YfFinancialsFetcher(cache=None)
    with patch("yfinance.Ticker", return_value=_make_ticker()):
        df = fetcher.fetch("AAPL")
    assert list(df.columns) == list(CANONICAL_FIELDS)
    assert len(df) == 5
    assert df.index.is_monotonic_increasing
    assert df.index.tz is None
    assert df["Revenue"].iloc[0] == 400e9
    assert df["NetIncome"].iloc[0] == 130e9


def test_fetch_handles_missing_aliases() -> None:
    """If the canonical alias names are absent, those cells stay NaN."""
    fetcher = YfFinancialsFetcher(cache=None)
    cols = pd.to_datetime(["2024-09-30"])
    income = pd.DataFrame({c: [10e9] for c in cols}, index=["Total Revenue"])
    cashflow = pd.DataFrame()
    balance = pd.DataFrame()
    ticker = MagicMock()
    ticker.income_stmt = income
    ticker.cashflow = cashflow
    ticker.balance_sheet = balance
    with patch("yfinance.Ticker", return_value=ticker):
        df = fetcher.fetch("X")
    assert df["Revenue"].iloc[0] == 10e9
    assert pd.isna(df["EBITDA"].iloc[0])
    assert pd.isna(df["FreeCashFlow"].iloc[0])
    assert pd.isna(df["TotalDebt"].iloc[0])


def test_fetch_returns_empty_frame_when_no_data() -> None:
    fetcher = YfFinancialsFetcher(cache=None)
    ticker = MagicMock()
    ticker.income_stmt = pd.DataFrame()
    ticker.cashflow = pd.DataFrame()
    ticker.balance_sheet = pd.DataFrame()
    with patch("yfinance.Ticker", return_value=ticker):
        df = fetcher.fetch("EMPTY")
    assert df.empty


def test_fetch_uses_parquet_cache(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path, namespace="financials")
    fetcher = YfFinancialsFetcher(cache=cache)
    ticker = _make_ticker()
    with patch("yfinance.Ticker", return_value=ticker) as m:
        df1 = fetcher.fetch("AAPL")
        df2 = fetcher.fetch("AAPL")
    pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))
    assert m.call_count == 1


def test_fetch_raises_on_error() -> None:
    fetcher = YfFinancialsFetcher(cache=None)
    ticker = MagicMock()
    type(ticker).income_stmt = property(  # type: ignore[misc]
        lambda self: (_ for _ in ()).throw(RuntimeError("delisted"))
    )
    with patch("yfinance.Ticker", return_value=ticker):
        try:
            fetcher.fetch("DEL")
        except ValueError as exc:
            assert "no financial data" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")


def test_fetch_rejects_empty_symbol() -> None:
    fetcher = YfFinancialsFetcher(cache=None)
    try:
        fetcher.fetch("")
    except ValueError as exc:
        assert "symbol" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
