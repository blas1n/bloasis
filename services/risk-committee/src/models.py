"""Data models for Risk Committee Service."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskDecision(str, Enum):
    """Risk decision types."""

    APPROVE = "approve"
    REJECT = "reject"
    ADJUST = "adjust"


@dataclass
class RiskVote:
    """Individual agent's risk vote."""

    agent: str
    decision: RiskDecision
    risk_score: float
    reasoning: str
    adjustments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommitteeDecision:
    """Final committee decision after voting."""

    approved: bool
    decision: RiskDecision
    risk_score: float
    votes: list[RiskVote]
    adjustments: list[dict[str, Any]]
    warnings: list[str]
    reasoning: str


@dataclass
class PortfolioPosition:
    """Position in the portfolio."""

    symbol: str
    quantity: float
    market_value: float
    sector: str = "Unknown"


@dataclass
class Portfolio:
    """User's portfolio summary."""

    user_id: str
    total_value: float
    positions: list[PortfolioPosition] = field(default_factory=list)


@dataclass
class OrderRequest:
    """Order to be evaluated."""

    user_id: str
    symbol: str
    action: str
    size: float
    price: float
    order_type: str = "market"
