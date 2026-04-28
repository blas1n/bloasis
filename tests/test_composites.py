"""Tests for `bloasis.scoring.composites`."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from bloasis.scoring.composites import (
    COMPOSITE_NAMES,
    Z_CAP,
    CompositeBuilder,
    CompositeVector,
)
from bloasis.scoring.features import FeatureVector

NOW = datetime.now(tz=UTC)


def _fv(symbol: str, **kwargs: float | str) -> FeatureVector:
    return FeatureVector(timestamp=NOW, symbol=symbol, feature_version=1, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CompositeBuilder.build
# ---------------------------------------------------------------------------


def test_build_empty_returns_empty() -> None:
    assert CompositeBuilder().build([]) == []


def test_build_returns_one_per_input() -> None:
    vecs = [_fv("A", per=10.0, roe=0.2), _fv("B", per=20.0, roe=0.1)]
    out = CompositeBuilder().build(vecs)
    assert len(out) == 2
    assert {o.symbol for o in out} == {"A", "B"}


def test_value_composite_inverts_per_so_low_per_wins() -> None:
    """A symbol with low PER + high profit_margin should beat one with high PER + low margin."""
    vecs = [
        _fv("CHEAP", per=8.0, pbr=1.0, profit_margin=0.20),
        _fv("EXPENSIVE", per=40.0, pbr=10.0, profit_margin=0.05),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["CHEAP"].value > out["EXPENSIVE"].value


def test_quality_composite_higher_roe_wins() -> None:
    vecs = [
        _fv("HIGH_Q", roe=0.30, debt_to_equity=0.3, current_ratio=2.0),
        _fv("LOW_Q", roe=0.05, debt_to_equity=3.0, current_ratio=0.8),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["HIGH_Q"].quality > out["LOW_Q"].quality


def test_volatility_composite_inverts_so_low_vol_wins() -> None:
    vecs = [
        _fv("STABLE", volatility_20d=0.10, atr_14=1.0),
        _fv("WILD", volatility_20d=0.80, atr_14=10.0),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["STABLE"].volatility > out["WILD"].volatility


def test_momentum_composite_higher_better() -> None:
    vecs = [
        _fv("STRONG", momentum_20d=0.20, momentum_60d=0.40, rsi_14=70.0),
        _fv("WEAK", momentum_20d=-0.10, momentum_60d=-0.20, rsi_14=30.0),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["STRONG"].momentum > out["WEAK"].momentum


def test_liquidity_uses_log_market_cap() -> None:
    """1B vs 100B: log scale should still rank correctly."""
    vecs = [
        _fv("MEGA", market_cap=1e12, volume_ratio_20d=1.5),
        _fv("MID", market_cap=2e9, volume_ratio_20d=1.0),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["MEGA"].liquidity > out["MID"].liquidity


def test_sentiment_composite_higher_score_wins() -> None:
    vecs = [
        _fv("GOOD_NEWS", sentiment_score=0.7, news_count=20.0),
        _fv("NO_NEWS", sentiment_score=-0.3, news_count=2.0),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    assert out["GOOD_NEWS"].sentiment > out["NO_NEWS"].sentiment


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_all_nan_constituents_produce_nan_composite() -> None:
    vecs = [_fv("X"), _fv("Y")]  # all defaults are NaN
    out = CompositeBuilder().build(vecs)
    for c in out:
        for name in COMPOSITE_NAMES:
            assert math.isnan(getattr(c, name)), f"{name} should be NaN when no data"


def test_constant_column_yields_neutral_score() -> None:
    """std=0 case: all symbols equal on a feature → 0.5 (neutral) for that constituent."""
    vecs = [
        _fv("A", per=15.0),
        _fv("B", per=15.0),
        _fv("C", per=15.0),
    ]
    out = CompositeBuilder().build(vecs)
    # value composite has 3 constituents, only `per` populated. Neutral 0.5
    # on PER, NaN on the other two (pbr, profit_margin all NaN). nanmean of
    # [0.5, NaN, NaN] = 0.5.
    for c in out:
        assert c.value == pytest.approx(0.5, abs=1e-9)


def test_unit_score_bounded_in_zero_one() -> None:
    rng = np.random.default_rng(42)
    vecs = [
        _fv(
            f"S{i}",
            per=float(rng.uniform(5, 50)),
            pbr=float(rng.uniform(0.5, 10)),
            profit_margin=float(rng.uniform(-0.1, 0.4)),
            roe=float(rng.uniform(-0.1, 0.5)),
            debt_to_equity=float(rng.uniform(0, 5)),
            current_ratio=float(rng.uniform(0.5, 3.0)),
            momentum_20d=float(rng.uniform(-0.3, 0.3)),
            momentum_60d=float(rng.uniform(-0.5, 0.5)),
            rsi_14=float(rng.uniform(20, 80)),
            macd_hist=float(rng.uniform(-1, 1)),
            adx_14=float(rng.uniform(10, 50)),
            bb_width=float(rng.uniform(0.02, 0.20)),
            volatility_20d=float(rng.uniform(0.1, 0.6)),
            atr_14=float(rng.uniform(0.5, 5.0)),
            market_cap=float(rng.uniform(1e9, 3e12)),
            volume_ratio_20d=float(rng.uniform(0.5, 3.0)),
            sentiment_score=float(rng.uniform(-1, 1)),
            news_count=float(rng.uniform(0, 30)),
        )
        for i in range(20)
    ]
    out = CompositeBuilder().build(vecs)
    for c in out:
        for name in COMPOSITE_NAMES:
            v = getattr(c, name)
            assert 0.0 <= v <= 1.0, f"{c.symbol}.{name}={v} out of [0,1]"


def test_extreme_outlier_clipped() -> None:
    """An extreme outlier should not dominate; clipping caps influence."""
    vecs = [
        _fv("OUTLIER", per=1e9),  # absurd
        _fv("NORMAL_A", per=10.0),
        _fv("NORMAL_B", per=12.0),
        _fv("NORMAL_C", per=15.0),
    ]
    out = {c.symbol: c for c in CompositeBuilder().build(vecs)}
    # With clipping at z_cap=3, the outlier's influence is bounded:
    # mean and std are dominated by it, but normals shouldn't all bunch up.
    normals = [out[s].value for s in ("NORMAL_A", "NORMAL_B", "NORMAL_C")]
    # All normals close to the same unit score (since they're tightly grouped vs the outlier)
    assert max(normals) - min(normals) < 0.1


def test_to_array_returns_correct_length() -> None:
    cv = CompositeVector(
        symbol="X",
        sector=None,
        value=0.5,
        quality=0.4,
        momentum=0.6,
        technical=0.3,
        volatility=0.7,
        liquidity=0.5,
        sentiment=0.5,
    )
    arr = cv.to_array()
    assert arr.shape == (len(COMPOSITE_NAMES),)


def test_z_cap_default_is_three() -> None:
    assert Z_CAP == 3.0
