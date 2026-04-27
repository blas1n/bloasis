"""yfinance-backed OHLCV fetcher.

Fetches daily bars from Yahoo Finance and caches them as parquet locally
so subsequent calls within `max_age` are zero-network.

Cache key encodes (symbol, start, end) so different windows for the same
symbol don't collide. We deliberately do NOT auto-merge windows (e.g.,
re-using a 90d cache for a 30d query) — the storage cost is negligible
and merging adds complexity.

Raises `ValueError` for empty/unrecognized symbols. yfinance is permissive
and returns empty DataFrames for typos; we surface that as an explicit
error so callers don't silently feed empty data into feature extraction.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, cast

from bloasis.data.cache import ParquetCache

if TYPE_CHECKING:
    import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class YfOhlcvFetcher:
    """Daily OHLCV fetcher with parquet cache."""

    def __init__(
        self,
        cache: ParquetCache | None = None,
        max_age_hours: int = 24,
    ) -> None:
        self._cache = cache
        self._max_age = timedelta(hours=max_age_hours)

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        if start > end:
            raise ValueError(f"start ({start}) must be <= end ({end})")

        key = self._cache_key(symbol, start, end)
        if self._cache is not None:
            cached = self._cache.get(key, max_age=self._max_age)
            if cached is not None:
                return cached

        df = self._download(symbol, start, end)
        if self._cache is not None:
            self._cache.put(key, df)
        return df

    @staticmethod
    def _cache_key(symbol: str, start: date, end: date) -> str:
        # yfinance treats `^VIX` etc. specially; preserve casing but replace
        # `^` so it's filesystem-safe.
        safe = symbol.replace("^", "IDX_")
        return f"{safe}_{start.isoformat()}_{end.isoformat()}"

    @staticmethod
    def _download(symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf

        # `auto_adjust=False` keeps unadjusted Close so callers can decide
        # adjustment themselves. Returns split-adjusted but not dividend-adj.
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if df is None or df.empty:
            raise ValueError(f"no OHLCV data returned for {symbol!r}")

        # Normalize columns to lower-case and drop any extras.
        df.columns = [str(c).lower() for c in df.columns]
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"yfinance returned unexpected columns for {symbol!r}: "
                f"missing {missing}, got {list(df.columns)}"
            )
        return cast("pd.DataFrame", df[list(OHLCV_COLUMNS)].copy())
