"""Tests for `bloasis.backtest.portfolio`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bloasis.backtest.portfolio import Fill, SimulatedPortfolio

NOW = datetime.now(tz=UTC)


def _buy(symbol: str, qty: float, price: float, sector: str | None = None) -> Fill:
    return Fill(
        timestamp=NOW,
        symbol=symbol,
        side="buy",
        quantity=qty,
        price=price,
        sector=sector,
    )


def _sell(symbol: str, qty: float, price: float) -> Fill:
    return Fill(
        timestamp=NOW,
        symbol=symbol,
        side="sell",
        quantity=qty,
        price=price,
    )


def test_starting_state() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    assert p.cash == 10_000
    assert p.total_equity() == 10_000
    assert p.held_symbols() == set()


def test_apply_buy_deducts_cash_and_adds_position() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("AAPL", 10, 150))
    assert p.cash == 10_000 - 1500
    assert "AAPL" in p.positions
    assert p.positions["AAPL"].quantity == 10
    assert p.positions["AAPL"].avg_cost == 150


def test_apply_buy_insufficient_cash_raises() -> None:
    p = SimulatedPortfolio(initial_capital=100)
    with pytest.raises(ValueError, match="insufficient cash"):
        p.apply(_buy("X", 10, 1000))


def test_apply_sell_credits_cash_and_realizes_pnl() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("AAPL", 10, 100))
    sell_fill = p.apply(_sell("AAPL", 10, 120))
    assert sell_fill.realized_pnl == pytest.approx(200.0)
    assert p.cash == pytest.approx(10_000 - 1000 + 1200)
    assert "AAPL" not in p.positions


def test_apply_partial_sell_keeps_remainder() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("AAPL", 10, 100))
    p.apply(_sell("AAPL", 4, 110))
    assert p.positions["AAPL"].quantity == 6


def test_apply_sell_oversize_raises() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("AAPL", 10, 100))
    with pytest.raises(ValueError, match="cannot sell"):
        p.apply(_sell("AAPL", 50, 100))


def test_buy_again_updates_avg_cost() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("X", 10, 100))
    p.apply(_buy("X", 10, 200))
    # weighted avg = (10*100 + 10*200) / 20 = 150
    assert p.positions["X"].avg_cost == 150.0
    assert p.positions["X"].quantity == 20


def test_mark_updates_last_price() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("X", 10, 100))
    p.mark({"X": 110.0})
    assert p.positions["X"].last_price == 110.0
    assert p.invested_value() == 1100.0
    assert p.total_equity() == 10_000 - 1000 + 1100


def test_sector_concentrations() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("A", 10, 100, sector="Tech"))
    p.apply(_buy("B", 10, 100, sector="Tech"))
    p.apply(_buy("C", 10, 100, sector="Energy"))
    p.mark({"A": 100, "B": 100, "C": 100})
    conc = p.sector_concentrations()
    # Total 3000 / 10000, Tech = 2000 / 10000 = 20%
    assert conc["Tech"] == pytest.approx(0.2)
    assert conc["Energy"] == pytest.approx(0.1)


def test_check_stops_emits_sell_on_sl() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("X", 10, 100))
    p.attach_levels("X", stop_loss=95.0, take_profit=120.0)
    fills = p.check_stops({"X": {"high": 99, "low": 94, "close": 96}}, NOW)
    assert len(fills) == 1
    assert fills[0].side == "sell"
    assert fills[0].reason == "stop-loss hit"
    assert "X" not in p.positions


def test_check_stops_emits_sell_on_tp() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("X", 10, 100))
    p.attach_levels("X", stop_loss=80.0, take_profit=120.0)
    fills = p.check_stops({"X": {"high": 125, "low": 100, "close": 122}}, NOW)
    assert len(fills) == 1
    assert fills[0].reason == "take-profit hit"


def test_check_stops_no_action_within_band() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("X", 10, 100))
    p.attach_levels("X", stop_loss=80.0, take_profit=120.0)
    fills = p.check_stops({"X": {"high": 110, "low": 95, "close": 105}}, NOW)
    assert fills == []
    assert "X" in p.positions


def test_win_rate_tracking() -> None:
    p = SimulatedPortfolio(initial_capital=10_000)
    p.apply(_buy("A", 10, 100))
    p.apply(_sell("A", 10, 120))  # win
    p.apply(_buy("B", 10, 100))
    p.apply(_sell("B", 10, 80))  # loss
    assert p.win_count == 1
    assert p.loss_count == 1
