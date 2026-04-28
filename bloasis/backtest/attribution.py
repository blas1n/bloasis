"""Per-factor PnL attribution from rationales attached to closed trades.

Phase 1: simple sum-of-contributions accounting. For each closed trade
(buy + matching sell), credit the realized PnL to factors in proportion
to their `contribution` in the BUY signal's rationale.

Phase 2/3 will replace this with a proper regression of returns against
factor exposures. The current implementation is a directional sketch —
useful for "did momentum drive our wins?" intuition without being a
rigorous decomposition.
"""

from __future__ import annotations

from collections.abc import Iterable

from bloasis.scoring.composites import COMPOSITE_NAMES
from bloasis.scoring.rationale import Rationale


def attribute_pnl_to_factors(
    closed_trades: Iterable[tuple[float, Rationale | None]],
) -> dict[str, float]:
    """Distribute each closed trade's realized PnL across factors.

    `closed_trades` is an iterable of (realized_pnl, BUY-signal rationale)
    pairs. Trades whose rationale is None contribute to "unattributed".

    For each trade, we normalize the rationale's contributions to sum to
    1.0 (handling the negative-contribution case by using absolute values
    for normalization) and split realized_pnl proportionally.
    """
    out: dict[str, float] = dict.fromkeys(COMPOSITE_NAMES, 0.0)
    out["unattributed"] = 0.0

    for pnl, rationale in closed_trades:
        if rationale is None or not rationale.contributions:
            out["unattributed"] += pnl
            continue
        weights = [abs(c.contribution) for c in rationale.contributions]
        total = sum(weights)
        if total <= 0:
            out["unattributed"] += pnl
            continue
        for c, w in zip(rationale.contributions, weights, strict=True):
            out.setdefault(c.name, 0.0)
            out[c.name] += pnl * (w / total)
    return out
