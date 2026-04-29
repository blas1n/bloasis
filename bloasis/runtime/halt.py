"""Live-trading halt-condition gate.

Refuses `bloasis trade live` when recent realized PnL has dropped beyond a
configured threshold. Implemented as a rolling-window read of the `trades`
table for live entries (`run_id IS NULL`).

Limitations (L009 in `docs/limitations.md`):
  - **Realized only.** Open positions' unrealized losses are not counted.
    The intent is to halt after a string of bad exits, not to react to
    intraday mark-to-market noise.
  - **Per-user (always user_id=0 in v1).** Cross-user halts aren't a thing.
  - **No timezone normalization.** `timestamp` is compared in UTC; the
    rest of the pipeline writes UTC, so this matches.

Use `evaluate_halt(engine, cfg, initial_capital, now)` from the CLI's live
gate. Returns a `HaltDecision` with a reason string suitable for printing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from bloasis.storage import trades

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from bloasis.config import RiskConfig


@dataclass(frozen=True, slots=True)
class HaltDecision:
    """Outcome of the halt check.

    `should_halt=True` means trade live MUST refuse. `realized_pnl` is the
    sum of `realized_pnl` from live trades over the lookback window
    (negative when there are losses); `threshold` is the absolute dollar
    floor below which we halt.
    """

    should_halt: bool
    realized_pnl: float
    threshold: float
    lookback_days: int
    reason: str = ""


def evaluate_halt(
    engine: Engine,
    risk_cfg: RiskConfig,
    *,
    initial_capital: float,
    now: datetime,
    user_id: int = 0,
) -> HaltDecision:
    """Compute realized PnL from live trades and compare to the halt floor.

    `halt_drawdown_pct == 0` disables the check (returns should_halt=False).
    """
    if risk_cfg.halt_drawdown_pct <= 0:
        return HaltDecision(
            should_halt=False,
            realized_pnl=0.0,
            threshold=0.0,
            lookback_days=risk_cfg.halt_drawdown_lookback_days,
            reason="halt disabled (halt_drawdown_pct=0)",
        )

    cutoff = now - timedelta(days=risk_cfg.halt_drawdown_lookback_days)
    threshold = -abs(risk_cfg.halt_drawdown_pct) * initial_capital

    with engine.connect() as conn:
        rows = conn.execute(
            select(trades.c.realized_pnl).where(
                trades.c.user_id == user_id,
                trades.c.run_id.is_(None),
                trades.c.timestamp >= cutoff,
                trades.c.realized_pnl.is_not(None),
            )
        ).fetchall()

    realized = sum(float(r[0]) for r in rows if r[0] is not None)
    should_halt = realized < threshold
    if should_halt:
        reason = (
            f"realized PnL ${realized:,.2f} over last "
            f"{risk_cfg.halt_drawdown_lookback_days}d below halt floor "
            f"${threshold:,.2f} ({risk_cfg.halt_drawdown_pct:.0%} of "
            f"${initial_capital:,.2f} initial)"
        )
    else:
        reason = (
            f"realized PnL ${realized:,.2f} over last "
            f"{risk_cfg.halt_drawdown_lookback_days}d above halt floor "
            f"${threshold:,.2f}"
        )
    return HaltDecision(
        should_halt=should_halt,
        realized_pnl=realized,
        threshold=threshold,
        lookback_days=risk_cfg.halt_drawdown_lookback_days,
        reason=reason,
    )


__all__ = ["HaltDecision", "evaluate_halt"]
