---
name: langgraph-patterns
description: LangGraph multi-agent workflow patterns for AI Analysis Service
---

# LangGraph Patterns Skill

## Basic Multi-Agent Workflow

### State Definition

```python
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END

class AnalysisState(TypedDict):
    user_id: str
    regime: str
    symbols: List[str]
    macro_strategy: Optional[dict]
    technical_strategy: Optional[dict]
    risk_score: Optional[float]
    final_decision: Optional[dict]
```

### Agent Definitions

```python
# Agent 1: Macro Strategist (Claude)
async def macro_strategist(state: AnalysisState) -> AnalysisState:
    """Analyze market regime and generate macro strategy."""
    prompt = f"Analyze {state['regime']} for symbols {state['symbols']}"
    response = await claude_client.analyze(prompt, response_format="json")

    return {
        **state,
        "macro_strategy": response
    }

# Agent 2: Technical Analyst (Claude)
async def technical_analyst(state: AnalysisState) -> AnalysisState:
    """Technical analysis based on macro strategy."""
    prompt = f"Technical analysis for {state['symbols']} given {state['macro_strategy']}"
    response = await claude_client.analyze(prompt)

    return {
        **state,
        "technical_strategy": response
    }

# Agent 3: Risk Assessor (Claude)
async def risk_assessor(state: AnalysisState) -> AnalysisState:
    """Calculate risk score."""
    risk_score = calculate_risk(state['technical_strategy'])

    return {
        **state,
        "risk_score": risk_score
    }

# Agent 4: Decision Maker (Claude)
async def decision_maker(state: AnalysisState) -> AnalysisState:
    """Make final trading decision."""
    decision = await claude_client.decide(
        macro=state['macro_strategy'],
        technical=state['technical_strategy'],
        risk=state['risk_score']
    )

    return {
        **state,
        "final_decision": decision
    }
```

---

## Conditional Branching

### Risk-Based Routing

```python
def should_adjust(state: AnalysisState) -> str:
    """Route based on risk score."""
    risk_score = state['risk_score']

    if risk_score < 30:
        return "approve"
    elif risk_score < 70:
        return "adjust"
    else:
        return "reject"

# Build graph with conditional edges
workflow = StateGraph(AnalysisState)
workflow.add_node("risk", risk_assessor)
workflow.add_node("adjust", adjust_strategy)
workflow.add_node("approve", decision_maker)
workflow.add_node("reject", reject_handler)

workflow.add_conditional_edges(
    "risk",
    should_adjust,
    {
        "approve": "approve",
        "adjust": "adjust",
        "reject": "reject"
    }
)
```

### Regime-Based Routing

```python
def route_by_regime(state: AnalysisState) -> str:
    """Different strategy paths for different regimes."""
    regime = state['regime']

    if regime == "crisis":
        return "defensive"
    elif regime == "bull":
        return "aggressive"
    else:
        return "balanced"

workflow.add_conditional_edges(
    "macro",
    route_by_regime,
    {
        "defensive": "defensive_strategy",
        "aggressive": "aggressive_strategy",
        "balanced": "balanced_strategy"
    }
)
```

---

## Feedback Loops

### Adjustment Loop

```python
# Adjustment node
async def adjust_strategy(state: AnalysisState) -> AnalysisState:
    """Adjust technical strategy to reduce risk."""
    adjusted = await claude_client.adjust(
        strategy=state['technical_strategy'],
        target_risk=state['risk_score'] - 20
    )

    return {
        **state,
        "technical_strategy": adjusted,
        "risk_score": None  # Reset to re-assess
    }

# Build graph with feedback loop
workflow = StateGraph(AnalysisState)
workflow.add_node("technical", technical_analyst)
workflow.add_node("risk", risk_assessor)
workflow.add_node("adjust", adjust_strategy)

workflow.add_edge("technical", "risk")
workflow.add_conditional_edges(
    "risk",
    should_adjust,
    {
        "approve": END,
        "adjust": "adjust",  # Loop back
        "reject": END
    }
)
workflow.add_edge("adjust", "technical")  # Re-analyze after adjustment

workflow.set_entry_point("technical")
```

---

## Parallel Execution

### Multi-Strategy Backtesting

```python
from typing import List

class BacktestState(TypedDict):
    strategy: dict
    data: dict
    vectorbt_result: Optional[dict]
    finrl_result: Optional[dict]
    ensemble_result: Optional[dict]

# Parallel backtesting nodes
async def vectorbt_backtest(state: BacktestState) -> BacktestState:
    result = await run_vectorbt(state['strategy'], state['data'])
    return {**state, "vectorbt_result": result}

async def finrl_backtest(state: BacktestState) -> BacktestState:
    result = await run_finrl(state['strategy'], state['data'])
    return {**state, "finrl_result": result}

async def ensemble_backtest(state: BacktestState) -> BacktestState:
    result = await run_ensemble(state['strategy'], state['data'])
    return {**state, "ensemble_result": result}

# Coordinator
async def backtest_coordinator(state: BacktestState) -> BacktestState:
    """Compare all backtest results."""
    best = select_best(
        state['vectorbt_result'],
        state['finrl_result'],
        state['ensemble_result']
    )
    return {**state, "best_strategy": best}

# Build parallel workflow
workflow = StateGraph(BacktestState)
workflow.add_node("vectorbt", vectorbt_backtest)
workflow.add_node("finrl", finrl_backtest)
workflow.add_node("ensemble", ensemble_backtest)
workflow.add_node("coordinator", backtest_coordinator)

# All three run in parallel
workflow.set_entry_point("vectorbt")
workflow.set_entry_point("finrl")
workflow.set_entry_point("ensemble")

# All converge to coordinator
workflow.add_edge("vectorbt", "coordinator")
workflow.add_edge("finrl", "coordinator")
workflow.add_edge("ensemble", "coordinator")
workflow.add_edge("coordinator", END)
```

