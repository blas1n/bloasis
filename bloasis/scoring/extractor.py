"""Pure feature extraction.

Same code path runs in live and backtest. The only thing that differs is
the data slice in `ExtractionContext` — which the caller is responsible
for time-bounding correctly. We enforce the bound with assertions in
`__post_init__` so look-ahead bias becomes a hard fail at the call site
instead of a silent statistical bug.

Limitation L007 (see `docs/limitations.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from bloasis.scoring.derived import (
    momentum,
    vix_zscore_60d,
    volatility_annualized,
    volume_ratio,
)
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.indicators import adx_14, atr_14, bb_width, macd, rsi_14, sma

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """All data needed to compute features at one (symbol, timestamp).

    `ohlcv` and `vix_series` MUST be sliced to `[-inf, timestamp]` by the
    caller — the assertion in `__post_init__` will fire if any data point
    has a label > timestamp. There is no fallback that "fixes" this; the
    test suite is expected to verify backtest engines pass clean slices.

    `spy_close_series` is similarly time-bounded; we use the last bar to
    compare against its SMA200.

    Fundamentals are point-in-time best effort (see L002). yfinance's
    `Ticker.info` returns the most recent quarterly snapshot; backtesters
    pass quarterly lag-1 to approximate PIT.

    `news_sentiment` and `news_count` come pre-scored from
    `bloasis.data.sentiment`; backtest periods that predate live deployment
    pass `None` (NaN propagates).
    """

    timestamp: datetime
    symbol: str
    feature_version: int

    sector: str | None
    ohlcv: pd.DataFrame  # ['open','high','low','close','volume'] indexed by datetime
    fundamentals: dict[str, float | None] = field(default_factory=dict)

    vix_series: pd.Series | None = None
    spy_close_series: pd.Series | None = None

    sentiment_score: float | None = None
    news_count: int | None = None

    def __post_init__(self) -> None:
        if self.ohlcv is None or self.ohlcv.empty:
            raise ValueError(f"empty ohlcv for {self.symbol} @ {self.timestamp}")

        # Normalize comparison to naive UTC. `self.timestamp` may be tz-aware
        # (live path) or naive (some backtest paths); pandas indices likewise.
        # Strip tz on both sides so > works without TypeError.
        ts_naive = _to_naive_utc(self.timestamp)

        ohlcv_max = _to_naive_utc(self.ohlcv.index.max())
        if ohlcv_max > ts_naive:
            raise ValueError(
                "look-ahead bias: ohlcv has data after extraction timestamp "
                f"({ohlcv_max} > {ts_naive})"
            )
        if self.vix_series is not None and not self.vix_series.empty:
            vix_max = _to_naive_utc(self.vix_series.index.max())
            if vix_max > ts_naive:
                raise ValueError(f"look-ahead in vix_series ({vix_max} > {ts_naive})")
        if self.spy_close_series is not None and not self.spy_close_series.empty:
            spy_max = _to_naive_utc(self.spy_close_series.index.max())
            if spy_max > ts_naive:
                raise ValueError(f"look-ahead in spy_close_series ({spy_max} > {ts_naive})")


def _to_naive_utc(value: object) -> datetime:
    """Coerce a datetime-ish value to a naive UTC `datetime`.

    Used for comparisons where mixed naive / tz-aware inputs would otherwise
    raise TypeError. We round-trip through pandas Timestamp to absorb
    NumPy datetime64, pandas Timestamp, and stdlib datetime uniformly.
    """
    import pandas as pd

    ts = pd.Timestamp(value)  # type: ignore[arg-type]
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


class FeatureExtractor:
    """Extract a `FeatureVector` from a properly-sliced context."""

    VERSION = 1

    def extract(self, ctx: ExtractionContext) -> FeatureVector:
        if ctx.feature_version != self.VERSION:
            raise ValueError(
                f"feature_version mismatch: ctx={ctx.feature_version} extractor={self.VERSION}"
            )

        ohlcv = ctx.ohlcv
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        volume = ohlcv["volume"]

        m, msig, mhist = macd(close)

        spy_above = float("nan")
        if ctx.spy_close_series is not None and not ctx.spy_close_series.empty:
            spy_sma = sma(ctx.spy_close_series, period=200)
            spy_last = float(ctx.spy_close_series.iloc[-1])
            if not _is_nan(spy_sma) and not _is_nan(spy_last):
                spy_above = 1.0 if spy_last > spy_sma else 0.0

        vix_value = float("nan")
        vix_z = float("nan")
        if ctx.vix_series is not None and not ctx.vix_series.empty:
            vix_value = float(ctx.vix_series.iloc[-1])
            vix_z = vix_zscore_60d(ctx.vix_series)

        f = ctx.fundamentals
        return FeatureVector(
            timestamp=ctx.timestamp,
            symbol=ctx.symbol,
            feature_version=self.VERSION,
            sector=ctx.sector,
            # Fundamentals
            per=_get_float(f, "per"),
            pbr=_get_float(f, "pbr"),
            market_cap=_get_float(f, "market_cap"),
            profit_margin=_get_float(f, "profit_margin"),
            roe=_get_float(f, "roe"),
            debt_to_equity=_get_float(f, "debt_to_equity"),
            current_ratio=_get_float(f, "current_ratio"),
            # Technicals
            rsi_14=rsi_14(close),
            macd=m,
            macd_signal=msig,
            macd_hist=mhist,
            adx_14=adx_14(high, low, close),
            atr_14=atr_14(high, low, close),
            bb_width=bb_width(close),
            # Derived
            momentum_20d=momentum(close, lookback=20),
            momentum_60d=momentum(close, lookback=60),
            volatility_20d=volatility_annualized(close, window=20),
            volume_ratio_20d=volume_ratio(volume, window=20),
            # Context
            vix=vix_value,
            spy_above_sma200=spy_above,
            vix_zscore_60d=vix_z,
            # Sentiment
            sentiment_score=ctx.sentiment_score
            if ctx.sentiment_score is not None
            else float("nan"),
            news_count=float(ctx.news_count) if ctx.news_count is not None else float("nan"),
        )


def _get_float(d: dict[str, float | None], key: str) -> float:
    v = d.get(key)
    if v is None:
        return float("nan")
    return float(v)


def _is_nan(v: float) -> bool:
    return v != v  # standard NaN check
