"""
Market Regime Service - Domain Models and Classifier.

Contains the RegimeClassifier that analyzes market conditions using FinGPT,
and SQLAlchemy ORM models for database persistence.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .clients.fingpt_client import FinGPTClient

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
        regime: Classification type (crisis, normal_bear, normal_bull, euphoria,
                high_volatility, low_volatility).
        confidence: Confidence score from 0.0 to 1.0.
        timestamp: ISO 8601 timestamp of classification.
        trigger: What triggered the classification (baseline, fomc, circuit_breaker,
                earnings_season, geopolitical).
    """

    regime: str
    confidence: float
    timestamp: str
    trigger: str


class RegimeClassifier:
    """
    Market regime classifier using FinGPT for AI-powered analysis.

    Analyzes market conditions and classifies into one of the following regimes:
    - crisis: High volatility, risk-off (VIX > 30, major drawdowns)
    - normal_bear: Declining market, moderate volatility
    - normal_bull: Rising market, low-moderate volatility
    - euphoria: Extreme optimism, potential bubble conditions
    - high_volatility: Elevated VIX without clear direction
    - low_volatility: Unusually calm markets, potential complacency
    """

    def __init__(self, fingpt_client: Optional[FinGPTClient] = None) -> None:
        """
        Initialize the RegimeClassifier.

        Args:
            fingpt_client: Optional FinGPT client for AI analysis.
                          If not provided, a new instance will be created.
        """
        self.fingpt = fingpt_client or FinGPTClient()

    async def classify(self) -> RegimeData:
        """
        Classify the current market regime.

        Uses FinGPT to analyze market conditions and determine the regime.
        Falls back to mock data if FinGPT integration is not available.

        Returns:
            RegimeData containing the classification results.

        TODO: Replace mock data with actual FinGPT integration.
        """
        logger.info("Starting market regime classification")

        try:
            # Attempt to use FinGPT for classification
            result = await self.fingpt.analyze()

            # Validate and use FinGPT result
            if result and "regime" in result:
                timestamp = datetime.now(timezone.utc).isoformat()
                regime_data = RegimeData(
                    regime=result.get("regime", "normal_bull"),
                    confidence=float(result.get("confidence", 0.5)),
                    timestamp=timestamp,
                    trigger=result.get("trigger", "baseline"),
                )
                logger.info(
                    f"Classified regime: {regime_data.regime} "
                    f"(confidence: {regime_data.confidence})"
                )
                return regime_data

        except Exception as e:
            logger.warning(f"FinGPT classification failed, using fallback: {e}")

        # Fallback: Return mock data
        # TODO: Replace with actual FinGPT integration
        timestamp = datetime.now(timezone.utc).isoformat()
        return RegimeData(
            regime="normal_bull",
            confidence=0.92,
            timestamp=timestamp,
            trigger="baseline",
        )
