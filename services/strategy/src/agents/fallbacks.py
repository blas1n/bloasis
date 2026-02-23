"""Rule-based fallback agents for when Claude API is unavailable.

Each fallback mirrors the interface of its Claude-based counterpart but uses
deterministic rules. These ensure the strategy workflow continues in degraded
mode rather than halting entirely.
"""

import logging
import statistics
from decimal import Decimal

from ..workflow.state import MarketContext, RiskAssessment, TechnicalSignal

logger = logging.getLogger(__name__)

# Regime → risk_level mapping
_REGIME_RISK_MAP = {
    "crisis": "extreme",
    "bear": "high",
    "sideways": "medium",
    "recovery": "medium",
    "bull": "low",
}


class RuleBasedMacroStrategist:
    """Fallback macro analysis using regime-to-risk direct mapping."""

    def analyze(
        self,
        stock_picks: list[dict],
        regime: str,
        user_preferences: dict,
    ) -> MarketContext:
        """Generate market context from regime alone.

        Args:
            stock_picks: Stock picks from Stage 3
            regime: Current market regime
            user_preferences: User investment preferences

        Returns:
            MarketContext with conservative confidence (0.6)
        """
        risk_level = _REGIME_RISK_MAP.get(regime, "medium")
        logger.info(f"[Fallback] Macro analysis: regime={regime} → risk_level={risk_level}")

        return MarketContext(
            regime=regime,
            confidence=0.6,
            risk_level=risk_level,
            sector_outlook={},
            macro_indicators={},
        )


class RuleBasedTechnicalAnalyst:
    """Fallback technical analysis using MA crossover."""

    def __init__(self, market_data_client=None):
        self.market_data = market_data_client

    async def analyze(
        self,
        stock_picks: list[dict],
        market_context: MarketContext,
    ) -> list[TechnicalSignal]:
        """Generate signals from MA10/MA20 crossover.

        Args:
            stock_picks: Stock picks from Stage 3
            market_context: Market context from Layer 1

        Returns:
            List of TechnicalSignal for symbols with clear signals
        """
        signals = []

        for pick in stock_picks:
            symbol = pick["symbol"]
            try:
                signal = await self._analyze_symbol(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.warning(f"[Fallback] Technical analysis failed for {symbol}: {e}")

        logger.info(
            f"[Fallback] Technical analysis: {len(signals)} signals "
            f"from {len(stock_picks)} picks"
        )
        return signals

    async def _analyze_symbol(self, symbol: str) -> TechnicalSignal | None:
        """Analyze single symbol using MA crossover.

        Args:
            symbol: Stock ticker symbol

        Returns:
            TechnicalSignal or None if no clear signal
        """
        if not self.market_data:
            return None

        bars = await self.market_data.get_ohlcv(symbol, period="60d", interval="1d")
        if len(bars) < 20:
            return None

        closes = [b["close"] for b in bars]
        current = closes[-1]
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:])

        # MA10 > MA20 and price > MA10 → Long
        if ma10 > ma20 and current > ma10:
            direction = "long"
            raw_strength = min((ma10 - ma20) / ma20 * 10, 0.8)
            strength = max(0.3, raw_strength)
        # MA10 < MA20 and price < MA10 → Short
        elif ma10 < ma20 and current < ma10:
            direction = "short"
            raw_strength = min((ma20 - ma10) / ma20 * 10, 0.8)
            strength = max(0.3, raw_strength)
        else:
            return None

        return TechnicalSignal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            entry_price=Decimal(str(current)),
            indicators={"ma10": ma10, "ma20": ma20},
            rationale=f"Rule-based MA crossover: MA10={ma10:.2f} vs MA20={ma20:.2f}",
        )


class RuleBasedRiskManager:
    """Fallback risk assessment using risk_level rules."""

    def assess(
        self,
        signals: list[TechnicalSignal],
        market_context: MarketContext,
        user_preferences: dict,
    ) -> RiskAssessment:
        """Rule-based risk: reject in extreme, reduce in high/medium.

        Args:
            signals: Technical signals from Layer 2
            market_context: Market context from Layer 1
            user_preferences: User investment preferences

        Returns:
            RiskAssessment with conservative adjustments
        """
        risk_level = market_context.risk_level

        if risk_level == "extreme":
            logger.info("[Fallback] Risk: extreme → rejecting all signals")
            return RiskAssessment(
                approved=False,
                risk_score=1.0,
                position_adjustments={},
                warnings=["Extreme risk - all signals rejected (rule-based fallback)"],
                concentration_risk=1.0,
            )

        multiplier = {
            "high": 0.5,
            "medium": 0.8,
            "low": 1.0,
        }.get(risk_level, 0.8)

        logger.info(f"[Fallback] Risk: {risk_level} → multiplier={multiplier}")

        return RiskAssessment(
            approved=True,
            risk_score=0.5,
            position_adjustments={s.symbol: multiplier for s in signals},
            warnings=[
                f"Using rule-based risk assessment (Claude unavailable), "
                f"multiplier={multiplier}"
            ],
            concentration_risk=0.4,
        )
