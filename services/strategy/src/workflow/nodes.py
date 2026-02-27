"""Workflow nodes for LangGraph AI Flow.

Each node represents a step in the 5-Layer AI Flow:
- Layer 1: Macro Analysis
- Layer 2: Technical Analysis
- Layer 3: Risk Assessment
- Layer 4: Signal Generation
- Layer 5: Event Publishing
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from shared.ai_clients import ClaudeClient
from shared.utils.event_publisher import EventPriority, EventPublisher
from shared.utils.redpanda_client import RedpandaClient

from ..agents.fallbacks import (
    RuleBasedMacroStrategist,
    RuleBasedRiskManager,
    RuleBasedTechnicalAnalyst,
)
from ..agents.macro_strategist import MacroStrategist
from ..agents.risk_manager import RiskManager
from ..agents.signal_generator import SignalGenerator
from ..agents.technical_analyst import TechnicalAnalyst
from ..clients.market_data_client import MarketDataClient
from ..config import config
from ..portfolio_optimizer import PortfolioOptimizer
from .state import AnalysisState, WorkflowPhase

logger = logging.getLogger(__name__)

# Shared Claude client — one connection pool for the entire workflow
_claude_client: ClaudeClient | None = None

# Agent instances (singleton pattern for workflow)
_macro_strategist: MacroStrategist | None = None
_technical_analyst: TechnicalAnalyst | None = None
_risk_manager: RiskManager | None = None
_signal_generator: SignalGenerator | None = None
_portfolio_optimizer: PortfolioOptimizer | None = None
_event_publisher: EventPublisher | None = None


def get_claude_client() -> ClaudeClient:
    """Get or create the shared ClaudeClient instance."""
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient(api_key=config.anthropic_api_key)
    return _claude_client


def get_macro_strategist() -> MacroStrategist:
    """Get or create MacroStrategist instance."""
    global _macro_strategist
    if _macro_strategist is None:
        _macro_strategist = MacroStrategist(analyst=get_claude_client())
    return _macro_strategist


def get_technical_analyst() -> TechnicalAnalyst:
    """Get or create TechnicalAnalyst instance."""
    global _technical_analyst
    if _technical_analyst is None:
        _technical_analyst = TechnicalAnalyst(
            claude_client=get_claude_client(),
            market_data_client=MarketDataClient(),
        )
    return _technical_analyst


def get_risk_manager() -> RiskManager:
    """Get or create RiskManager instance."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager(claude_client=get_claude_client())
    return _risk_manager


def get_signal_generator() -> SignalGenerator:
    """Get or create SignalGenerator instance."""
    global _signal_generator
    if _signal_generator is None:
        _signal_generator = SignalGenerator()
    return _signal_generator


def get_portfolio_optimizer() -> PortfolioOptimizer:
    """Get or create PortfolioOptimizer instance."""
    global _portfolio_optimizer
    if _portfolio_optimizer is None:
        _portfolio_optimizer = PortfolioOptimizer()
    return _portfolio_optimizer


async def get_event_publisher() -> EventPublisher:
    """Get or create EventPublisher instance."""
    global _event_publisher
    if _event_publisher is None:
        redpanda = RedpandaClient(brokers=config.redpanda_brokers)
        await redpanda.start()
        _event_publisher = EventPublisher(redpanda)
    return _event_publisher


async def initialize_analysis(state: AnalysisState) -> dict:
    """Initialize workflow and generate analysis ID.

    Args:
        state: Current workflow state

    Returns:
        Updated state with analysis_id and started_at
    """
    analysis_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()

    logger.info(f"Initializing analysis: {analysis_id}")

    return {
        "analysis_id": analysis_id,
        "started_at": started_at,
        "phase": WorkflowPhase.MACRO_ANALYSIS,
        "errors": [],
    }


