"""Tests for InMemoryPaperBroker — fills, idempotency, account/position tracking."""

from __future__ import annotations

import pytest

from bloasis.broker import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    InMemoryPaperBroker,
)


def _broker(prices: dict[str, float], **kwargs: float) -> InMemoryPaperBroker:
    return InMemoryPaperBroker(price_fn=prices.__getitem__, **kwargs)


def test_initial_account_state() -> None:
    b = _broker({"AAPL": 150.0}, initial_cash=10_000.0)
    acct = b.get_account()
    assert isinstance(acct, AccountInfo)
    assert acct.cash == pytest.approx(10_000.0)
    assert acct.equity == pytest.approx(10_000.0)
    assert acct.buying_power == pytest.approx(10_000.0)
    assert b.get_positions() == []


def test_buy_fills_and_updates_state() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0)
    result = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=10, client_order_id="c1")
    )
    assert result.status == "filled"
    assert result.filled_qty == 10
    assert result.filled_avg_price == pytest.approx(100.0)

    acct = b.get_account()
    assert acct.cash == pytest.approx(9_000.0)
    assert acct.equity == pytest.approx(10_000.0)  # cash + 10*100 last_price

    positions = b.get_positions()
    assert len(positions) == 1
    pos = positions[0]
    assert isinstance(pos, BrokerPosition)
    assert pos.symbol == "AAPL"
    assert pos.quantity == 10
    assert pos.avg_cost == pytest.approx(100.0)
    assert pos.market_value == pytest.approx(1_000.0)


def test_buy_with_slippage_costs_more() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0, slippage_bps=50.0)
    result = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, client_order_id="c1")
    )
    # 50 bps over 100 = 0.5
    assert result.filled_avg_price == pytest.approx(100.5)


def test_idempotent_client_order_id_returns_same_result() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0)
    o = BrokerOrder(symbol="AAPL", side="buy", qty=5, client_order_id="dup-key")
    r1 = b.place_market_order(o)
    r2 = b.place_market_order(o)
    assert r1 is r2
    # Cash should only have been deducted once.
    assert b.get_account().cash == pytest.approx(9_500.0)


def test_buy_rejected_on_insufficient_cash() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=100.0)
    result = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=10, client_order_id="c1")
    )
    assert result.status == "rejected"
    assert "insufficient" in result.reason.lower()
    assert b.get_account().cash == pytest.approx(100.0)


def test_buy_rejected_on_unknown_symbol() -> None:
    b = _broker({"AAPL": 100.0})
    result = b.place_market_order(
        BrokerOrder(symbol="ZZZ", side="buy", qty=1, client_order_id="c1")
    )
    assert result.status == "rejected"


def test_buy_rejected_on_non_positive_price() -> None:
    b = _broker({"AAPL": 0.0})
    result = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, client_order_id="c1")
    )
    assert result.status == "rejected"
    assert "non-positive" in result.reason


def test_sell_reduces_position() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0)
    b.place_market_order(BrokerOrder(symbol="AAPL", side="buy", qty=10, client_order_id="b1"))
    sell = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="sell", qty=4, client_order_id="s1")
    )
    assert sell.status == "filled"
    pos = b.get_positions()[0]
    assert pos.quantity == 6


def test_sell_full_position_removes_it() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0)
    b.place_market_order(BrokerOrder(symbol="AAPL", side="buy", qty=5, client_order_id="b"))
    b.place_market_order(BrokerOrder(symbol="AAPL", side="sell", qty=5, client_order_id="s"))
    assert b.get_positions() == []


def test_sell_rejected_when_no_position() -> None:
    b = _broker({"AAPL": 100.0}, initial_cash=10_000.0)
    result = b.place_market_order(
        BrokerOrder(symbol="AAPL", side="sell", qty=1, client_order_id="s1")
    )
    assert result.status == "rejected"


def test_buy_average_cost_blends_across_lots() -> None:
    # Two buys at 100 and 110 of equal quantity → avg = 105.
    prices = {"AAPL": 100.0}
    b = InMemoryPaperBroker(price_fn=lambda s: prices[s], initial_cash=10_000.0)
    b.place_market_order(BrokerOrder(symbol="AAPL", side="buy", qty=10, client_order_id="b1"))
    prices["AAPL"] = 110.0
    b.place_market_order(BrokerOrder(symbol="AAPL", side="buy", qty=10, client_order_id="b2"))
    pos = b.get_positions()[0]
    assert pos.avg_cost == pytest.approx(105.0)
    assert pos.quantity == 20


def test_cancel_order_returns_false() -> None:
    # Paper broker fills instantly — nothing to cancel.
    b = _broker({"AAPL": 100.0})
    assert b.cancel_order("any-id") is False


def test_mode_is_offline() -> None:
    assert _broker({"X": 1.0}).mode == "offline"
