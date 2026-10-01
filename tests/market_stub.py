"""Shared stub for the VIX + SPY market-context fetcher.

The live candidate builder reads the VIX close and SPY returns out of the
prefetched panel (#91) and refuses to trade without a VIX close, so tests
that drive it must hand prefetch a real `MarketContext`, not a bare MagicMock.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from bloasis.data.fetchers.protocols import MarketContext


def market_fetcher(index: pd.DatetimeIndex | list[pd.Timestamp], vix: float = 18.0) -> MagicMock:
    """A fetcher whose `fetch()` returns a flat VIX and SPY close on `index`.

    Pass the same index the test's OHLCV stub uses, so the as-of slicing
    sees the same timezone convention as the bars.
    """
    idx = pd.DatetimeIndex(index)
    fetcher = MagicMock()
    fetcher.fetch.return_value = MarketContext(
        vix=pd.Series(vix, index=idx), spy_close=pd.Series(400.0, index=idx)
    )
    return fetcher
