"""Regime-aware position sizing overlay.

Combines two ideas from the momentum literature:

1. **Barroso & Santa-Clara (2015) — "Momentum Has Its Moments"**: scale
   exposure inversely to the strategy's recent realized volatility, so
   total portfolio vol stays near a target. We use SPY's 126-day realized
   vol as a proxy for market state.

2. **Daniel & Moskowitz (2016) — "Momentum Crashes"**: cross-sectional
   momentum is most dangerous after extended bear markets, when "loser"
   stocks have option-like recovery payoffs. The classical bear-gate is
   `past 24-month cumulative return ≤ 0` → additional derisk.

Long-only Bloasis specific note: the DM 2016 alpha mechanism is partly
on the *short* leg (loser-as-call), which we don't have. We therefore
favour the simpler BSC variant + DM bear gate as a layered safety net,
not the full GJR-GARCH dynamic optimal weight from DM Appendix C.

See ~/Docs/bloasis/Research_DM_Dynamic_Momentum.md for the full
derivation and references.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class RegimeOverlayParams:
    """Parameters for `compute_regime_scale`. Defaults match
    `bloasis.config.RegimeOverlayConfig` and PR12 design lock-in §6."""

    enabled: bool = True
    sigma_target: float = 0.12  # annualized target vol
    vol_lookback_days: int = 126  # ~6 months realized vol window (BSC)
    bear_lookback_days: int = 504  # ~24 months for DM bear gate
    bear_scale: float = 0.5  # additional derisk during bear state
    scale_clip: tuple[float, float] = (0.0, 1.5)


DEFAULT_OVERLAY = RegimeOverlayParams()


def compute_regime_scale(
    daily_returns: pd.Series,
    *,
    params: RegimeOverlayParams = DEFAULT_OVERLAY,
) -> float:
    """Return a position-size scale factor based on recent SPY behaviour.

    Multiply per-trade `size_pct` by this value at entry. Always returns a
    finite number; cold start and degenerate states yield 1.0 (pass-through).

    Acceptance anchors (see ~/Docs/bloasis/Research_DM_Dynamic_Momentum.md):
        2020-03 (COVID panic)         → ~0.30
        2009-03 (post-GFC bear gate)  → ≤ 0.20
        2017-06 (calm bull, ceiling)  → 1.5
    """
    if not params.enabled:
        return 1.0

    if daily_returns is None or len(daily_returns) < params.vol_lookback_days:
        return 1.0

    arr = np.asarray(daily_returns.to_numpy(dtype=np.float64))
    arr = arr[~np.isnan(arr)]
    if arr.size < params.vol_lookback_days:
        return 1.0

    vol_window = arr[-params.vol_lookback_days :]
    realized_vol = float(np.std(vol_window, ddof=1)) * math.sqrt(TRADING_DAYS_PER_YEAR)

    # BSC: target_vol / realized_vol, with floor on realized to avoid blowup.
    bsc_scale = params.sigma_target / max(realized_vol, 0.01)
    lo, hi = params.scale_clip
    bsc_scale = float(np.clip(bsc_scale, lo, hi))

    # DM bear gate — sum of returns over 24-month lookback ≤ 0.
    bear_window_size = min(params.bear_lookback_days, arr.size)
    bear_window = arr[-bear_window_size:]
    bear_state = float(np.sum(bear_window)) <= 0.0
    if bear_state:
        bsc_scale *= params.bear_scale

    return float(bsc_scale)