async def macro_analysis_node(state: AnalysisState) -> dict:
    """Layer 1: Macro economic analysis using Claude.

    Args:
        state: Current workflow state

    Returns:
        Updated state with market_context
    """
    analysis_id = state["analysis_id"]
    logger.info(f"[{analysis_id}] Starting macro analysis")

    try:
        strategist = get_macro_strategist()

        market_context = await strategist.analyze(
            stock_picks=state["stock_picks"],
            regime=state.get("preferences", {}).get("regime", "normal_bull"),
            user_preferences=state["preferences"],
        )

        logger.info(
            f"[{analysis_id}] Macro analysis complete: risk_level={market_context.risk_level}"
        )

        return {
            "market_context": market_context,
            "phase": WorkflowPhase.TECHNICAL_ANALYSIS,
        }

    except Exception as e:
        logger.warning(f"[{analysis_id}] Macro analysis failed, using fallback: {e}", exc_info=True)

        fallback = RuleBasedMacroStrategist()
        market_context = fallback.analyze(
            stock_picks=state["stock_picks"],
            regime=state.get("preferences", {}).get("regime", "normal_bull"),
            user_preferences=state["preferences"],
        )

        warnings = state.get("warnings", [])
        return {
            "market_context": market_context,
            "phase": WorkflowPhase.TECHNICAL_ANALYSIS,
            "warnings": warnings + [f"Macro analysis fallback used: {str(e)}"],
        }


async def technical_analysis_node(state: AnalysisState) -> dict:
    """Layer 2: Technical analysis using Claude.

    Args:
        state: Current workflow state

    Returns:
        Updated state with technical_signals
    """
    analysis_id = state["analysis_id"]
    logger.info(f"[{analysis_id}] Starting technical analysis")

    try:
        analyst = get_technical_analyst()

        signals = await analyst.analyze(
            stock_picks=state["stock_picks"],
            market_context=state["market_context"],
        )

        # Cache OHLCV data for signal generation (ATR-based SL/TP)
        ohlcv_data = {}
        market_data = MarketDataClient()
        for pick in state["stock_picks"]:
            symbol = pick["symbol"]
            try:
                bars = await market_data.get_ohlcv(symbol, period="3mo")
                ohlcv_data[symbol] = bars
            except Exception:
                ohlcv_data[symbol] = []

        logger.info(f"[{analysis_id}] Technical analysis complete: {len(signals)} signals")

        return {
            "technical_signals": signals,
            "ohlcv_data": ohlcv_data,
            "phase": WorkflowPhase.RISK_ASSESSMENT,
        }

    except Exception as e:
        logger.warning(
            f"[{analysis_id}] Technical analysis failed, using fallback: {e}",
            exc_info=True,
        )

        fallback = RuleBasedTechnicalAnalyst(market_data_client=MarketDataClient())
        signals = await fallback.analyze(
            stock_picks=state["stock_picks"],
            market_context=state["market_context"],
        )

        warnings = state.get("warnings", [])
        return {
            "technical_signals": signals,
            "phase": WorkflowPhase.RISK_ASSESSMENT,
            "warnings": warnings + [f"Technical analysis fallback used: {str(e)}"],
        }


async def risk_assessment_node(state: AnalysisState) -> dict:
    """Layer 3: Risk assessment using Claude.

    Args:
        state: Current workflow state

    Returns:
        Updated state with risk_assessment
    """
    analysis_id = state["analysis_id"]
    logger.info(f"[{analysis_id}] Starting risk assessment")

    try:
        manager = get_risk_manager()

        assessment = await manager.assess(
            signals=state["technical_signals"],
            market_context=state["market_context"],
            user_preferences=state["preferences"],
        )

        logger.info(
            f"[{analysis_id}] Risk assessment complete: "
            f"approved={assessment.approved}, risk_score={assessment.risk_score:.2f}"
        )

        return {
            "risk_assessment": assessment,
            "phase": WorkflowPhase.SIGNAL_GENERATION,
        }

    except Exception as e:
        logger.warning(
            f"[{analysis_id}] Risk assessment failed, using fallback: {e}",
            exc_info=True,
        )

        fallback = RuleBasedRiskManager()
        assessment = fallback.assess(
            signals=state["technical_signals"],
            market_context=state["market_context"],
            user_preferences=state["preferences"],
        )

        warnings = state.get("warnings", [])
        return {
            "risk_assessment": assessment,
            "phase": WorkflowPhase.SIGNAL_GENERATION,
            "warnings": warnings + [f"Risk assessment fallback used: {str(e)}"],
        }


