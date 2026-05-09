"""Tests for `bloasis.strategy.runner.execute_strategy_step` (PR49).

The runner is the single per-step entry point used by both backtest
(once per trading day in a fold) and live (once per cron invocation).
Same code, different OrderExecutor — `SimulatedPortfolio` for backtest,
`AlpacaBrokerAdapter` for live. Without this consolidation, every
risk / overlay / sizing change has to be made in two places (and was
silently missing from the live path until PR48).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from bloasis.backtest.portfolio import SimulatedPortfolio
from bloasis.broker.protocols import (
    AccountInfo,
    BrokerAdapter,
    BrokerOrder,
    BrokerPosition,
    OrderResult,
)

# ---------------------------------------------------------------------------
# SimulatedPortfolio implements BrokerAdapter protocol
# ---------------------------------------------------------------------------


def test_sim_portfolio_satisfies_broker_adapter_protocol() -> None:
    """SimulatedPortfolio MUST be a runtime BrokerAdapter so the same
    runner code drives backtest + live.
    """
    panel: dict[str, pd.DataFrame] = {}
    p = SimulatedPortfolio(initial_capital=10_000.0, data_panel=panel)
    assert isinstance(p, BrokerAdapter)


def test_sim_portfolio_get_account_returns_initial_capital() -> None:
    p = SimulatedPortfolio(initial_capital=10_000.0, data_panel={})
    acc = p.get_account()
    assert isinstance(acc, AccountInfo)
    assert acc.cash == pytest.approx(10_000.0)
    assert acc.equity == pytest.approx(10_000.0)


def test_sim_portfolio_get_positions_starts_empty() -> None:
    p = SimulatedPortfolio(initial_capital=10_000.0, data_panel={})
    assert p.get_positions() == []


def test_sim_portfolio_mode_is_offline() -> None:
    p = SimulatedPortfolio(initial_capital=10_000.0, data_panel={})
    assert p.mode == "offline"


# ---------------------------------------------------------------------------
# place_market_order on SimulatedPortfolio uses next-day open from panel
# ---------------------------------------------------------------------------


def _make_panel(symbol: str, signal_close: float, next_open: float) -> dict:
    """Two-day panel: signal_date close + next-day open."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2026-05-08", tz="UTC"), pd.Timestamp("2026-05-11", tz="UTC")]
    )
    df = pd.DataFrame(
        {
            "open": [signal_close, next_open],
            "high": [signal_close * 1.01, next_open * 1.01],
            "low": [signal_close * 0.99, next_open * 0.99],
            "close": [signal_close, next_open],
            "volume": [1_000_000, 1_000_000],
            "atr_14": [signal_close * 0.02, next_open * 0.02],
        },
        index=idx,
    )
    return {symbol: df}


def _exec_cfg():
    """Minimal market-mode execution config — no slippage/fees so the
    tests focus on correctness of the dispatch, not the friction model."""
    from bloasis.config.schema import ExecutionConfig

    return ExecutionConfig(
        fill_mode="market",
        market_slippage_bps=0.0,
        fees_bps=0.0,
        initial_capital=100_000.0,
    )


def test_sim_portfolio_place_buy_fills_at_next_day_open() -> None:
    panel = _make_panel("AAPL", signal_close=200.0, next_open=201.0)
    p = SimulatedPortfolio(initial_capital=100_000.0, data_panel=panel, execution_cfg=_exec_cfg())
    p.advance_clock(date(2026, 5, 8))

    order = BrokerOrder(
        symbol="AAPL",
        side="buy",
        qty=10.0,
        client_order_id="bt-AAPL-1",
    )
    result = p.place_market_order(order)
    assert isinstance(result, OrderResult)
    assert result.status == "filled"
    assert result.filled_qty == pytest.approx(10.0)
    # Filled near next day's open price (with possible slippage).
    assert 200.5 < result.filled_avg_price < 202.0


def test_sim_portfolio_buy_then_sell_realizes_pnl() -> None:
    panel = _make_panel("MSFT", signal_close=400.0, next_open=400.0)
    p = SimulatedPortfolio(initial_capital=100_000.0, data_panel=panel, execution_cfg=_exec_cfg())
    p.advance_clock(date(2026, 5, 8))

    p.place_market_order(BrokerOrder("MSFT", "buy", 5.0, "buy-1"))
    positions_after_buy = p.get_positions()
    assert len(positions_after_buy) == 1
    assert positions_after_buy[0].symbol == "MSFT"
    assert positions_after_buy[0].quantity == pytest.approx(5.0)

    # Sell back at same date (using the same panel — fill simulator will
    # use next-day open which equals signal_close in this panel).
    sell_result = p.place_market_order(BrokerOrder("MSFT", "sell", 5.0, "sell-1"))
    assert sell_result.status == "filled"
    assert p.get_positions() == []


