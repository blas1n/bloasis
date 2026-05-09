"""Schema + writer tests for paper-trading persistence (PR45).

Three new tables let us measure friction, OOS alpha, and rotation
behaviour from `bloasis trade paper`:

  paper_sessions          one row per running paper session
  paper_orders            every BUY/SELL submitted to broker (with fill)
  paper_equity_snapshots  daily mark-to-market from broker.get_account()
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from bloasis.storage import (
    create_all,
    get_engine,
    paper_equity_snapshots,
    paper_orders,
    paper_sessions,
    writers,
)


@pytest.fixture
def engine(tmp_path: Path):
    eng = get_engine(tmp_path / "paper.db")
    create_all(eng)
    return eng


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def test_paper_tables_created(engine) -> None:
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"paper_sessions", "paper_orders", "paper_equity_snapshots"} <= names


# ---------------------------------------------------------------------------
# create_paper_session — idempotent by name
# ---------------------------------------------------------------------------


def test_create_paper_session_returns_id(engine) -> None:
    sid = writers.create_paper_session(
        engine,
        name="edgar-rolling2-paper-2026-05",
        config_hash="abcd1234",
        config_json='{"foo": 1}',
    )
    assert isinstance(sid, int) and sid > 0


def test_create_paper_session_idempotent_by_name(engine) -> None:
    """Calling twice with same name returns the existing session_id (no dup row)."""
    sid1 = writers.create_paper_session(
        engine, name="dup-test", config_hash="abcd", config_json="{}"
    )
    sid2 = writers.create_paper_session(
        engine, name="dup-test", config_hash="abcd", config_json="{}"
    )
    assert sid1 == sid2

    with engine.connect() as conn:
        n = conn.execute(
            select(paper_sessions.c.session_id).where(paper_sessions.c.name == "dup-test")
        ).fetchall()
    assert len(n) == 1


# ---------------------------------------------------------------------------
# write_paper_order — captures fill data + rationale + slippage
# ---------------------------------------------------------------------------


def test_write_paper_order_persists_full_row(engine) -> None:
    sid = writers.create_paper_session(engine, name="x", config_hash="h", config_json="{}")
    ts = datetime(2026, 5, 9, 16, 0, tzinfo=UTC)

    order_id = writers.write_paper_order(
        engine,
        session_id=sid,
        ts=ts,
        symbol="AAPL",
        side="buy",
        qty=10.0,
        target_capital=2000.0,
        entry_price_hint=200.0,
        filled_qty=10.0,
        filled_avg_price=200.5,
        broker_status="filled",
        broker_order_id="bloasis-paper-AAPL-1",
        slippage_bps=2.5,
        fees=0.0,
        rationale_json='{"score": 0.99, "scorer": "edgar_textdiff"}',
    )
    assert order_id > 0

    with engine.connect() as conn:
        row = conn.execute(
            select(paper_orders).where(paper_orders.c.order_id == order_id)
        ).fetchone()

    assert row.session_id == sid
    assert row.symbol == "AAPL"
    assert row.side == "buy"
    assert row.qty == pytest.approx(10.0)
    assert row.target_capital == pytest.approx(2000.0)
    assert row.entry_price_hint == pytest.approx(200.0)
    assert row.filled_qty == pytest.approx(10.0)
    assert row.filled_avg_price == pytest.approx(200.5)
    assert row.broker_status == "filled"
    assert row.broker_order_id == "bloasis-paper-AAPL-1"
    assert row.slippage_bps == pytest.approx(2.5)
    assert row.rationale_json == '{"score": 0.99, "scorer": "edgar_textdiff"}'


def test_write_paper_order_handles_rejected(engine) -> None:
    """Rejected orders should still persist (with filled_qty=0, status='rejected')."""
    sid = writers.create_paper_session(engine, name="x", config_hash="h", config_json="{}")
    order_id = writers.write_paper_order(
        engine,
        session_id=sid,
        ts=datetime(2026, 5, 9, tzinfo=UTC),
        symbol="MSFT",
        side="buy",
        qty=5.0,
        target_capital=1000.0,
        entry_price_hint=200.0,
        filled_qty=0.0,
        filled_avg_price=0.0,
        broker_status="rejected",
        broker_order_id="bloasis-paper-MSFT-1",
        slippage_bps=None,
        fees=0.0,
        rationale_json=None,
    )
    with engine.connect() as conn:
        row = conn.execute(
            select(paper_orders).where(paper_orders.c.order_id == order_id)
        ).fetchone()
    assert row.broker_status == "rejected"
    assert row.filled_qty == pytest.approx(0.0)
    assert row.slippage_bps is None
    assert row.rationale_json is None


# ---------------------------------------------------------------------------
# snapshot_paper_equity — daily MTM
# ---------------------------------------------------------------------------


def test_snapshot_paper_equity_persists_account_state(engine) -> None:
    sid = writers.create_paper_session(engine, name="x", config_hash="h", config_json="{}")
    ts = datetime(2026, 5, 9, 20, 0, tzinfo=UTC)
    writers.snapshot_paper_equity(
        engine,
        session_id=sid,
        ts=ts,
        cash=15_000.0,
        positions_value=85_000.0,
        equity=100_000.0,
        n_positions=33,
    )
    with engine.connect() as conn:
        row = conn.execute(
            select(paper_equity_snapshots).where(paper_equity_snapshots.c.session_id == sid)
        ).fetchone()
    assert row.cash == pytest.approx(15_000.0)
    assert row.positions_value == pytest.approx(85_000.0)
    assert row.equity == pytest.approx(100_000.0)
    assert row.n_positions == 33


def test_snapshot_paper_equity_multiple_days(engine) -> None:
    sid = writers.create_paper_session(engine, name="x", config_hash="h", config_json="{}")
    for day, eq in [(8, 100_000.0), (9, 100_500.0), (10, 99_800.0)]:
        writers.snapshot_paper_equity(
            engine,
            session_id=sid,
            ts=datetime(2026, 5, day, tzinfo=UTC),
            cash=50_000.0,
            positions_value=eq - 50_000.0,
            equity=eq,
            n_positions=20,
        )
    with engine.connect() as conn:
        rows = conn.execute(
            select(paper_equity_snapshots.c.equity)
            .where(paper_equity_snapshots.c.session_id == sid)
            .order_by(paper_equity_snapshots.c.ts)
        ).fetchall()
    assert [r.equity for r in rows] == pytest.approx([100_000.0, 100_500.0, 99_800.0])


def test_close_paper_session_marks_ended(engine) -> None:
    sid = writers.create_paper_session(engine, name="x", config_hash="h", config_json="{}")
    writers.close_paper_session(engine, session_id=sid)
    with engine.connect() as conn:
        row = conn.execute(
            select(paper_sessions).where(paper_sessions.c.session_id == sid)
        ).fetchone()
    assert row.status == "closed"
    assert row.ended_at is not None
