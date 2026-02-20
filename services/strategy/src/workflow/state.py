"""Workflow state definitions for LangGraph AI Flow.

This module defines the state management for the 5-Layer AI Flow:
- Layer 1: Macro Strategist (Claude)
- Layer 2: Technical Analyst (Claude)
- Layer 3: Risk Manager (Claude)
- Layer 4: Signal Generator
- Layer 5: Event Publisher
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TypedDict


class WorkflowPhase(StrEnum):
    """Workflow progress phase tracking."""

    INIT = "init"
    MACRO_ANALYSIS = "macro_analysis"
    TECHNICAL_ANALYSIS = "technical_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    SIGNAL_GENERATION = "signal_generation"
    EVENT_PUBLISHING = "event_publishing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class MarketContext:
    """Macro economic context from Layer 1 (Macro Strategist)."""

    regime: str
    confidence: float
    risk_level: str  # "low", "medium", "high", "extreme"
    sector_outlook: dict[str, float]
    macro_indicators: dict[str, any]


@dataclass
class TechnicalSignal:
    """Technical analysis signal from Layer 2 (Technical Analyst)."""

    symbol: str
    direction: str  # "long", "short", "neutral"
    strength: float  # 0-1
    entry_price: Decimal
    indicators: dict[str, any]
    rationale: str


@dataclass
class RiskAssessment:
    """Risk assessment result from Layer 3 (Risk Manager)."""

    approved: bool
    risk_score: float  # 0-1
    position_adjustments: dict[str, float]  # symbol -> size multiplier
    warnings: list[str]
    concentration_risk: float


@dataclass
class TradingSignal:
    """Final trading signal from Layer 4 (Signal Generator)."""

    symbol: str
    action: str  # "buy", "sell", "hold"
    confidence: float
    size_recommendation: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    rationale: str
    risk_approved: bool


class AnalysisState(TypedDict):
    """LangGraph workflow state.

    This state is passed through all workflow nodes and tracks
    the complete analysis pipeline state.
    """

    # Input
    user_id: str
    stock_picks: list[dict]  # From Stage 3 (Factor Scoring)
    preferences: dict

    # Phase tracking
    phase: WorkflowPhase

    # Layer outputs
    market_context: MarketContext | None
    technical_signals: list[TechnicalSignal]
    risk_assessment: RiskAssessment | None
    trading_signals: list[TradingSignal]

    # Metadata
    analysis_id: str
    started_at: str
    errors: list[str]