---

## Complete AI Analysis Workflow

```python
from langgraph.graph import StateGraph, END

class FullAnalysisState(TypedDict):
    user_id: str
    regime: str
    symbols: List[str]
    macro_strategy: Optional[dict]
    technical_strategy: Optional[dict]
    backtest_result: Optional[dict]
    risk_score: Optional[float]
    final_decision: Optional[dict]
    iteration: int

async def macro_strategist(state):
    # Claude macro analysis
    pass

async def technical_analyst(state):
    # Claude technical analysis
    pass

async def backtester(state):
    # Multi-strategy backtest (parallel internally)
    pass

async def risk_assessor(state):
    # Calculate risk score
    pass

async def adjuster(state):
    # Adjust strategy based on risk
    state['iteration'] += 1
    pass

async def decision_maker(state):
    # Final decision
    pass

def route_by_risk(state) -> str:
    if state['risk_score'] < 30:
        return "approve"
    elif state['risk_score'] < 70 and state['iteration'] < 3:
        return "adjust"
    else:
        return "reject"

# Build workflow
workflow = StateGraph(FullAnalysisState)

# Add all nodes
workflow.add_node("macro", macro_strategist)
workflow.add_node("technical", technical_analyst)
workflow.add_node("backtest", backtester)
workflow.add_node("risk", risk_assessor)
workflow.add_node("adjust", adjuster)
workflow.add_node("approve", decision_maker)

# Linear path until risk
workflow.add_edge("macro", "technical")
workflow.add_edge("technical", "backtest")
workflow.add_edge("backtest", "risk")

# Conditional branching
workflow.add_conditional_edges(
    "risk",
    route_by_risk,
    {
        "approve": "approve",
        "adjust": "adjust",
        "reject": END
    }
)

# Feedback loop
workflow.add_edge("adjust", "technical")  # Re-run from technical
workflow.add_edge("approve", END)

workflow.set_entry_point("macro")

# Compile and run
app = workflow.compile()
result = await app.ainvoke({
    "user_id": "user123",
    "regime": "crisis",
    "symbols": ["AAPL", "MSFT"],
    "iteration": 0
})
```

---

## Error Handling

### Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def claude_with_retry(prompt: str):
    return await claude_client.analyze(prompt, response_format="json")

async def macro_strategist(state: AnalysisState) -> AnalysisState:
    try:
        response = await claude_with_retry(prompt)
        return {**state, "macro_strategy": response}
    except Exception as e:
        # Fallback to rule-based
        return {**state, "macro_strategy": fallback_strategy()}
```

### Timeout

```python
import asyncio

async def technical_analyst(state: AnalysisState) -> AnalysisState:
    try:
        response = await asyncio.wait_for(
            claude_client.analyze(prompt),
            timeout=30.0
        )
        return {**state, "technical_strategy": response}
    except asyncio.TimeoutError:
        # Handle timeout
        return {**state, "technical_strategy": None, "error": "timeout"}
```

---

## Monitoring and Logging

### State Logging

```python
import logging

logger = logging.getLogger(__name__)

async def macro_strategist(state: AnalysisState) -> AnalysisState:
    logger.info("Macro strategist started", extra={
        "user_id": state['user_id'],
        "regime": state['regime'],
        "symbols": state['symbols']
    })

    response = await claude_client.analyze(prompt, response_format="json")

    logger.info("Macro strategist completed", extra={
        "confidence": response.get('confidence'),
        "duration_ms": duration
    })

    return {**state, "macro_strategy": response}
```

### Performance Metrics

```python
import time

async def measure_node(node_func):
    """Decorator to measure node execution time."""
    async def wrapper(state):
        start = time.time()
        result = await node_func(state)
        duration = (time.time() - start) * 1000

        logger.info(f"{node_func.__name__} completed", extra={
            "duration_ms": duration
        })

        return result
    return wrapper

# Apply to nodes
workflow.add_node("macro", measure_node(macro_strategist))
```

---

## Critical LangGraph Rules

1. **Always define state as TypedDict** (type safety)
2. **Return updated state**, not just changes
3. **Use conditional edges** for routing logic
4. **Limit feedback loops** (max iterations)
5. **Handle agent failures** (retry, fallback)
6. **Log state transitions** (debugging)
7. **Set timeouts** on all LLM calls
8. **Parallelize independent agents** (performance)
