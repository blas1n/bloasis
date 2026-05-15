"""Tests for `bloasis paper reconcile` + the writer it uses (PR51).

Paper orders persist with `broker_status="accepted"` and `filled_qty=0`
at submit time (market closed at 08:00 KST cron). The actual fill
happens hours later at US market open and is never reflected in the
DB. `paper friction` returns "no filled orders" forever despite the
strategy actually trading.

Reconcile pulls each open paper_orders row, queries Alpaca by
`client_order_id`, and updates the row with the realised fill data
so friction / total-return / per-order slippage analyses see truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.storage import (
    create_all,
    get_engine,
    paper_orders,
    writers,
)

runner = CliRunner()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "paper.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(p))
    create_all(get_engine(p))
    return p


def _seed_accepted_order(engine, client_order_id: str, *, session_id: int = 1) -> int:
    """Seed one paper_orders row in the 'accepted, no fill yet' state."""
    sid = writers.create_paper_session(engine, name="t", config_hash="h", config_json="{}")
    return writers.write_paper_order(
        engine,
        session_id=sid,
        ts=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
        symbol="AAPL",
        side="buy",
        qty=10.0,
        target_capital=2000.0,
        entry_price_hint=200.0,
        filled_qty=0.0,
        filled_avg_price=0.0,
        broker_status="accepted",
        broker_order_id=client_order_id,
        slippage_bps=None,
        fees=0.0,
        rationale_json=None,
    )


# ---------------------------------------------------------------------------
# Writer: update_paper_order_fill
# ---------------------------------------------------------------------------


def test_update_paper_order_fill_writes_realized_status(db_path: Path) -> None:
    engine = get_engine(db_path)
    order_id = _seed_accepted_order(engine, "bloasis-paper-buy-AAPL-100")

    writers.update_paper_order_fill(
        engine,
        client_order_id="bloasis-paper-buy-AAPL-100",
        broker_status="filled",
        filled_qty=10.0,
        filled_avg_price=200.5,
        slippage_bps=25.0,
    )

    with engine.connect() as conn:
        row = conn.execute(
            select(paper_orders).where(paper_orders.c.order_id == order_id)
        ).fetchone()

    assert row is not None
    assert row.broker_status == "filled"
    assert row.filled_qty == pytest.approx(10.0)
    assert row.filled_avg_price == pytest.approx(200.5)
    assert row.slippage_bps == pytest.approx(25.0)


def test_update_paper_order_fill_missing_client_order_id_is_noop(db_path: Path) -> None:
    """Reconciling against an Alpaca order_id we don't have in our DB
    silently no-ops rather than crashing."""
    engine = get_engine(db_path)
    writers.update_paper_order_fill(
        engine,
        client_order_id="never-stored",
        broker_status="filled",
        filled_qty=1.0,
        filled_avg_price=100.0,
        slippage_bps=0.0,
    )
    # No exception; no rows affected.


# ---------------------------------------------------------------------------
# CLI: bloasis paper reconcile <session>
# ---------------------------------------------------------------------------


def test_paper_reconcile_updates_filled_orders_from_alpaca(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = get_engine(db_path)
    _seed_accepted_order(engine, "bloasis-paper-buy-AAPL-x")

    # Mock Alpaca: order is now filled at 200.50 (signal hint was 200.00).
    alpaca_order = MagicMock()
    alpaca_order.status = "filled"
    alpaca_order.filled_qty = 10.0
    alpaca_order.filled_avg_price = 200.50

    broker = MagicMock()
    broker._client.get_order_by_client_id.return_value = alpaca_order
    monkeypatch.setattr("bloasis.broker.AlpacaBrokerAdapter", lambda mode="paper": broker)

    res = runner.invoke(app, ["paper", "reconcile", "t"])
    assert res.exit_code == 0, res.output

    with engine.connect() as conn:
        rows = conn.execute(select(paper_orders)).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r.broker_status == "filled"
    assert r.filled_qty == pytest.approx(10.0)
    assert r.filled_avg_price == pytest.approx(200.50)
    # slippage = (200.50 - 200.00) / 200.00 × 10000 = 25 bps
    assert r.slippage_bps == pytest.approx(25.0)


def test_paper_reconcile_skips_already_terminal_orders(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orders already in a terminal state (filled / rejected / canceled)
    are skipped — no Alpaca round-trip needed."""
    engine = get_engine(db_path)
    sid = writers.create_paper_session(engine, name="t", config_hash="h", config_json="{}")
    writers.write_paper_order(
        engine,
        session_id=sid,
        ts=datetime(2026, 5, 11, tzinfo=UTC),
        symbol="MSFT",
        side="buy",
        qty=5.0,
        target_capital=1000.0,
        entry_price_hint=200.0,
        filled_qty=5.0,
        filled_avg_price=200.0,
        broker_status="filled",  # already terminal
        broker_order_id="already-done",
        slippage_bps=0.0,
        fees=0.0,
        rationale_json=None,
    )

    broker = MagicMock()
    broker._client.get_order_by_client_id = MagicMock()
    monkeypatch.setattr("bloasis.broker.AlpacaBrokerAdapter", lambda mode="paper": broker)

    res = runner.invoke(app, ["paper", "reconcile", "t"])
    assert res.exit_code == 0, res.output
    # No Alpaca query because the only row was already filled.
    broker._client.get_order_by_client_id.assert_not_called()


def test_paper_reconcile_handles_partial_fill(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial fill updates the row to status='partially_filled' with
    the actually-filled quantity (not the requested qty)."""
    engine = get_engine(db_path)
    _seed_accepted_order(engine, "bloasis-paper-buy-AAPL-pf")

    alpaca_order = MagicMock()
    alpaca_order.status = "partially_filled"
    alpaca_order.filled_qty = 3.0  # asked for 10, only 3 filled
    alpaca_order.filled_avg_price = 200.10

    broker = MagicMock()
    broker._client.get_order_by_client_id.return_value = alpaca_order
    monkeypatch.setattr("bloasis.broker.AlpacaBrokerAdapter", lambda mode="paper": broker)

    res = runner.invoke(app, ["paper", "reconcile", "t"])
    assert res.exit_code == 0, res.output

    with engine.connect() as conn:
        row = conn.execute(select(paper_orders)).fetchone()
    assert row is not None
    assert row.broker_status == "partially_filled"
    assert row.filled_qty == pytest.approx(3.0)
    assert row.filled_avg_price == pytest.approx(200.10)


def test_paper_reconcile_unknown_session(db_path: Path) -> None:
    res = runner.invoke(app, ["paper", "reconcile", "nope"])
    assert res.exit_code != 0
    assert "not found" in res.output.lower() or "no" in res.output.lower()
