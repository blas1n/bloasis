"""yfinance-backed earnings history fetcher.

Returns a DataFrame indexed by earnings announcement date with columns
`eps_estimate`, `reported_eps`, `surprise_pct`. Used by `PEADScorer`
(Phase 3 Candidate A) — see
`~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md` §A.

yfinance limit: typically 2-3 years of historical earnings dates per
ticker. For multi-year backtests this is a hard ceiling — see Phase 3
spec for paid-data alternatives.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from bloasis.data.cache import ParquetCache

if TYPE_CHECKING:
    import pandas as pd


EARNINGS_COLUMNS = ("eps_estimate", "reported_eps", "surprise_pct")


class YfEarningsFetcher:
    """Earnings history fetcher with parquet cache.

    Returns a DataFrame indexed by earnings date (UTC, midnight) with
    columns `[eps_estimate, reported_eps, surprise_pct]`. Rows with all
    NaN values are dropped (yfinance returns 'next earnings' rows that
    are still future placeholders).
    """

    def __init__(
        self,
        cache: ParquetCache | None = None,
        max_age_hours: int = 24,
        limit: int = 20,
    ) -> None:
        self._cache = cache
        self._max_age = timedelta(hours=max_age_hours)
        self._limit = limit

    def fetch(self, symbol: str) -> pd.DataFrame:
        if not symbol:
            raise ValueError("symbol must be non-empty")

        key = self._cache_key(symbol)
        if self._cache is not None:
            cached = self._cache.get(key, max_age=self._max_age)
            if cached is not None:
                return cached

        df = self._download(symbol)
        if self._cache is not None:
            self._cache.put(key, df)
        return df

    def _cache_key(self, symbol: str) -> str:
        safe = symbol.replace("^", "IDX_")
        return f"earnings_{safe}_n{self._limit}"

    def _download(self, symbol: str) -> pd.DataFrame:
        import pandas as pd
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        try:
            raw = ticker.get_earnings_dates(limit=self._limit)
        except Exception as e:
            raise ValueError(f"no earnings data for {symbol!r}: {e}") from e

        if raw is None or raw.empty:
            # Empty frame with the right schema — caller handles "no data".
            return pd.DataFrame(columns=list(EARNINGS_COLUMNS)).rename_axis("timestamp")

        # yfinance columns are pretty-printed; map to canonical names.
        col_map = {
            "EPS Estimate": "eps_estimate",
            "Reported EPS": "reported_eps",
            "Surprise(%)": "surprise_pct",
        }
        renamed = raw.rename(columns=col_map)
        keep = [c for c in EARNINGS_COLUMNS if c in renamed.columns]
        out = renamed[keep].copy()

        # Drop rows where reported_eps is NaN — those are future earnings
        # placeholders ("next quarter") which we cannot use.
        if "reported_eps" in out.columns:
            out = out.dropna(subset=["reported_eps"])

        # Normalize index to UTC midnight (same as ohlcv fetcher).
        if out.index.tz is not None:
            out.index = out.index.tz_convert("UTC").tz_localize(None)
        out.index = out.index.normalize()
        out.index.name = "timestamp"
        out = out.sort_index()  # ascending date

        # Make sure all canonical columns exist.
        for c in EARNINGS_COLUMNS:
            if c not in out.columns:
                out[c] = float("nan")
        return cast("pd.DataFrame", out[list(EARNINGS_COLUMNS)])
