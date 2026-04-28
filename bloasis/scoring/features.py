"""FeatureVector — per-(symbol, timestamp) feature snapshot.

Convention:
- All numeric features are `float`. Missing values are `float('nan')`, not
  Optional[float] — keeps math/array conversion zero-overhead and matches
  LightGBM's native NaN handling for Phase 3 ML.
- Frozen + slots: backtests construct millions of these; allocation matters.
- `to_array()` produces a fixed-order numpy row matching `FEATURE_COLUMNS`
  for ML training/inference.

`feature_version` lets us evolve extraction logic without losing old data;
ML training filters by version.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import ClassVar

import numpy as np

# Order matters — `to_array()` and ML inputs depend on this. Append-only;
# bump `feature_version` whenever you change the order or remove a column.
FEATURE_COLUMNS: tuple[str, ...] = (
    # Fundamentals
    "per",
    "pbr",
    "market_cap",
    "profit_margin",
    "roe",
    "debt_to_equity",
    "current_ratio",
    # Technicals
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "adx_14",
    "atr_14",
    "bb_width",
    # Price/volume derived
    "momentum_20d",
    "momentum_60d",
    "volatility_20d",
    "volume_ratio_20d",
    # Context (raw — classify_regime applied at display time)
    "vix",
    "spy_above_sma200",
    "vix_zscore_60d",
    # Sentiment (live only; NaN in backtest periods predating live deployment)
    "sentiment_score",
    "news_count",
)


def _nan() -> float:
    return float("nan")


@dataclass(frozen=True, slots=True)
class FeatureVector:
    timestamp: datetime
    symbol: str
    feature_version: int

    # Identity / context (not in FEATURE_COLUMNS — they're metadata)
    sector: str | None = None

    # Fundamentals
    per: float = field(default_factory=_nan)
    pbr: float = field(default_factory=_nan)
    market_cap: float = field(default_factory=_nan)
    profit_margin: float = field(default_factory=_nan)
    roe: float = field(default_factory=_nan)
    debt_to_equity: float = field(default_factory=_nan)
    current_ratio: float = field(default_factory=_nan)

    # Technicals
    rsi_14: float = field(default_factory=_nan)
    macd: float = field(default_factory=_nan)
    macd_signal: float = field(default_factory=_nan)
    macd_hist: float = field(default_factory=_nan)
    adx_14: float = field(default_factory=_nan)
    atr_14: float = field(default_factory=_nan)
    bb_width: float = field(default_factory=_nan)

    # Price/volume derived
    momentum_20d: float = field(default_factory=_nan)
    momentum_60d: float = field(default_factory=_nan)
    volatility_20d: float = field(default_factory=_nan)
    volume_ratio_20d: float = field(default_factory=_nan)

    # Context (raw)
    vix: float = field(default_factory=_nan)
    spy_above_sma200: float = field(default_factory=_nan)  # 0.0 / 1.0 / NaN
    vix_zscore_60d: float = field(default_factory=_nan)

    # Sentiment
    sentiment_score: float = field(default_factory=_nan)
    news_count: float = field(default_factory=_nan)

    FEATURE_COLUMNS: ClassVar[tuple[str, ...]] = FEATURE_COLUMNS

    def to_array(self) -> np.ndarray:
        """Fixed-order numpy row matching `FEATURE_COLUMNS`."""
        return np.array([getattr(self, c) for c in FEATURE_COLUMNS], dtype=np.float64)

    def to_db_row(self) -> dict[str, float | str | int | None]:
        """Mapping suitable for `feature_log` table insert.

        Keys match `feature_log` columns. `spy_above_sma200` is converted
        to int (0/1) since the schema uses INTEGER. NaN floats become None
        so SQLite stores NULL rather than the literal string 'nan'.
        """
        d: dict[str, float | str | int | None] = {
            "timestamp": self.timestamp,  # type: ignore[dict-item]
            "symbol": self.symbol,
            "feature_version": self.feature_version,
            "sector": self.sector,
        }
        for col in FEATURE_COLUMNS:
            v = getattr(self, col)
            d[col] = _float_or_none(v)
        # Schema uses INTEGER for spy_above_sma200 — coerce.
        spy = d["spy_above_sma200"]
        if isinstance(spy, float):
            d["spy_above_sma200"] = int(spy)
        nc = d["news_count"]
        if isinstance(nc, float):
            d["news_count"] = int(nc)
        return d

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _float_or_none(v: float) -> float | None:
    if isinstance(v, float) and math.isnan(v):
        return None
    return v
