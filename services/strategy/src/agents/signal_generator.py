"""Layer 4: Signal Generator.

The Signal Generator creates final trading signals by combining technical signals
with risk adjustments and calculating ATR-based position sizes, stop-loss,
and take-profit levels.
"""

import logging
import math
from decimal import Decimal

from ..technical_indicators import calculate_indicators
from ..workflow.state import MarketContext, RiskAssessment, TechnicalSignal, TradingSignal

logger = logging.getLogger(__name__)

# Risk multiplier by market risk level — scales ATR distances
_RISK_MULT = {
    "extreme": Decimal("0.5"),
    "high": Decimal("0.75"),
    "medium": Decimal("1.0"),
    "low": Decimal("1.25"),
}

# Target annualized volatility by risk profile (for position sizing)
_TARGET_VOL = {
    "CONSERVATIVE": 0.10,
    "MODERATE": 0.15,
    "AGGRESSIVE": 0.25,
}

# Max position sizes by risk profile (hard cap)
_MAX_SIZE = {
    "CONSERVATIVE": Decimal("0.05"),
    "MODERATE": Decimal("0.10"),
    "AGGRESSIVE": Decimal("0.15"),
}


class SignalGenerator:
    """Layer 4: Final trading signal generation.

    Combines technical signals with risk adjustments to produce
    actionable trading signals with ATR-based levels and
    volatility-adjusted position sizing.
    """

    def generate(
        self,
        technical_signals: list[TechnicalSignal],
        risk_assessment: RiskAssessment,
        market_context: MarketContext,
        user_preferences: dict,
        ohlcv_data: dict | None = None,
    ) -> list[TradingSignal]:
        """Generate final trading signals.

        Args:
            technical_signals: Signals from Layer 2 (Technical Analyst)
            risk_assessment: Assessment from Layer 3 (Risk Manager)
            market_context: Context from Layer 1 (Macro Strategist)
            user_preferences: User investment preferences
            ohlcv_data: OHLCV data keyed by symbol (for ATR calculation)

        Returns:
            List of final trading signals
        """
        logger.info(
            f"Generating trading signals from "
            f"{len(technical_signals)} technical signals"
        )
        ohlcv_data = ohlcv_data or {}
        risk_profile = user_preferences.get("risk_profile", "MODERATE")

        trading_signals = []

        for tech_signal in technical_signals:
            # Compute ATR from OHLCV data
            atr = self._get_atr(tech_signal.symbol, ohlcv_data)

            # Calculate volatility-adjusted position size
            base_size = self._calculate_base_size(
                tech_signal.strength,
                risk_profile,
                atr,
                float(tech_signal.entry_price),
            )

            # Apply risk adjustment
            multiplier = risk_assessment.position_adjustments.get(
                tech_signal.symbol, 1.0,
            )
            final_size = base_size * Decimal(str(multiplier))

            # Calculate ATR-based stop-loss and take-profit
            stop_loss, take_profit = self._calculate_levels(
                tech_signal, market_context, atr,
            )

            trading_signal = TradingSignal(
                symbol=tech_signal.symbol,
                action=self._signal_to_action(tech_signal.direction),
                confidence=tech_signal.strength,
                size_recommendation=final_size,
                entry_price=tech_signal.entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                rationale=tech_signal.rationale,
                risk_approved=risk_assessment.approved,
            )

            trading_signals.append(trading_signal)

        logger.info(
            f"Generated {len(trading_signals)} trading signals "
            f"(risk_approved={risk_assessment.approved})"
        )
        return trading_signals

    def _get_atr(self, symbol: str, ohlcv_data: dict) -> float:
        """Get ATR for a symbol from OHLCV data.

        Args:
            symbol: Stock ticker symbol.
            ohlcv_data: OHLCV data keyed by symbol.

        Returns:
            ATR value, or 0.0 if unavailable.
        """
        bars = ohlcv_data.get(symbol, [])
        if len(bars) < 26:
            return 0.0

        indicators = calculate_indicators(symbol, bars)
        if indicators is None:
            return 0.0

        return indicators.atr_14

    def _calculate_base_size(
        self,
        strength: float,
        risk_profile: str,
        atr: float,
        entry_price: float,
    ) -> Decimal:
        """Calculate volatility-adjusted position size.

        Uses inverse-volatility weighting: base_size * (target_vol / actual_vol).
        Capped at max_size per risk profile.

        Args:
            strength: Signal strength (0-1).
            risk_profile: User risk profile.
            atr: Current ATR value.
            entry_price: Current entry price.

        Returns:
            Position size as decimal (0.0-1.0 of portfolio).
        """
        max_size = _MAX_SIZE.get(risk_profile, Decimal("0.10"))
        target_vol = _TARGET_VOL.get(risk_profile, 0.15)

        # Base size from signal strength
        base = Decimal(str(strength)) * max_size

        # Volatility adjustment (inverse-volatility weighting)
        if atr > 0 and entry_price > 0:
            # ATR as percentage of price → annualized
            daily_vol = atr / entry_price
            annual_vol = daily_vol * math.sqrt(252)

            if annual_vol > 0:
                vol_ratio = Decimal(str(target_vol / annual_vol))
                # Clamp vol_ratio to [0.3, 2.0] to avoid extreme adjustments
                vol_ratio = max(Decimal("0.3"), min(Decimal("2.0"), vol_ratio))
                base = base * vol_ratio

        # Enforce hard cap
        base = min(base, max_size)

        return base.quantize(Decimal("0.0001"))

    def _calculate_levels(
        self,
        signal: TechnicalSignal,
        market_context: MarketContext,
        atr: float,
    ) -> tuple[Decimal, Decimal]:
        """Calculate ATR-based stop-loss and take-profit.

        SL = entry ± (2 × ATR × risk_mult)
        TP = entry ± (3 × ATR × risk_mult)

        Falls back to fixed percentage if ATR is unavailable.

        Args:
            signal: Technical signal.
            market_context: Market context.
            atr: ATR value.

        Returns:
            Tuple of (stop_loss, take_profit).
        """
        entry = signal.entry_price
        risk_mult = _RISK_MULT.get(
            market_context.risk_level, Decimal("1.0"),
        )

        if atr > 0:
            atr_d = Decimal(str(atr))
            sl_distance = Decimal("2") * atr_d * risk_mult
            tp_distance = Decimal("3") * atr_d * risk_mult

            if signal.direction == "long":
                stop_loss = entry - sl_distance
                take_profit = entry + tp_distance
            else:
                stop_loss = entry + sl_distance
                take_profit = entry - tp_distance
        else:
            # Fallback: fixed percentage based on risk level
            sl_pct, tp_pct = self._fallback_pct(
                signal.direction, market_context.risk_level,
            )
            stop_loss = entry * sl_pct
            take_profit = entry * tp_pct

        return stop_loss, take_profit

    def _fallback_pct(
        self, direction: str, risk_level: str,
    ) -> tuple[Decimal, Decimal]:
        """Get fallback SL/TP percentages when ATR is unavailable.

        Args:
            direction: Signal direction.
            risk_level: Market risk level.

        Returns:
            Tuple of (sl_pct, tp_pct) as multipliers on entry price.
        """
        if risk_level == "extreme":
            sl, tp = Decimal("0.005"), Decimal("0.02")
        elif risk_level == "high":
            sl, tp = Decimal("0.01"), Decimal("0.03")
        else:
            sl, tp = Decimal("0.02"), Decimal("0.05")

        if direction == "long":
            return (Decimal("1") - sl, Decimal("1") + tp)
        else:
            return (Decimal("1") + sl, Decimal("1") - tp)

    def _signal_to_action(self, direction: str) -> str:
        """Convert signal direction to trading action.

        Args:
            direction: Signal direction (long/short/neutral)

        Returns:
            Trading action (buy/sell/hold)
        """
        action_map = {
            "long": "buy",
            "short": "sell",
            "neutral": "hold",
        }

        return action_map.get(direction, "hold")
