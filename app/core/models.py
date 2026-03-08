"""Domain models for BLOASIS trading platform.

Pure Pydantic models with no infrastructure dependencies.
These represent the core domain concepts shared across the application.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# --- Enums ---


class RegimeType(StrEnum):
    """Market regime classification."""

    CRISIS = "crisis"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    RECOVERY = "recovery"
    BULL = "bull"


class RiskLevel(StrEnum):
    """Market risk level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class RiskProfile(StrEnum):
    """User risk tolerance level."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class RiskDecision(StrEnum):
    """Risk evaluation outcome."""

    APPROVE = "approve"
    REJECT = "reject"
    ADJUST = "adjust"


class SignalAction(StrEnum):
    """Trading signal action."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class OrderSide(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class BrokerType(StrEnum):
    """Supported broker integrations."""

    ALPACA = "alpaca"
    MOCK = "mock"


class OrderStatus(StrEnum):
    """Order lifecycle status (Outbox + Saga)."""

    PENDING = "pending"  # Recorded in DB, not yet submitted to broker
    SUBMITTED = "submitted"  # Submitted to broker, awaiting fill
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPENSATION_NEEDED = "compensation_needed"  # Broker filled but DB failed


class TradingStatus(StrEnum):
    """Automated trading session status."""

    ACTIVE = "active"
    SOFT_STOPPED = "soft_stopped"
    HARD_STOPPED = "hard_stopped"
    INACTIVE = "inactive"


# --- Market Regime ---


class MarketRegimeIndicators(BaseModel):
    """Market indicators used in regime classification."""

    vix: float = 20.0
    sp500_trend: str = "neutral"
    yield_curve: str = "0.0"
    credit_spreads: str = "normal"


class MarketRegime(BaseModel):
    """Market regime classification result."""

    regime: RegimeType
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: str
    trigger: str = "baseline"
    reasoning: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    indicators: MarketRegimeIndicators = Field(default_factory=MarketRegimeIndicators)


# --- Classification ---


class SectorScore(BaseModel):
    """Individual sector analysis score."""

    sector: str
    score: float = Field(ge=0, le=100)
    rationale: str
    selected: bool = False


class CandidateSymbol(BaseModel):
    """Candidate stock from classification pipeline."""

    symbol: str
    sector: str
    theme: str = ""
    preliminary_score: float = Field(ge=0, le=100, default=50.0)


# --- Factor Scoring ---


class FactorScores(BaseModel):
    """6-factor scores for a single stock."""

    momentum: float = Field(ge=0, le=100, default=50.0)
    value: float = Field(ge=0, le=100, default=50.0)
    quality: float = Field(ge=0, le=100, default=50.0)
    volatility: float = Field(ge=0, le=100, default=50.0)
    liquidity: float = Field(ge=0, le=100, default=50.0)
    sentiment: float = Field(ge=0, le=100, default=50.0)


class StockPick(BaseModel):
    """Stock recommendation with factor analysis."""

    symbol: str
    sector: str
    theme: str = ""
    factor_scores: FactorScores = Field(default_factory=FactorScores)
    final_score: float = Field(ge=0, le=100, default=0.0)
    rank: int = Field(ge=0, default=0)
    rationale: str = ""


# --- Signals ---


class ProfitTier(BaseModel):
    """Single profit-taking tier."""

    level: Decimal
    size_pct: Decimal  # Portion of position to close (0-1)


class TradingSignal(BaseModel):
    """Final trading signal with ATR-based levels."""

    symbol: str
    action: SignalAction
    confidence: float = Field(ge=0, le=1)
    size_recommendation: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")
    rationale: str = ""
    risk_approved: bool = True
    profit_tiers: list[ProfitTier] = Field(default_factory=list)
    trailing_stop_pct: Decimal = Decimal("0")


# --- Risk Evaluation ---


