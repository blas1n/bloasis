"""CLI tests for `bloasis trade paper --session` persistence (PR45).

Mocks AlpacaBrokerAdapter + the candidate builder so no network or yfinance
calls are made. Verifies the runner persists per-order rows and an equity
snapshot, and is idempotent under repeated runs with the same session name.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.storage import (
    create_all,
    get_engine,
    paper_equity_snapshots,
    paper_orders,
    paper_sessions,
)

runner = CliRunner()


@pytest.fixture
def baseline_config(tmp_path: Path) -> Path:
    """Tiny 2-symbol strategy config that produces signals deterministically."""
    payload = {
        "scorer": {
            "type": "edgar_textdiff",
            "edgar_textdiff_top_pct": 0.5,
            "edgar_rolling_window": 1,
        },
        "signal": {
            "position_size_max_pct": 0.02,
        },
    }
    p = tmp_path / "smoke.yaml"
    p.write_text(yaml.safe_dump(payload))
    return p


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "paper.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(p))
    create_all(get_engine(p))
    return p


def _fake_signal(symbol: str, action: str = "BUY") -> MagicMock:
    """Signal stub matching the attributes _execute_against_broker reads."""
    sig = MagicMock()
    sig.action = action
    sig.symbol = symbol
    sig.entry_price = 200.0 if action == "BUY" else None
    sig.target_size_pct = 0.02 if action == "BUY" else 0.0
    sig.timestamp = pd.Timestamp("2026-05-09", tz="UTC")
    sig.reason = f"smoke-{action}-{symbol}"
    return sig


def _fake_position(symbol: str, qty: float = 5.0, price: float = 195.0) -> MagicMock:
    """BrokerPosition stub for broker.get_positions()."""
    pos = MagicMock()
    pos.symbol = symbol
    pos.quantity = qty
    pos.avg_cost = price
    pos.current_price = price
    pos.market_value = qty * price
    return pos


def _patch_broker_and_pipeline(monkeypatch: pytest.MonkeyPatch, symbols: list[str]) -> MagicMock:
    """Stub Alpaca + candidate builder + SignalGenerator. Returns broker mock."""
    broker = MagicMock()
    broker.mode = "paper"
    account = MagicMock()
    account.cash = 100_000.0
    account.equity = 100_000.0
    broker.get_account.return_value = account

    fill = MagicMock()
    fill.status = "filled"
    fill.filled_qty = 10.0
    fill.filled_avg_price = 200.5
    fill.reason = None
    broker.place_market_order.return_value = fill
    # Default: no positions held. Tests that exercise SELL set this explicitly.
    broker.get_positions.return_value = []

    # Both isinstance(broker, BrokerAdapter) sites need to pass — patch
    # the base class so MagicMock instances qualify.
    from bloasis.broker import BrokerAdapter

    BrokerAdapter.register(MagicMock)

    monkeypatch.setattr("bloasis.broker.AlpacaBrokerAdapter", lambda mode="paper": broker)
    monkeypatch.setattr(
        "bloasis.cli._build_live_candidates",
        lambda cfg, symbols, days: ([MagicMock(symbol=s) for s in symbols], {}),
    )

    sig_gen_cls = MagicMock()
    sig_gen_instance = MagicMock()
    sig_gen_instance.generate.return_value = [_fake_signal(s) for s in symbols]
    sig_gen_cls.return_value = sig_gen_instance
    monkeypatch.setattr("bloasis.signal.SignalGenerator", sig_gen_cls)

    return broker


def test_paper_run_without_session_persists_nothing(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy behavior: no --session arg means no persistence (back-compat)."""
    _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])

    res = runner.invoke(
        app,
        [
            "trade",
            "paper",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "-c",
            str(baseline_config),
        ],
    )
    assert res.exit_code == 0, res.output

    eng = get_engine(db_path)
    with eng.connect() as conn:
        n_sess = conn.execute(select(paper_sessions)).fetchall()
        n_ord = conn.execute(select(paper_orders)).fetchall()
        n_snap = conn.execute(select(paper_equity_snapshots)).fetchall()
    assert (len(n_sess), len(n_ord), len(n_snap)) == (0, 0, 0)


def test_paper_run_with_session_creates_session_and_orders(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])

    res = runner.invoke(
        app,
        [
            "trade",
            "paper",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "-c",
            str(baseline_config),
            "--session",
            "smoke-session",
        ],
    )
    assert res.exit_code == 0, res.output
    assert broker.place_market_order.called

    eng = get_engine(db_path)
    with eng.connect() as conn:
        sessions = conn.execute(select(paper_sessions)).fetchall()
        orders = conn.execute(select(paper_orders)).fetchall()
        snaps = conn.execute(select(paper_equity_snapshots)).fetchall()

    assert len(sessions) == 1
    assert sessions[0].name == "smoke-session"
    assert sessions[0].status == "running"

    # 2 candidates → 2 orders submitted.
    assert len(orders) == 2
    symbols = sorted(o.symbol for o in orders)
    assert symbols == ["AAPL", "MSFT"]
    for o in orders:
        assert o.broker_status == "filled"
        assert o.filled_qty == pytest.approx(10.0)
        assert o.filled_avg_price == pytest.approx(200.5)
        # slippage = (200.5 - 200.0) / 200.0 * 10000 = 25 bps
        assert o.slippage_bps == pytest.approx(25.0)

    # Exactly one daily snapshot per run.
    assert len(snaps) == 1
    assert snaps[0].equity == pytest.approx(100_000.0)


