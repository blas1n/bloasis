"""Pydantic models for Strategy Service.

These models are service-specific and used for internal business logic.
Inter-service communication uses Proto messages only (gRPC).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskProfile(StrEnum):
    """Risk profile enumeration."""

    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class FactorScores(BaseModel):
    """Individual factor scores for a stock."""

    momentum: float = Field(ge=0, le=100, description="Momentum score (0-100)")
    value: float = Field(ge=0, le=100, description="Value score (0-100)")
    quality: float = Field(ge=0, le=100, description="Quality score (0-100)")
    volatility: float = Field(ge=0, le=100, description="Volatility score (0-100, inverse)")
    liquidity: float = Field(ge=0, le=100, description="Liquidity score (0-100)")
    sentiment: float = Field(ge=0, le=100, description="Sentiment score (0-100)")


class StockPick(BaseModel):
    """Individual stock recommendation with factor analysis."""

    symbol: str = Field(description="Stock symbol")
    sector: str = Field(description="Sector classification")
    theme: str = Field(description="Primary investment theme")
    factor_scores: FactorScores = Field(description="Factor scores breakdown")
    final_score: float = Field(ge=0, le=100, description="Final weighted score")
    rank: int = Field(ge=0, description="Ranking position (1 = highest, 0 = unranked)")
    rationale: str = Field(description="Investment rationale")


class UserPreferences(BaseModel):
    """User investment preferences."""

    user_id: str = Field(description="User ID")
    risk_profile: RiskProfile = Field(description="Risk tolerance level")
    preferred_sectors: list[str] = Field(
        default_factory=list, description="Preferred sectors (boost these)"
    )
    excluded_sectors: list[str] = Field(
        default_factory=list, description="Excluded sectors (filter out)"
    )
    max_single_position: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Maximum single position size (0.0-1.0)"
    )


class CandidateSymbol(BaseModel):
    """Candidate symbol from Classification Service."""

    symbol: str = Field(description="Stock symbol")
    sector: str = Field(description="Sector classification")
    theme: str = Field(description="Primary investment theme")
    preliminary_score: float = Field(ge=0, le=100, description="Preliminary score from Stage 1+2")


class OHLCVBar(BaseModel):
    """Single OHLCV bar/candle."""

    timestamp: str = Field(description="ISO 8601 timestamp")
    open: float = Field(description="Open price")
    high: float = Field(description="High price")
    low: float = Field(description="Low price")
    close: float = Field(description="Close price")
    volume: int = Field(description="Trading volume")
    adj_close: float | None = Field(default=None, description="Adjusted close price")
