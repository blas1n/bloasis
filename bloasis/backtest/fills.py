"""FillSimulator — model BUY entries with limit_with_fallback semantics.

Two fill modes (config.execution.fill_mode):
  market              : fill at next bar's open + bps slippage
  limit_with_fallback : try a limit at (close - offset_bps); if that price
                        isn't touched within `limit_timeout_bars`, fall back
                        to a market fill at the bar after the timeout.

Long-only in v1. SELL fills (manual or stop-triggered) live in
SimulatedPortfolio.check_stops; this module focuses on entries.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from bloasis.backtest.portfolio import Fill
from bloasis.config import ExecutionConfig

if TYPE_CHECKING:
    import pandas as pd


class FillSimulator:
    """Simulate BUY fills using the configured fill mode."""

    def __init__(self, cfg: ExecutionConfig) -> None:
        self._cfg = cfg

    def simulate_buy(
        self,
        symbol: str,
        quantity: float,
        signal_date: datetime,
        signal_close: float,
        bars: pd.DataFrame,
        sector: str | None = None,
        reason: str = "",
    ) -> Fill | None:
        """Return a Fill for the BUY, or None if it could not execute.

        `signal_date` is the date the signal was generated (the bar whose
        close produced the signal). Filling happens on the *next* trading
        day to avoid look-ahead.

        `bars` is the symbol's full OHLCV panel; we slice forward from
        signal_date to find the fill bar.
        """
        forward = bars.loc[bars.index > signal_date]
        if forward.empty:
            return None

        if self._cfg.fill_mode == "market":
            return self._market_fill(symbol, quantity, forward.iloc[0], sector, reason)

        # limit_with_fallback
        limit_price = signal_close * (1 - self._cfg.limit_offset_bps / 10_000)
        timeout = max(1, self._cfg.limit_timeout_bars)
        candidate_bars = forward.iloc[:timeout]
        for ts, bar in candidate_bars.iterrows():
            low = float(bar["low"])
            if low <= limit_price:
                return Fill(
                    timestamp=_to_dt(ts),
                    symbol=symbol,
                    side="buy",
                    quantity=quantity,
                    price=limit_price,
                    fees=quantity * limit_price * self._cfg.fees_bps / 10_000,
                    slippage_bps=0.0,
                    sector=sector,
                    reason=reason or f"limit fill at {limit_price:.4f}",
                )

        # Fallback: market fill on the bar after the limit window expired.
        fallback_bars = forward.iloc[timeout : timeout + 1]
        if fallback_bars.empty:
            return None
        return self._market_fill(symbol, quantity, fallback_bars.iloc[0], sector, reason)

    # ------------------------------------------------------------------

    def _market_fill(
        self,
        symbol: str,
        quantity: float,
        bar: pd.Series,
        sector: str | None,
        reason: str,
    ) -> Fill:
        open_price = float(bar["open"])
        slippage = open_price * self._cfg.market_slippage_bps / 10_000
        executed = open_price + slippage  # BUY — we pay more
        return Fill(
            timestamp=_to_dt(bar.name),
            symbol=symbol,
            side="buy",
            quantity=quantity,
            price=executed,
            fees=quantity * executed * self._cfg.fees_bps / 10_000,
            slippage_bps=self._cfg.market_slippage_bps,
            sector=sector,
            reason=reason or f"market fill at {executed:.4f}",
        )


def _to_dt(value: object) -> datetime:
    """Coerce a pandas Timestamp / datetime to a tz-aware UTC `datetime`."""
    import pandas as pd

    ts = pd.Timestamp(value)  # type: ignore[arg-type]
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()