def test_paper_session_idempotent_across_runs(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running with the same --session name resumes (no duplicate row)."""
    _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])

    for _ in range(3):
        res = runner.invoke(
            app,
            [
                "trade",
                "paper",
                "-s",
                "AAPL",
                "-s",
                "MSFT",
                "-c",
                str(baseline_config),
                "--session",
                "daily-cron",
            ],
        )
        assert res.exit_code == 0, res.output

    eng = get_engine(db_path)
    with eng.connect() as conn:
        sessions = conn.execute(select(paper_sessions)).fetchall()
        orders = conn.execute(select(paper_orders)).fetchall()
        snaps = conn.execute(select(paper_equity_snapshots)).fetchall()

    assert len(sessions) == 1
    assert len(orders) == 6  # 3 runs × 2 symbols
    assert len(snaps) == 3  # 3 runs × 1 snapshot each


# ---------------------------------------------------------------------------
# PR46 — SELL handling + held-position fetch
# ---------------------------------------------------------------------------


def test_paper_run_fetches_held_positions_for_signal_generator(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without held positions passed in, SignalGenerator can't emit SELL signals.

    The runner must call broker.get_positions() and pass them through.
    """
    broker = _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])
    broker.get_positions.return_value = [
        _fake_position("GOOG", qty=3.0, price=180.0),
        _fake_position("META", qty=4.0, price=400.0),
    ]

    res = runner.invoke(
        app,
        [
            "trade",
            "paper",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "-c",
            str(baseline_config),
            "--session",
            "sell-test-1",
        ],
    )
    assert res.exit_code == 0, res.output

    # broker.get_positions must have been called (rotation needs current state)
    assert broker.get_positions.called

    # SignalGenerator.generate(candidates, held=...) — `held` must be non-empty
    # since broker reported 2 positions. Inspect the call kwargs.
    from bloasis import signal as signal_mod

    sig_gen_cls = signal_mod.SignalGenerator  # patched MagicMock class
    instance = sig_gen_cls.return_value
    # Last call's `held` kwarg should contain 2 HeldPosition objects matching
    # broker's positions (translated symbols).
    assert instance.generate.called
    call_kwargs = instance.generate.call_args.kwargs
    held = list(call_kwargs.get("held", ()))
    held_symbols = sorted(h.symbol for h in held)
    assert held_symbols == ["GOOG", "META"]


def test_paper_run_submits_sell_orders_and_persists_them(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SELL signals from SignalGenerator must be submitted as sell orders
    and persisted to paper_orders with side='sell'."""
    broker = _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])
    broker.get_positions.return_value = [
        _fake_position("GOOG", qty=3.0, price=180.0),
    ]
    # SignalGenerator returns: 2 BUYs (AAPL, MSFT) + 1 SELL (GOOG)
    from bloasis import signal as signal_mod

    sig_gen_cls = signal_mod.SignalGenerator
    sig_gen_cls.return_value.generate.return_value = [
        _fake_signal("AAPL", "BUY"),
        _fake_signal("MSFT", "BUY"),
        _fake_signal("GOOG", "SELL"),
    ]
    # SELL fill: broker returns 3 shares filled at slightly worse price
    sell_fill = MagicMock()
    sell_fill.status = "filled"
    sell_fill.filled_qty = 3.0
    sell_fill.filled_avg_price = 179.5
    sell_fill.reason = None
    buy_fill = MagicMock()
    buy_fill.status = "filled"
    buy_fill.filled_qty = 10.0
    buy_fill.filled_avg_price = 200.5
    buy_fill.reason = None

    def route_order(order: object) -> MagicMock:
        return sell_fill if getattr(order, "side", None) == "sell" else buy_fill

    broker.place_market_order.side_effect = route_order

    res = runner.invoke(
        app,
        [
            "trade",
            "paper",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "-c",
            str(baseline_config),
            "--session",
            "sell-test-2",
        ],
    )
    assert res.exit_code == 0, res.output

    eng = get_engine(db_path)
    with eng.connect() as conn:
        orders = conn.execute(select(paper_orders)).fetchall()

    # 2 BUY + 1 SELL = 3 orders persisted
    sides = sorted(o.side for o in orders)
    assert sides == ["buy", "buy", "sell"]

    sell_row = next(o for o in orders if o.side == "sell")
    assert sell_row.symbol == "GOOG"
    assert sell_row.qty == pytest.approx(3.0)
    assert sell_row.filled_qty == pytest.approx(3.0)
    assert sell_row.filled_avg_price == pytest.approx(179.5)
    assert sell_row.broker_status == "filled"


def test_paper_run_no_sell_when_no_held_positions(
    baseline_config: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First-day run (empty broker) should still work — only BUYs."""
    broker = _patch_broker_and_pipeline(monkeypatch, ["AAPL", "MSFT"])
    broker.get_positions.return_value = []  # explicit clarity

    res = runner.invoke(
        app,
        [
            "trade",
            "paper",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "-c",
            str(baseline_config),
            "--session",
            "first-day",
        ],
    )
    assert res.exit_code == 0, res.output

    eng = get_engine(db_path)
    with eng.connect() as conn:
        orders = conn.execute(select(paper_orders)).fetchall()
    assert all(o.side == "buy" for o in orders)
    assert len(orders) == 2