class RiskResult(BaseModel):
    """Result of risk rule evaluation."""

    action: RiskDecision
    risk_score: float = Field(ge=0, le=1, default=0.0)
    reasoning: str = ""
    adjustments: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    adjusted_size: Decimal | None = None


class RiskLimits(BaseModel):
    """Risk limits configuration."""

    max_position_size: Decimal = Decimal("0.10")
    max_single_order: Decimal = Decimal("0.05")
    max_sector_concentration: Decimal = Decimal("0.30")
    vix_high_threshold: Decimal = Decimal("30.0")
    vix_extreme_threshold: Decimal = Decimal("40.0")
    min_daily_volume: int = 100_000

    @classmethod
    def from_snapshot(cls, data: dict[str, Any] | None) -> "RiskLimits | None":
        """Safely deserialize a stored JSONB snapshot with Pydantic validation."""
        if data is None:
            return None
        return cls.model_validate(data)


# --- Portfolio ---


class Position(BaseModel):
    """Portfolio position."""

    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal
    current_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    unrealized_pnl_percent: float = 0.0
    daily_pnl: Decimal = Decimal("0")
    daily_pnl_pct: float = 0.0
    sector: str = "Unknown"
    currency: str = "USD"


class Portfolio(BaseModel):
    """User portfolio summary."""

    user_id: str
    total_value: Decimal = Decimal("0")
    cash_balance: Decimal = Decimal("0")
    invested_value: Decimal = Decimal("0")
    total_return: float = 0.0
    total_return_amount: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    daily_pnl_pct: float = 0.0
    positions: list[Position] = Field(default_factory=list)
    currency: str = "USD"
    timestamp: str = ""


class Trade(BaseModel):
    """Completed trade record."""

    order_id: str | None = None
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    executed_at: str = ""
    ai_reason: str | None = None


# --- Orders ---


class OrderRequest(BaseModel):
    """Order to submit or evaluate."""

    user_id: str
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal = Decimal("0")
    order_type: str = "market"
    sector: str = "Unknown"


class OrderResult(BaseModel):
    """Order execution result."""

    order_id: str
    client_order_id: str = ""
    symbol: str
    side: OrderSide
    qty: Decimal
    status: OrderStatus
    filled_qty: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    submitted_at: str = ""
    filled_at: str | None = None
    error_message: str | None = None


# --- User ---


class UserPreferences(BaseModel):
    """User trading preferences."""

    user_id: str
    risk_profile: RiskProfile = RiskProfile.MODERATE
    max_portfolio_risk: Decimal = Decimal("0.20")
    max_position_size: Decimal = Decimal("0.10")
    preferred_sectors: list[str] = Field(default_factory=list)
    excluded_sectors: list[str] = Field(default_factory=list)
    enable_notifications: bool = True
    trading_enabled: bool = False


class BrokerAccountInfo(BaseModel):
    """Account information returned by broker adapter."""

    equity: Decimal = Decimal("0")
    cash: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")


class BrokerPosition(BaseModel):
    """Position reported by the broker (for sync/reconciliation)."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal


class BrokerStatus(BaseModel):
    """Broker connection status."""

    configured: bool = False
    connected: bool = False
    equity: Decimal = Decimal("0")
    cash: Decimal = Decimal("0")
    error_message: str = ""


# --- Analysis Result (Strategy Pipeline Output) ---


class AnalysisResult(BaseModel):
    """Complete analysis pipeline result."""

    user_id: str
    regime: MarketRegime
    selected_sectors: list[str] = Field(default_factory=list)
    top_themes: list[str] = Field(default_factory=list)
    stock_picks: list[StockPick] = Field(default_factory=list)
    signals: list[TradingSignal] = Field(default_factory=list)
    cached_at: str = ""
    from_cache: bool = False
    error: str | None = None


# --- Trading Session ---


class TradingSession(BaseModel):
    """Automated trading session state."""

    user_id: str
    trading_enabled: bool = False
    status: TradingStatus = TradingStatus.INACTIVE
    last_changed: str = ""
