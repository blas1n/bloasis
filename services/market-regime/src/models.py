"""
Market Regime Service - Domain Models and Classifier.

Contains the RegimeClassifier that analyzes market conditions using Claude AI,
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

from .prompts import format_classification_prompt, get_model_parameters, get_system_prompt

if TYPE_CHECKING:
    from shared.ai_clients import ClaudeClient

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
    Market regime classifier using Claude AI for analysis.

    Analyzes market conditions and classifies into one of the following regimes:
    - crisis: High volatility, risk-off (VIX > 30, major drawdowns)
    - bear: Declining market, moderate volatility
    - bull: Rising market, low-moderate volatility
    - sideways: Range-bound, no clear direction
    - recovery: Transition from crisis/bear to bull
    """

    def __init__(
        self,
        analyst: "ClaudeClient",
        macro_fetcher: Optional["MacroDataFetcher"] = None,
        claude_model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        """
        Initialize the RegimeClassifier.

        Args:
            analyst: Claude client for AI analysis (required).
            macro_fetcher: Macro data fetcher for economic indicators.
            claude_model: Claude model ID to use for analysis.
        """
        self.analyst = analyst
        self.macro_fetcher = macro_fetcher
        self.claude_model = claude_model

    async def classify(
        self,
        market_data: Optional[dict] = None,
        macro_indicators: Optional[dict] = None,
        trigger: str = "baseline",
    ) -> RegimeData:
        """
        Classify the current market regime using Claude AI.

        Args:
            market_data: Optional pre-fetched market data.
            macro_indicators: Optional pre-fetched macro indicators.
            trigger: What caused this classification to run.
                Allowed values: "baseline" (scheduled), "fomc",
                "circuit_breaker", "earnings_season", "geopolitical".

        Returns:
            RegimeData containing the classification results.

        Raises:
            Exception: If Claude API call fails.
        """
        logger.info(f"Starting market regime classification (trigger={trigger})")

        # Fetch data if not provided
        if market_data is None and self.macro_fetcher:
            market_data = await self.macro_fetcher.get_full_market_data()
        elif market_data is None:
            market_data = {"vix": 20.0, "sp500_1m_change": 0.0}

        if macro_indicators is None and self.macro_fetcher:
            macro_indicators = await self.macro_fetcher.get_indicators()
        elif macro_indicators is None:
            macro_indicators = {"yield_curve_10y_2y": 0.5, "fed_funds_rate": 5.25}

        prompt = format_classification_prompt(market_data, macro_indicators)
        system_prompt = get_system_prompt()
        params = get_model_parameters()

        raw_result = await self.analyst.analyze(
            prompt=prompt,
            model=self.claude_model,
            system_prompt=system_prompt,
            response_format="json",
            max_tokens=params.get("max_new_tokens", 500),
        )

        result = self._parse_regime_response(raw_result)

        timestamp = datetime.now(timezone.utc).isoformat()

        # Determine risk level based on regime and VIX
        vix = market_data.get("vix", 20.0)
        risk_level = self._calculate_risk_level(result.get("regime", "sideways"), vix)

        regime_data = RegimeData(
            regime=result.get("regime", "sideways"),
            confidence=float(result.get("confidence", 0.5)),
            timestamp=timestamp,
            trigger=trigger,
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

    def _parse_regime_response(self, data: dict) -> dict:
        """
        Validate and normalize Claude's regime classification response.

        Args:
            data: Parsed JSON from Claude API

        Returns:
            Validated regime response dict
        """
        try:
            regime = data.get("regime", "sideways")
            if regime not in ["crisis", "bear", "bull", "sideways", "recovery"]:
                regime = "sideways"

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            return {
                "regime": regime,
                "confidence": confidence,
                "reasoning": data.get("reasoning", "Unable to determine"),
                "indicators": data.get("key_indicators", []),
            }

        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse Claude response: {e}")
            return {
                "regime": "sideways",
                "confidence": 0.5,
                "reasoning": "Parse error",
                "indicators": [],
            }

    def _calculate_risk_level(self, regime: str, vix: float) -> str:
        """Calculate risk level based on regime and VIX."""
        if regime == "crisis" or vix > 30:
            return "high"
        elif regime == "bear" or vix > 20:
            return "medium"
        else:
            return "low"
