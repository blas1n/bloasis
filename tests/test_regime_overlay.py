"""Tests for `bloasis.scoring.regime_overlay`.

Barroso-Santa-Clara constant-vol scaling + Daniel-Moskowitz bear gate.
See ~/Docs/bloasis/Research_DM_Dynamic_Momentum.md for derivation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from bloasis.scoring.regime_overlay import (
    DEFAULT_OVERLAY,
    RegimeOverlayParams,
    compute_regime_scale,
)


def _daily_returns(values: list[float]) -> pd.Series:
    """Build a daily-frequency Series from a list of returns."""
    idx = pd.bdate_range("2020-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# Cold start — insufficient history → scale 1.0 (no derisk)
# ---------------------------------------------------------------------------


def test_cold_start_returns_one() -> None:
    """Less than vol_lookback bars → no scaling applied."""
    rets = _daily_returns([0.001] * 50)  # need 126
    scale = compute_regime_scale(rets)
    assert scale == 1.0


def test_empty_series_returns_one() -> None:
    rets = pd.Series([], dtype=float)
    assert compute_regime_scale(rets) == 1.0


# ---------------------------------------------------------------------------
# Constant-vol scaling — calm markets hit the ceiling, panic hits the floor
# ---------------------------------------------------------------------------


def test_calm_market_hits_ceiling() -> None:
    """Realized vol ~6% annualized → 12%/6% = 2.0 → clipped to 1.5."""
    rng = np.random.default_rng(42)
    # ~6% annualized vol = ~0.378% daily std
    daily_std = 0.06 / math.sqrt(252)
    rets = _daily_returns(rng.normal(0.0005, daily_std, 600).tolist())
    scale = compute_regime_scale(rets)
    assert scale == pytest.approx(1.5, abs=0.05)


def test_panic_market_drops_below_one() -> None:
    """Realized vol ~50% annualized (COVID-like) → 12%/50% ≈ 0.24.

    Bull period is deterministically positive so 24-month cumulative > 0
    and bear gate stays OFF — isolating the BSC scaling effect.
    """
    rng = np.random.default_rng(7)
    daily_std = 0.50 / math.sqrt(252)
    # Strong deterministic bull drift (20bps/day) over 504 days = ~100% cumulative
    # — large enough that any plausible panic-period drawdown leaves total > 0
    bull_rets = [0.002] * 504
    # Panic with high vol but ~zero drift over last 126 days
    panic_rets = rng.normal(0.0, daily_std, 126).tolist()
    rets = _daily_returns(bull_rets + panic_rets)
    scale = compute_regime_scale(rets)
    # BSC ≈ 0.12 / 0.50 ≈ 0.24, no bear penalty.
    assert 0.20 <= scale <= 0.40


# ---------------------------------------------------------------------------
# Bear gate — 24-month cumulative ≤ 0 triggers ×0.5 derisk
# ---------------------------------------------------------------------------


def test_bear_gate_active_halves_scale() -> None:
    """24m cumulative negative → bear=True → scale ×= 0.5."""
    # Constant moderate negative drift over 504 days, then 126 normal vol
    rng = np.random.default_rng(11)
    daily_std = 0.20 / math.sqrt(252)  # ~20% ann vol → BSC base ≈ 0.6
    # Total return over 630 days < 0
    rets_504 = rng.normal(-0.001, daily_std, 504).tolist()
    rets_126 = rng.normal(-0.0005, daily_std, 126).tolist()
    rets = _daily_returns(rets_504 + rets_126)
    scale = compute_regime_scale(rets)
    # BSC base ~0.6, × 0.5 bear = ~0.3
    assert 0.20 <= scale <= 0.45


def test_bear_gate_inactive_normal_scale() -> None:
    """Strong bull cumulative (positive) → bear gate off → no extra ×0.5."""
    rng = np.random.default_rng(13)
    daily_std = 0.20 / math.sqrt(252)
    rets = _daily_returns(rng.normal(0.001, daily_std, 630).tolist())
    scale = compute_regime_scale(rets)
    # BSC base 0.12/0.20 = 0.6, no bear penalty → 0.6
    assert 0.45 <= scale <= 0.85


# ---------------------------------------------------------------------------
# Custom params (config injection)
# ---------------------------------------------------------------------------


def test_custom_sigma_target() -> None:
    """Higher sigma_target → larger scale (less aggressive derisk)."""
    rng = np.random.default_rng(17)
    daily_std = 0.20 / math.sqrt(252)
    rets = _daily_returns(rng.normal(0.001, daily_std, 600).tolist())
    s_default = compute_regime_scale(rets, params=DEFAULT_OVERLAY)
    s_higher = compute_regime_scale(rets, params=RegimeOverlayParams(sigma_target=0.20))
    assert s_higher > s_default


def test_custom_clip_caps_leverage() -> None:
    """scale_clip upper bound caps even when realized vol is super low.

    Use deterministic positive drift to keep bear gate OFF.
    """
    daily_std = 0.03 / math.sqrt(252)  # 3% annualized — calm
    rng = np.random.default_rng(19)
    # Drift +0.001/day ensures positive cumulative, vol stays ~3%
    rets_arr = (0.001 + rng.normal(0.0, daily_std, 600)).tolist()
    rets = _daily_returns(rets_arr)
    s = compute_regime_scale(rets, params=RegimeOverlayParams(scale_clip=(0.0, 1.0)))
    assert s == pytest.approx(1.0)


def test_disabled_params_returns_one() -> None:
    """`enabled=False` → always 1.0 regardless of vol state."""
    rng = np.random.default_rng(23)
    daily_std = 0.50 / math.sqrt(252)
    rets = _daily_returns(rng.normal(-0.005, daily_std, 600).tolist())
    s = compute_regime_scale(rets, params=RegimeOverlayParams(enabled=False))
    assert s == 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_zero_vol_doesnt_explode() -> None:
    """Constant returns (vol=0) — guard against div-by-zero, return ceiling."""
    rets = _daily_returns([0.0] * 600)
    s = compute_regime_scale(rets)
    # 24m cum = 0, bear gate triggers (≤ 0)
    # vol=0 protected → BSC scale clipped to upper, then × 0.5 = 0.75
    assert math.isfinite(s)
    assert 0.0 <= s <= 1.5


def test_nan_returns_skipped() -> None:
    """Series with NaN — function should still produce a finite scale."""
    rng = np.random.default_rng(29)
    daily_std = 0.20 / math.sqrt(252)
    rets_arr = rng.normal(0.0005, daily_std, 600).tolist()
    rets_arr[10] = float("nan")
    rets = _daily_returns(rets_arr)
    s = compute_regime_scale(rets)
    assert math.isfinite(s)
    assert 0.0 <= s <= 1.5
