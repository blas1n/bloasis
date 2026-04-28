"""Market context fetcher: VIX index + SPY ETF close series.

These are the inputs to `classify_regime()` and several composite factors.
We reuse the OHLCV fetcher under the hood — VIX (`^VIX`) and SPY are
just regular ticker fetches as far as yfinance is concerned.
"""

from __future__ import annotations

from datetime import date

from bloasis.data.fetchers.protocols import MarketContext, OhlcvFetcher

VIX_SYMBOL = "^VIX"
SPY_SYMBOL = "SPY"


class YfMarketContextFetcher:
    def __init__(self, ohlcv: OhlcvFetcher) -> None:
        self._ohlcv = ohlcv

    def fetch(self, start: date, end: date) -> MarketContext:
        vix_df = self._ohlcv.fetch(VIX_SYMBOL, start, end)
        spy_df = self._ohlcv.fetch(SPY_SYMBOL, start, end)
        return MarketContext(vix=vix_df["close"], spy_close=spy_df["close"])