async def signal_generation_node(state: AnalysisState) -> dict:
    """Layer 4: Trading signal generation.

    Args:
        state: Current workflow state

    Returns:
        Updated state with trading_signals
    """
    analysis_id = state["analysis_id"]
    logger.info(f"[{analysis_id}] Generating trading signals")

    try:
        generator = get_signal_generator()
        ohlcv_data = state.get("ohlcv_data", {})

        trading_signals = generator.generate(
            technical_signals=state["technical_signals"],
            risk_assessment=state["risk_assessment"],
            market_context=state["market_context"],
            user_preferences=state["preferences"],
            ohlcv_data=ohlcv_data,
        )

        # Apply portfolio optimization to adjust position sizes
        if len(trading_signals) >= 2 and ohlcv_data:
            try:
                optimizer = get_portfolio_optimizer()
                symbols = [s.symbol for s in trading_signals]
                risk_profile = state["preferences"].get("risk_profile", "MODERATE")
                opt_weights = optimizer.optimize(symbols, ohlcv_data, risk_profile)

                for signal in trading_signals:
                    if signal.symbol in opt_weights:
                        opt_w = opt_weights[signal.symbol]
                        # Blend: 50% signal-based + 50% optimizer-based
                        blended = signal.size_recommendation * Decimal("0.5") + opt_w * Decimal(
                            "0.5"
                        )
                        signal.size_recommendation = blended.quantize(
                            Decimal("0.0001"),
                        )
            except Exception as e:
                logger.warning(f"[{analysis_id}] Portfolio optimization skipped: {e}")

        logger.info(f"[{analysis_id}] Signal generation complete: {len(trading_signals)} signals")

        return {
            "trading_signals": trading_signals,
            "phase": WorkflowPhase.EVENT_PUBLISHING,
        }

    except Exception as e:
        logger.error(
            f"[{analysis_id}] Signal generation failed: {e}",
            exc_info=True,
        )
        errors = state.get("errors", [])
        return {
            "errors": errors + [f"Signal generation error: {str(e)}"],
            "phase": WorkflowPhase.ERROR,
        }


async def event_publishing_node(state: AnalysisState) -> dict:
    """Layer 5: Event publishing to Redpanda.

    Args:
        state: Current workflow state

    Returns:
        Updated state with phase=COMPLETE
    """
    analysis_id = state["analysis_id"]
    user_id = state["user_id"]
    logger.info(f"[{analysis_id}] Publishing events")

    try:
        publisher = await get_event_publisher()

        # Publish each trading signal
        for signal in state["trading_signals"]:
            await publisher.publish_strategy_signal(
                strategy_id=analysis_id,
                signal_type="ai_generated",
                symbol=signal.symbol,
                action=signal.action,
                confidence=signal.confidence,
                priority=EventPriority.HIGH,
                parameters={
                    "user_id": user_id,
                    "entry_price": str(signal.entry_price),
                    "stop_loss": str(signal.stop_loss),
                    "take_profit": str(signal.take_profit),
                    "size_recommendation": str(signal.size_recommendation),
                    "rationale": signal.rationale,
                    "profit_tiers": [
                        {"level": str(t.level), "size_pct": str(t.size_pct)}
                        for t in signal.profit_tiers
                    ],
                    "trailing_stop_pct": str(signal.trailing_stop_pct),
                },
            )

        # Publish analysis complete event
        signal_count = len(state["trading_signals"])
        await publisher.publish_market_alert(
            alert_type="analysis_complete",
            severity="info",
            message=f"AI analysis complete for user {user_id}: {signal_count} signals",
            priority=EventPriority.MEDIUM,
            indicators={
                "analysis_id": analysis_id,
                "user_id": user_id,
                "signal_count": str(signal_count),
                "regime": state["market_context"].regime,
                "risk_level": state["market_context"].risk_level,
            },
        )

        logger.info(f"[{analysis_id}] Event publishing complete")

        return {
            "phase": WorkflowPhase.COMPLETE,
        }

    except Exception as e:
        logger.error(f"[{analysis_id}] Event publishing failed: {e}", exc_info=True)
        errors = state.get("errors", [])
        return {
            "errors": errors + [f"Event publishing error: {str(e)}"],
            "phase": WorkflowPhase.ERROR,
        }
