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


def _fake_signal(symbol: str) -> MagicMock:
    """A BUY signal stub matching the attributes _execute_against_broker reads."""
    sig = MagicMock()
    sig.action = "BUY"
    sig.symbol = symbol
    sig.entry_price = 200.0
    sig.target_size_pct = 0.02
    sig.timestamp = pd.Timestamp("2026-05-09", tz="UTC")
    sig.reason = f"smoke-{symbol}"
    return sig


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
