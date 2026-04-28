"""Composite factor scoring via cross-section z-score.

Composites group raw features into 7 interpretable buckets:

    value      <- per (lower is better), pbr (lower is better), profit_margin (higher is better)
    quality    <- roe, debt_to_equity (lower is better), current_ratio
    momentum   <- momentum_20d, momentum_60d, rsi_14
    technical  <- macd_hist, adx_14, bb_width
    volatility <- volatility_20d (lower is better), atr_14 (lower is better)
    liquidity  <- log(market_cap), volume_ratio_20d
    sentiment  <- sentiment_score, log1p(news_count)

For each feature within a composite:
    1. Compute cross-sectional z-score across all symbols at the same
       timestamp: (x - mean) / std. Clip to [-cap, cap] (default cap=3)
       to bound outlier influence.
    2. Flip sign for "lower is better" features so higher composite =
       better candidate.
    3. Map z to [0, 1] via min-max with the same cap (z = -3 → 0, z = +3 → 1).

Composite score = mean of constituent unit scores, ignoring NaNs. If
all constituents are NaN, composite is NaN (signals "not enough data").

This module is pure compute. NaN-safe via `numpy.nanmean`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from bloasis.scoring.features import FeatureVector

Z_CAP = 3.0  # outlier clip threshold (in standard deviations)


# Each composite is a tuple of (feature_name, sign).
# sign = +1: higher raw value is better
# sign = -1: lower raw value is better (we flip the z-score)
COMPOSITE_SPEC: dict[str, tuple[tuple[str, int], ...]] = {
    "value": (
        ("per", -1),
        ("pbr", -1),
        ("profit_margin", +1),
    ),
    "quality": (
        ("roe", +1),
        ("debt_to_equity", -1),
        ("current_ratio", +1),
    ),
    "momentum": (
        ("momentum_20d", +1),
        ("momentum_60d", +1),
        ("rsi_14", +1),
    ),
    "technical": (
        ("macd_hist", +1),
        ("adx_14", +1),
        ("bb_width", +1),
    ),
    "volatility": (
        ("volatility_20d", -1),
        ("atr_14", -1),
    ),
    "liquidity": (
        ("market_cap_log", +1),  # synthesized — see _prepare()
        ("volume_ratio_20d", +1),
    ),
    "sentiment": (
        ("sentiment_score", +1),
        ("news_count_log", +1),  # synthesized — see _prepare()
    ),
}

COMPOSITE_NAMES: tuple[str, ...] = tuple(COMPOSITE_SPEC.keys())


@dataclass(frozen=True, slots=True)
class CompositeVector:
    """Per-symbol composite scores at one timestamp. Each value in [0, 1] or NaN."""

    symbol: str
    sector: str | None
    value: float
    quality: float
    momentum: float
    technical: float
    volatility: float
    liquidity: float
    sentiment: float

    NAMES: ClassVar[tuple[str, ...]] = COMPOSITE_NAMES

    def to_array(self) -> np.ndarray:
        return np.array([getattr(self, name) for name in COMPOSITE_NAMES], dtype=np.float64)


@dataclass(frozen=True, slots=True)
class CompositeBuilder:
    """Build composites from a cross-section of FeatureVectors.

    Stateless — instantiate freely. The `z_cap` parameter is the only
    knob; default 3.0 (standard deviations) clips outliers without
    eliminating their directional signal.
    """

    z_cap: float = Z_CAP
    log_features: tuple[str, ...] = field(default=("market_cap", "news_count"))

    def build(self, vectors: list[FeatureVector]) -> list[CompositeVector]:
        if not vectors:
            return []
        symbols = [v.symbol for v in vectors]
        sectors = [v.sector for v in vectors]

        # Step 1: prepare a (n_symbols x n_raw_features) matrix.
        prepared = self._prepare(vectors)

        # Step 2: cross-section z-score each column, clip, sign-adjust, unitize.
        unit_scores: dict[str, np.ndarray] = {}
        for raw_name, sign in self._all_constituents():
            col = prepared[raw_name]
            unit_scores[raw_name] = self._unitize(col, sign=sign)

        # Step 3: mean across constituents per composite. NaN-aware.
        results: list[CompositeVector] = []
        for i, (sym, sec) in enumerate(zip(symbols, sectors, strict=True)):
            comp_values: dict[str, float] = {}
            for comp_name, constituents in COMPOSITE_SPEC.items():
                row_values = np.array(
                    [unit_scores[raw_name][i] for raw_name, _sign in constituents],
                    dtype=np.float64,
                )
                # If all NaN → composite NaN (signals "not enough data").
                if np.all(np.isnan(row_values)):
                    comp_values[comp_name] = float("nan")
                else:
                    comp_values[comp_name] = float(np.nanmean(row_values))
            results.append(CompositeVector(symbol=sym, sector=sec, **comp_values))
        return results

    # ----- helpers -----

    def _prepare(self, vectors: list[FeatureVector]) -> dict[str, np.ndarray]:
        """Build a column matrix keyed by raw feature name.

        Synthesizes log-transformed columns for highly skewed features
        (market_cap spans 6+ orders of magnitude, news_count is heavy-tailed).
        """
        n = len(vectors)
        out: dict[str, np.ndarray] = {}
        # Pull every constituent name once.
        for raw_name, _sign in self._all_constituents():
            if raw_name == "market_cap_log":
                arr = np.array([_log1p_safe(v.market_cap) for v in vectors], dtype=np.float64)
            elif raw_name == "news_count_log":
                arr = np.array([_log1p_safe(v.news_count) for v in vectors], dtype=np.float64)
            else:
                arr = np.array([getattr(v, raw_name) for v in vectors], dtype=np.float64)
            assert arr.shape == (n,)
            out[raw_name] = arr
        return out

    def _unitize(self, col: np.ndarray, *, sign: int) -> np.ndarray:
        """Cross-section z-score → clip → sign-flip → map to [0, 1].

        NaNs in input remain NaN in output. If std is zero (all values
        equal), returns 0.5 for all (neutral) — represents "no information"
        rather than divide-by-zero.
        """
        valid_mask = ~np.isnan(col)
        if not valid_mask.any():
            return col  # all NaN → all NaN

        valid = col[valid_mask]
        mean = float(np.mean(valid))
        std = float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0

        out = np.full_like(col, fill_value=np.nan)
        if std == 0.0:
            out[valid_mask] = 0.5
            return out

        z = (col[valid_mask] - mean) / std
        z = np.clip(z, -self.z_cap, self.z_cap) * sign
        # Map [-cap, cap] → [0, 1]
        unit = (z + self.z_cap) / (2 * self.z_cap)
        out[valid_mask] = unit
        return out

    def _all_constituents(self) -> list[tuple[str, int]]:
        seen: dict[str, int] = {}
        for constituents in COMPOSITE_SPEC.values():
            for name, sign in constituents:
                seen[name] = sign  # last writer wins (signs are consistent across composites)
        return list(seen.items())


def _log1p_safe(v: float) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return float("nan")
    if v < 0:
        return float("nan")
    return math.log1p(v)
