"""Portfolio Optimizer using Riskfolio-Lib.

Provides optimal position sizing via Mean-CVaR optimization
with approximate Kelly Criterion weighting.

Pure computation module -- no I/O, no service clients.
Receives OHLCV data directly as dict[str, list[dict]].
"""

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog

from .models import RiskProfile

logger = structlog.get_logger(__name__)

# Lazy import: riskfolio-lib is a heavy optional dependency.
rp: Any = None


def _get_rp() -> Any:
    """Lazy-load riskfolio module."""
    global rp  # noqa: PLW0603
    if rp is None:
        import riskfolio as _rp

        rp = _rp
    return rp


# Minimum bars needed for covariance estimation
_MIN_BARS = 30


class PortfolioOptimizer:
    """Riskfolio-Lib based portfolio optimizer.

    Uses Mean-CVaR optimization with Kelly Criterion approximation
    to determine optimal position weights.
    """

    def optimize(
        self,
        symbols: list[str],
        ohlcv_data: dict[str, list[dict[str, Any]]],
        risk_profile: RiskProfile = RiskProfile.MODERATE,
    ) -> dict[str, Decimal]:
        """Compute optimal portfolio weights for given symbols.

        Args:
            symbols: List of symbols to optimize.
            ohlcv_data: OHLCV data keyed by symbol. Each value is a list of dicts
                        with keys: timestamp, open, high, low, close, volume.
            risk_profile: User risk profile (CONSERVATIVE, MODERATE, AGGRESSIVE).

        Returns:
            Dict of symbol -> optimal weight (Decimal, sums to ~1.0).
            Falls back to equal-weight if optimization fails.
        """
        returns_df = self._build_returns(symbols, ohlcv_data)
        if returns_df is None or returns_df.shape[1] < 2:
            return self._equal_weight(symbols)

        try:
            _rp = _get_rp()
            port = _rp.Portfolio(returns=returns_df)
            port.assets_stats(method_mu="hist", method_cov="ledoit")

            # Kelly-approximate CVaR optimization
            weights = port.optimization(
                model="Classic",
                rm="CVaR",
                obj="MaxRet",
                kelly="approx",
                rf=0.0,
                hist=True,
            )

            if weights is None or weights.empty:
                logger.warning("optimization_empty_weights", fallback="equal_weight")
                return self._equal_weight(symbols)

            # Apply risk profile scaling
            scale = {
                RiskProfile.CONSERVATIVE: 0.5,
                RiskProfile.MODERATE: 0.75,
                RiskProfile.AGGRESSIVE: 1.0,
            }
            factor = scale.get(risk_profile, 0.75)

            result: dict[str, Decimal] = {}
            for sym in symbols:
                if sym in weights.index:
                    w = float(weights.loc[sym, "weights"]) * factor
                    result[sym] = Decimal(str(max(0.0, w))).quantize(Decimal("0.0001"))
                else:
                    result[sym] = Decimal("0")

            logger.info("weights_optimized", symbol_count=len(result), risk_profile=risk_profile)
            return result

        except (ValueError, RuntimeError) as e:
            logger.warning("portfolio_optimization_failed", error=str(e), fallback="equal_weight")
            return self._equal_weight(symbols)

    def _build_returns(
        self,
        symbols: list[str],
        ohlcv_data: dict[str, list[dict[str, Any]]],
    ) -> pd.DataFrame | None:
        """Build daily returns DataFrame from OHLCV data.

        Args:
            symbols: List of symbols.
            ohlcv_data: OHLCV bars keyed by symbol.

        Returns:
            DataFrame of daily returns, or None if insufficient data.
        """
        series: dict[str, pd.Series] = {}

        for sym in symbols:
            bars = ohlcv_data.get(sym, [])
            if len(bars) < _MIN_BARS:
                continue

            closes = [float(b["close"]) for b in bars]
            prices = pd.Series(closes, dtype=np.float64)
            rets = prices.pct_change().dropna()

            if len(rets) >= _MIN_BARS - 1:
                series[sym] = rets.reset_index(drop=True)

        if len(series) < 2:
            return None

        # Align to shortest series
        min_len = min(len(s) for s in series.values())
        aligned = {sym: s.iloc[:min_len] for sym, s in series.items()}

        return pd.DataFrame(aligned)

    def _equal_weight(self, symbols: list[str]) -> dict[str, Decimal]:
        """Fallback to equal-weight allocation.

        Args:
            symbols: List of symbols.

        Returns:
            Dict with equal weights.
        """
        if not symbols:
            return {}

        w = Decimal(str(1.0 / len(symbols))).quantize(Decimal("0.0001"))
        return {sym: w for sym in symbols}