def test_sim_portfolio_buy_persists_position_via_get_positions() -> None:
    panel = _make_panel("GOOG", signal_close=180.0, next_open=180.0)
    p = SimulatedPortfolio(initial_capital=100_000.0, data_panel=panel, execution_cfg=_exec_cfg())
    p.advance_clock(date(2026, 5, 8))

    p.place_market_order(BrokerOrder("GOOG", "buy", 3.0, "buy-1"))
    pos = p.get_positions()
    assert len(pos) == 1
    assert isinstance(pos[0], BrokerPosition)
    assert pos[0].symbol == "GOOG"
    assert pos[0].quantity == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# AlpacaBrokerAdapter still satisfies BrokerAdapter (no regression)
# ---------------------------------------------------------------------------


def test_alpaca_adapter_satisfies_protocol() -> None:
    """Sanity — PR49 must not break the existing adapter."""
    from bloasis.broker.alpaca import AlpacaBrokerAdapter

    # Construct with a stub client so we don't need real env vars.
    stub = MagicMock()
    stub.get_account.return_value = MagicMock(cash="1000", equity="1000", buying_power="2000")
    stub.get_all_positions.return_value = []
    adapter = AlpacaBrokerAdapter(mode="paper", client=stub)
    assert isinstance(adapter, BrokerAdapter)


# ---------------------------------------------------------------------------
# execute_strategy_step — same code drives backtest + live
# ---------------------------------------------------------------------------


def test_execute_step_smoke_with_no_candidates() -> None:
    """Smoke: empty candidates list → no signals → no orders submitted,
    but executor state was consulted (account.equity needed for sizing)."""
    from bloasis.config import StrategyConfig
    from bloasis.risk import MarketState, PortfolioState
    from bloasis.strategy.runner import execute_strategy_step

    executor = MagicMock(spec=BrokerAdapter)
    executor.get_account.return_value = AccountInfo(
        cash=100_000.0, equity=100_000.0, buying_power=200_000.0
    )
    executor.get_positions.return_value = []

    cfg = StrategyConfig()
    res = execute_strategy_step(
        cfg=cfg,
        candidates=[],
        held_positions=[],
        market_state=MarketState(timestamp=datetime(2026, 5, 11, tzinfo=UTC), vix=15.0),
        spy_returns_to_date=pd.Series([], dtype=float),
        portfolio_state=PortfolioState(total_value=100_000.0, sector_concentrations={}),
        signal_date=datetime(2026, 5, 11, tzinfo=UTC),
        executor=executor,
    )
    assert res.submitted == []
    assert res.new_buy_set == set()
    # executor.place_market_order should not have been called.
    executor.place_market_order.assert_not_called()


def test_execute_step_submits_buy_for_buy_signal_via_executor() -> None:
    """End-to-end: candidate with score above entry threshold → BUY signal
    → executor.place_market_order called with the right symbol+side+qty."""
    from bloasis.config import StrategyConfig
    from bloasis.risk import MarketState, PortfolioState
    from bloasis.signal import CandidateData
    from bloasis.strategy.runner import execute_strategy_step

    # Build a CandidateData with a high score (>= entry_threshold default 0.5).
    feature_vector = MagicMock()
    feature_vector.symbol = "AAPL"
    feature_vector.atr_14 = 4.0
    feature_vector.timestamp = datetime(2026, 5, 11, tzinfo=UTC)
    scored = MagicMock()
    scored.symbol = "AAPL"
    scored.score = 0.99
    scored.timestamp = feature_vector.timestamp
    scored.rationale = MagicMock(triggers=["edgar"], risks=[], contributions=[])
    candidate = CandidateData(
        scored=scored, feature_vector=feature_vector, last_close=200.0, sector=None
    )

    executor = MagicMock(spec=BrokerAdapter)
    executor.get_account.return_value = AccountInfo(
        cash=100_000.0, equity=100_000.0, buying_power=200_000.0
    )
    executor.get_positions.return_value = []
    executor.place_market_order.return_value = OrderResult(
        order_id="x",
        client_order_id="y",
        status="filled",
        filled_qty=10.0,
        filled_avg_price=200.5,
        submitted_at=datetime(2026, 5, 11, tzinfo=UTC),
    )

    cfg = StrategyConfig()
    res = execute_strategy_step(
        cfg=cfg,
        candidates=[candidate],
        held_positions=[],
        market_state=MarketState(timestamp=datetime(2026, 5, 11, tzinfo=UTC), vix=15.0),
        spy_returns_to_date=pd.Series([], dtype=float),
        portfolio_state=PortfolioState(total_value=100_000.0, sector_concentrations={}),
        signal_date=datetime(2026, 5, 11, tzinfo=UTC),
        executor=executor,
    )
    assert len(res.submitted) == 1
    order, _result, sig = res.submitted[0]
    assert order.symbol == "AAPL"
    assert order.side == "buy"
    assert order.qty > 0
    assert sig.action == "BUY"
    assert "AAPL" in res.new_buy_set
