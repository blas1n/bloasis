"""yfinance annual financial statements fetcher.

Returns a normalized DataFrame indexed by fiscal year-end date with a
fixed set of canonical columns (Revenue, EBITDA, NetIncome, FreeCashFlow,
TotalDebt, StockholdersEquity). Used by `FundamentalLLMScorer`
(Phase 3 Candidate B-modern) — see
`~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md` §B.

yfinance returns ~5 fiscal years of annual statements (vs only 5
quarters of quarterly), so multi-year backtest (2021-2025+) is feasible.
PIT (point-in-time) note: caller MUST slice by `index < timestamp` —
fiscal year-end is itself the announcement date approximation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from bloasis.data.cache import ParquetCache

if TYPE_CHECKING:
    import pandas as pd


CANONICAL_FIELDS = (
    "Revenue",
    "EBITDA",
    "NetIncome",
    "FreeCashFlow",
    "TotalDebt",
    "StockholdersEquity",
)


# Map (statement, ordered yfinance row aliases) → canonical field. First
# alias found wins. yfinance row labels vary subtly across tickers.
INCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "Revenue": ("Total Revenue", "Operating Revenue"),
    "EBITDA": ("EBITDA", "Normalized EBITDA"),
    "NetIncome": ("Net Income", "Net Income From Continuing Operation Net Minority Interest"),
}
CASHFLOW_ALIASES: dict[str, tuple[str, ...]] = {
    "FreeCashFlow": ("Free Cash Flow",),
}
BALANCE_ALIASES: dict[str, tuple[str, ...]] = {
    "TotalDebt": ("Total Debt", "Net Debt"),
    "StockholdersEquity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
}


class YfFinancialsFetcher:
    """Quarterly financial statements with parquet cache.

    Returns a DataFrame indexed by quarter-end date (UTC midnight) with
    columns CANONICAL_FIELDS. Rows where every canonical column is NaN
    are dropped.
    """

    def __init__(
        self,
        cache: ParquetCache | None = None,
        max_age_hours: int = 24,
    ) -> None:
        self._cache = cache
        self._max_age = timedelta(hours=max_age_hours)

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

    @staticmethod
    def _cache_key(symbol: str) -> str:
        safe = symbol.replace("^", "IDX_")
        return f"financials_{safe}"

    def _download(self, symbol: str) -> pd.DataFrame:
        import pandas as pd
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        try:
            income = ticker.income_stmt  # annual, ~5 fiscal years
            cashflow = ticker.cashflow
            balance = ticker.balance_sheet
        except Exception as e:
            raise ValueError(f"no financial data for {symbol!r}: {e}") from e

        if income is None or income.empty:
            return pd.DataFrame(columns=list(CANONICAL_FIELDS)).rename_axis("timestamp")

        # Union of quarter-end dates across all three statements. Cast to
        # pd.Timestamp so sorting has a well-defined order.
        all_dates: set[pd.Timestamp] = {pd.Timestamp(d) for d in income.columns}
        for s in (cashflow, balance):
            if s is not None and not s.empty:
                all_dates.update(pd.Timestamp(d) for d in s.columns)
        dates_sorted = sorted(all_dates)

        rows: dict[object, dict[str, float]] = {}
        for d in dates_sorted:
            row: dict[str, float] = dict.fromkeys(CANONICAL_FIELDS, float("nan"))
            for canon, aliases in INCOME_ALIASES.items():
                row[canon] = self._lookup(income, d, aliases)
            for canon, aliases in CASHFLOW_ALIASES.items():
                row[canon] = self._lookup(cashflow, d, aliases)
            for canon, aliases in BALANCE_ALIASES.items():
                row[canon] = self._lookup(balance, d, aliases)
            rows[d] = row

        df = pd.DataFrame.from_dict(rows, orient="index")
        df = df[list(CANONICAL_FIELDS)]
        # Drop rows where every value is NaN.
        df = df.dropna(how="all")
        # Normalize index → naive UTC midnight.
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        df.index = df.index.normalize()
        df.index.name = "timestamp"
        df = df.sort_index()
        return df

    @staticmethod
    def _lookup(stmt: pd.DataFrame | None, col: pd.Timestamp, aliases: tuple[str, ...]) -> float:
        if stmt is None or stmt.empty or col not in stmt.columns:
            return float("nan")
        for alias in aliases:
            if alias in stmt.index:
                v = stmt.at[alias, col]
                if v is None:
                    continue
                try:
                    fv = float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if fv == fv:  # not NaN
                    return fv
        return float("nan")
