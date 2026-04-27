"""Data fetchers — Protocol interfaces and concrete implementations.

The Protocol layer (`protocols.py`) keeps the rest of the code provider-
agnostic. Swapping yfinance for EODHD or Sharadar in the future is a
single-module change.
"""

from bloasis.data.fetchers.protocols import (
    FundamentalRow,
    FundamentalsFetcher,
    MarketContext,
    MarketContextFetcher,
    NewsFetcher,
    NewsItem,
    OhlcvFetcher,
)

__all__ = [
    "FundamentalRow",
    "FundamentalsFetcher",
    "MarketContext",
    "MarketContextFetcher",
    "NewsFetcher",
    "NewsItem",
    "OhlcvFetcher",
]
