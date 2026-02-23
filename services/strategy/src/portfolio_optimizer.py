"""Portfolio Optimizer using Riskfolio-Lib.

Provides optimal position sizing via Mean-CVaR optimization
with approximate Kelly Criterion weighting.
"""

import logging
from decimal import Decimal

import numpy as np
import pandas as pd
import riskfolio as rp

logger = logging.getLogger(__name__)

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
        ohlcv_data: dict[str, list[dict]],
        risk_profile: str = "MODERATE",
    ) -> dict[str, Decimal]:
        """Compute optimal portfolio weights for given symbols.

        Args:
            symbols: List of symbols to optimize.
            ohlcv_data: OHLCV data keyed by symbol.
            risk_profile: User risk profile.

        Returns:
            Dict of symbol -> optimal weight (Decimal, sums to ~1.0).
            Falls back to equal-weight if optimization fails.
        """
        # Build returns DataFrame
        returns_df = self._build_returns(symbols, ohlcv_data)
        if returns_df is None or returns_df.shape[1] < 2:
            return self._equal_weight(symbols)

        try:
            port = rp.Portfolio(returns=returns_df)
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
                logger.warning("Optimization returned empty weights, using equal-weight")
                return self._equal_weight(symbols)

            # Apply risk profile scaling
            scale = {"CONSERVATIVE": 0.5, "MODERATE": 0.75, "AGGRESSIVE": 1.0}
            factor = scale.get(risk_profile, 0.75)

            result: dict[str, Decimal] = {}
            for sym in symbols:
                if sym in weights.index:
                    w = float(weights.loc[sym, "weights"]) * factor
                    result[sym] = Decimal(str(max(0.0, w))).quantize(
                        Decimal("0.0001"),
                    )
                else:
                    result[sym] = Decimal("0")

            logger.info(
                f"Optimized weights for {len(result)} symbols "
                f"(profile={risk_profile})"
            )
            return result

        except Exception as e:
            logger.warning(f"Portfolio optimization failed, using equal-weight: {e}")
            return self._equal_weight(symbols)

    def _build_returns(
        self,
        symbols: list[str],
        ohlcv_data: dict[str, list[dict]],
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

            closes = [b["close"] for b in bars]
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
