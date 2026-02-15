"""
Market Regime Service - Domain Models and Classifier.

Contains the RegimeClassifier that analyzes market conditions using FinGPT,
and SQLAlchemy ORM models for database persistence.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    from .clients.fingpt_client import FinGPTClient
    from .macro_data import MacroDataFetcher

logger = logging.getLogger(__name__)


# SQLAlchemy ORM Models


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class MarketRegimeRecord(Base):
    """
    SQLAlchemy model for market_data.market_regimes table.

    Stores historical market regime classifications with timestamps.
    """

    __tablename__ = "market_regimes"
    __table_args__ = {"schema": "market_data"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regime: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Domain Models


@dataclass
class RegimeData:
    """
    Data class representing a market regime classification.

    Attributes:
        regime: Classification type (crisis, bear, bull, sideways, recovery).
        confidence: Confidence score from 0.0 to 1.0.
        timestamp: ISO 8601 timestamp of classification.
        trigger: What triggered the classification (baseline, fomc, circuit_breaker,
                earnings_season, geopolitical).
        reasoning: AI-generated explanation of the regime classification.
        risk_level: Risk assessment (low, medium, high).
        indicators: Market indicators used in classification.
    """

    regime: str
    confidence: float
    timestamp: str
    trigger: str
    reasoning: str = ""
    risk_level: str = "medium"
    indicators: Optional[dict] = None


class RegimeClassifier:
    """
    Market regime classifier using FinGPT for AI-powered analysis.

    Analyzes market conditions and classifies into one of the following regimes:
    - crisis: High volatility, risk-off (VIX > 30, major drawdowns)
    - bear: Declining market, moderate volatility
    - bull: Rising market, low-moderate volatility
    - sideways: Range-bound, no clear direction
    - recovery: Transition from crisis/bear to bull
    """

    def __init__(
        self,
        fingpt_client: Optional["FinGPTClient"] = None,
        macro_fetcher: Optional["MacroDataFetcher"] = None,
    ) -> None:
        """
        Initialize the RegimeClassifier.

        Args:
            fingpt_client: FinGPT client for AI analysis.
            macro_fetcher: Macro data fetcher for economic indicators.
        """
        self.fingpt = fingpt_client
        self.macro_fetcher = macro_fetcher

    async def classify(
        self,
        market_data: Optional[dict] = None,
        macro_indicators: Optional[dict] = None,
    ) -> RegimeData:
        """
        Classify the current market regime.

        Uses FinGPT to analyze market conditions and determine the regime.

        Args:
            market_data: Optional pre-fetched market data.
            macro_indicators: Optional pre-fetched macro indicators.

        Returns:
            RegimeData containing the classification results.
        """
        logger.info("Starting market regime classification")

        # Fetch data if not provided
        if market_data is None and self.macro_fetcher:
            market_data = await self.macro_fetcher.get_full_market_data()
        elif market_data is None:
            market_data = {"vix": 20.0, "sp500_1m_change": 0.0}

        if macro_indicators is None and self.macro_fetcher:
            macro_indicators = await self.macro_fetcher.get_indicators()
        elif macro_indicators is None:
            macro_indicators = {"yield_curve_10y_2y": 0.5, "fed_funds_rate": 5.25}

        try:
            if self.fingpt:
                # Use FinGPT for classification
                result = await self.fingpt.classify_regime(
                    market_data=market_data,
                    macro_indicators=macro_indicators,
                )

                timestamp = datetime.now(timezone.utc).isoformat()

                # Determine risk level based on regime and VIX
                vix = market_data.get("vix", 20.0)
                risk_level = self._calculate_risk_level(result.get("regime", "sideways"), vix)

                regime_data = RegimeData(
                    regime=result.get("regime", "sideways"),
                    confidence=float(result.get("confidence", 0.5)),
                    timestamp=timestamp,
                    trigger=result.get("reasoning", "baseline")[:50],
                    reasoning=result.get("reasoning", "AI-generated market analysis"),
                    risk_level=risk_level,
                    indicators={
                        "vix": vix,
                        "sp500_trend": market_data.get("sp500_trend", "neutral"),
                        "yield_curve": str(macro_indicators.get("yield_curve_10y_2y", 0.0)),
                        "credit_spreads": market_data.get("credit_spreads", "normal"),
                    },
                )
                logger.info(
                    f"Classified regime: {regime_data.regime} "
                    f"(confidence: {regime_data.confidence}, risk: {risk_level})"
                )
                return regime_data

        except Exception as e:
            logger.warning(f"FinGPT classification failed, using fallback: {e}")

        # Fallback: Simple rule-based classification
        return self._fallback_classify(market_data, macro_indicators)

    def _calculate_risk_level(self, regime: str, vix: float) -> str:
        """Calculate risk level based on regime and VIX."""
        if regime == "crisis" or vix > 30:
            return "high"
        elif regime == "bear" or vix > 20:
            return "medium"
        else:
            return "low"

    def _fallback_classify(
        self,
        market_data: dict,
        macro_indicators: dict,
    ) -> RegimeData:
        """Fallback rule-based classification when FinGPT is unavailable."""
        vix = market_data.get("vix", 20.0)
        timestamp = datetime.now(timezone.utc).isoformat()

        if vix > 30:
            regime = "crisis"
            confidence = 0.85
            trigger = "high_vix"
            reasoning = f"High volatility detected (VIX: {vix:.1f}), indicating crisis conditions"
        elif vix > 25:
            regime = "bear"
            confidence = 0.75
            trigger = "elevated_vix"
            reasoning = f"Elevated volatility (VIX: {vix:.1f}), bearish market conditions"
        elif vix < 15:
            regime = "bull"
            confidence = 0.80
            trigger = "low_vix"
            reasoning = f"Low volatility (VIX: {vix:.1f}), bullish market conditions"
        else:
            regime = "sideways"
            confidence = 0.65
            trigger = "baseline"
            reasoning = f"Moderate volatility (VIX: {vix:.1f}), range-bound market"

        return RegimeData(
            regime=regime,
            confidence=confidence,
            timestamp=timestamp,
            trigger=trigger,
            reasoning=reasoning,
            risk_level=self._calculate_risk_level(regime, vix),
            indicators={
                "vix": vix,
                "sp500_trend": market_data.get("sp500_trend", "neutral"),
                "yield_curve": str(macro_indicators.get("yield_curve_10y_2y", 0.0)),
                "credit_spreads": market_data.get("credit_spreads", "normal"),
            },
        )
