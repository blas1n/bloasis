"""Display-time regime classifier.

Per the design discussion, we do **not** persist a `regime` label in
`feature_log`. Instead we store the raw inputs (vix, spy_above_sma200,
vix_zscore_60d) and classify on demand.

If the rule changes, all historical bars are reclassified consistently —
no `feature_version` bump needed for label changes.

Classification rule (v1):
    crisis    : vix > 40
    bear      : vix > 30 OR spy_above_sma200 == 0
    sideways  : 20 < vix <= 30 (and spy above SMA200)
    recovery  : 15 < vix <= 20
    bull      : vix <= 15
"""

from __future__ import annotations

import math
from typing import Literal

RegimeLabel = Literal["crisis", "bear", "sideways", "recovery", "bull"]


def classify_regime(vix: float, spy_above_sma200: float) -> RegimeLabel:
    """Classify market regime from VIX + SPY trend.

    `vix` : current VIX value. NaN treated as bullish-default (rare; only
            happens during data outages, where we prefer not to over-react).
    `spy_above_sma200` : 0.0 (below) / 1.0 (above) / NaN (unknown).
    """
    if math.isnan(vix):
        return "bull"  # data gap → don't trigger defensive posture
    if vix > 40.0:
        return "crisis"

    spy_above = spy_above_sma200 == 1.0  # NaN → False, strict
    if vix > 30.0 or not spy_above:
        return "bear"
    if vix > 20.0:
        return "sideways"
    if vix > 15.0:
        return "recovery"
    return "bull"
