"""LangGraph workflow definition for 5-Layer AI Flow.

This module defines the complete workflow graph with conditional branching:
- Layer 1: Macro Analysis (Claude)
- Layer 2: Technical Analysis (Claude)
- Layer 3: Risk Assessment (Claude)
- Layer 4: Signal Generation
- Layer 5: Event Publishing

Conditional branching:
- After Macro: Check for extreme risk
- After Risk: Check for approval before signal generation
"""

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from .nodes import (
    event_publishing_node,
    initialize_analysis,
    macro_analysis_node,
    risk_assessment_node,
    signal_generation_node,
    technical_analysis_node,
)
from .state import AnalysisState

logger = logging.getLogger(__name__)


def should_proceed_to_technical(state: AnalysisState) -> Literal["technical", "error"]:
    """Conditional edge after macro analysis.

    Only aborts if market_context is entirely missing (unrecoverable error)
    or extreme risk level is detected. Fallback-based analysis is allowed
    to proceed — errors from using fallback are non-fatal.

    Args:
        state: Current workflow state

    Returns:
        "technical" to continue, "error" to abort
    """
    market_context = state.get("market_context")

    # Abort only if macro analysis completely failed (no context at all)
    if not market_context:
        logger.warning("No market context available, aborting workflow")
        return "error"

    # Abort on extreme risk
    if market_context.risk_level == "extreme":
        logger.warning("Extreme risk level detected, aborting workflow")
        return "error"

    return "technical"


def should_approve_signals(state: AnalysisState) -> Literal["generate", "reject"]:
    """Conditional edge after risk assessment.

    Only rejects if risk assessment is entirely missing or explicitly rejected.
    Fallback-based risk assessment that approves signals is allowed to proceed.

    Args:
        state: Current workflow state

    Returns:
        "generate" to proceed with signal generation, "reject" to abort
    """
    risk_assessment = state.get("risk_assessment")

    # Reject if risk assessment completely failed (no result at all)
    if not risk_assessment:
        logger.warning("No risk assessment available, rejecting signals")
        return "reject"

    # Reject only if explicitly not approved
    if not risk_assessment.approved:
        logger.warning("Risk manager rejected signals, aborting workflow")
        return "reject"

    return "generate"


def create_ai_workflow() -> Any:
    """Create the 5-Layer AI Flow workflow graph.

    Returns:
        Compiled LangGraph workflow (CompiledGraph with ainvoke method)
    """
    logger.info("Creating AI workflow graph")

    # Create workflow
    workflow = StateGraph(AnalysisState)

    # Add nodes
    workflow.add_node("initialize", initialize_analysis)
    workflow.add_node("macro", macro_analysis_node)
    workflow.add_node("technical", technical_analysis_node)
    workflow.add_node("risk", risk_assessment_node)
    workflow.add_node("generate", signal_generation_node)
    workflow.add_node("publish", event_publishing_node)

    # Set entry point
    workflow.set_entry_point("initialize")

    # Add edges
    workflow.add_edge("initialize", "macro")

    # Conditional edge: Macro -> Technical or Error
    workflow.add_conditional_edges(
        "macro",
        should_proceed_to_technical,
        {
            "technical": "technical",
            "error": END,
        },
    )

    workflow.add_edge("technical", "risk")

    # Conditional edge: Risk -> Generate or Reject
    workflow.add_conditional_edges(
        "risk",
        should_approve_signals,
        {
            "generate": "generate",
            "reject": END,
        },
    )

    workflow.add_edge("generate", "publish")
    workflow.add_edge("publish", END)

    logger.info("AI workflow graph created successfully")

    # Compile and return
    return workflow.compile()
