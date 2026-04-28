"""Provider-agnostic Protocol interfaces for the data layer.

Concrete implementations (yfinance, Finnhub, future EODHD) live alongside
this file. Code that consumes data — feature extraction, backtest, scoring
— takes these Protocols as parameters so the underlying provider can swap
without touching downstream logic.

OHLCV column convention (across all `OhlcvFetcher` impls):
    DataFrame indexed by `pd.DatetimeIndex` (UTC, daily bars).
    Columns: ['open', 'high', 'low', 'close', 'volume'] (lower case, floats).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class FundamentalRow:
    """One symbol's fundamentals snapshot at fetch time."""

    symbol: str
    fetched_at: datetime
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    pe_ratio_ttm: float | None = None
    pb_ratio: float | None = None
    dollar_volume_avg: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None


@dataclass(frozen=True, slots=True)
class MarketContext:
    """VIX and SPY series for regime classification.

    Both are pandas Series indexed by `pd.DatetimeIndex` (daily close).
    Length must match across the two series; callers may align before use.
    """

    vix: pd.Series
    spy_close: pd.Series


@dataclass(frozen=True, slots=True)
class NewsItem:
    """One news article. `headline` is what gets passed to the LLM."""

    symbol: str
    published_at: datetime
    headline: str
    url: str
    source: str | None = None


@runtime_checkable
class OhlcvFetcher(Protocol):
    """Daily OHLCV fetcher."""

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...


@runtime_checkable
class FundamentalsFetcher(Protocol):
    """Fundamentals fetcher.

    `fetch_bulk()` is the primary path — one or a few API calls returns
    fundamentals for the entire universe. `fetch_single()` is a per-symbol
    fallback for stocks missing from the bulk response.
    """

    def fetch_bulk(self, max_count: int = 1000) -> list[FundamentalRow]: ...

    def fetch_single(self, symbol: str) -> FundamentalRow | None: ...


@runtime_checkable
class MarketContextFetcher(Protocol):
    """VIX + SPY fetcher for regime classification inputs."""

    def fetch(self, start: date, end: date) -> MarketContext: ...


@runtime_checkable
class NewsFetcher(Protocol):
    """News headline fetcher.

    Implementations should respect their provider's rate limit internally
    (e.g., Finnhub free tier = 60/min). Callers should not need a separate
    limiter wrapper.
    """

    def fetch(self, symbol: str, since: datetime) -> list[NewsItem]: ...
