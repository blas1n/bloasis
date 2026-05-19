"""CLI tests for `bloasis paper {sessions,show,entry-gap,close}` (PR47/PR52).

Populates the paper_* tables directly via writers, then invokes the
analysis subcommands and asserts on the rendered output.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.storage import (
    create_all,
    get_engine,
    paper_sessions,
    writers,
)

runner = CliRunner()


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "paper.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(p))
    create_all(get_engine(p))
    return p


def _seed_session(
    engine, name: str, *, n_orders: int = 4, equity_path: list[float] | None = None
) -> int:
    """Seed a session with N orders and an equity curve.

    Default equity path: [100k, 100.5k, 101k, 100.8k, 102k] (5 points).
    Each order has +25 bps slippage (filled at hint × 1.0025).
    """
    sid = writers.create_paper_session(engine, name=name, config_hash="abcd", config_json="{}")
    base_ts = datetime(2026, 5, 1, 16, 0, tzinfo=UTC)
    for i in range(n_orders):
        writers.write_paper_order(
            engine,
            session_id=sid,
            ts=base_ts + timedelta(days=i),
            symbol=f"SYM{i}",
            side="buy",
            qty=10.0,
            target_capital=2000.0,
            entry_price_hint=200.0,
            filled_qty=10.0,
            filled_avg_price=200.5,
            broker_status="filled",
            broker_order_id=f"oid-{i}",
            slippage_bps=25.0,
            fees=0.0,
            rationale_json='{"reason": "smoke"}',
        )

    eq = equity_path or [100_000.0, 100_500.0, 101_000.0, 100_800.0, 102_000.0]
    for i, e in enumerate(eq):
        writers.snapshot_paper_equity(
            engine,
            session_id=sid,
            ts=base_ts + timedelta(days=i),
            cash=10_000.0,
            positions_value=e - 10_000.0,
            equity=e,
            n_positions=20,
        )
    return sid


# ---------------------------------------------------------------------------
# bloasis paper sessions — list
# ---------------------------------------------------------------------------


def test_paper_sessions_lists_all(db_path: Path) -> None:
    engine = get_engine(db_path)
    _seed_session(engine, "sess-A", n_orders=2)
    _seed_session(engine, "sess-B", n_orders=5)

    res = runner.invoke(app, ["paper", "sessions"])
    assert res.exit_code == 0, res.output
    assert "sess-A" in res.output
    assert "sess-B" in res.output
    # Order counts visible
    assert "2" in res.output and "5" in res.output


def test_paper_sessions_empty_db(db_path: Path) -> None:
    res = runner.invoke(app, ["paper", "sessions"])
    assert res.exit_code == 0, res.output
    assert "no" in res.output.lower() or "0 sessions" in res.output.lower()


# ---------------------------------------------------------------------------
# bloasis paper show <session> — detail
# ---------------------------------------------------------------------------


def test_paper_show_renders_session_details(db_path: Path) -> None:
    engine = get_engine(db_path)
    _seed_session(engine, "detail-test")

    res = runner.invoke(app, ["paper", "show", "detail-test"])
    assert res.exit_code == 0, res.output
    assert "detail-test" in res.output
    # Equity start (100k) and end (102k) should appear in the summary
    assert "100,000" in res.output or "100000" in res.output
    assert "102,000" in res.output or "102000" in res.output
    # Total return = (102k - 100k) / 100k = 2.00%
    assert "2.00" in res.output or "+2.0" in res.output


def test_paper_show_unknown_session(db_path: Path) -> None:
    res = runner.invoke(app, ["paper", "show", "nope"])
    assert res.exit_code != 0
    assert "not found" in res.output.lower() or "no" in res.output.lower()


# ---------------------------------------------------------------------------
# bloasis paper entry-gap <session> — signal-close → fill-open drift
# ---------------------------------------------------------------------------


def test_paper_entry_gap_summarizes_drift(db_path: Path) -> None:
    engine = get_engine(db_path)
    _seed_session(engine, "gap-test", n_orders=4)

    res = runner.invoke(app, ["paper", "entry-gap", "gap-test"])
    assert res.exit_code == 0, res.output
    # Median drift across 4 orders all at 25 bps = 25 bps
    assert "25" in res.output  # bps value should appear
    assert "gap-test" in res.output


def test_paper_entry_gap_no_filled_orders(db_path: Path) -> None:
    engine = get_engine(db_path)
    _seed_session(engine, "empty-gap", n_orders=0)

    res = runner.invoke(app, ["paper", "entry-gap", "empty-gap"])
    # Either a clean "no fills" message or exit with code != 0 — both acceptable.
    assert res.exit_code == 0 or "no" in res.output.lower()


# ---------------------------------------------------------------------------
# bloasis paper close <session>
# ---------------------------------------------------------------------------


def test_paper_close_marks_session_closed(db_path: Path) -> None:
    engine = get_engine(db_path)
    sid = _seed_session(engine, "close-me")

    res = runner.invoke(app, ["paper", "close", "close-me"])
    assert res.exit_code == 0, res.output

    with engine.connect() as conn:
        row = conn.execute(
            select(paper_sessions).where(paper_sessions.c.session_id == sid)
        ).fetchone()
    assert row is not None
    assert row.status == "closed"
    assert row.ended_at is not None


def test_paper_close_idempotent(db_path: Path) -> None:
    engine = get_engine(db_path)
    sid = _seed_session(engine, "close-twice")

    res1 = runner.invoke(app, ["paper", "close", "close-twice"])
    res2 = runner.invoke(app, ["paper", "close", "close-twice"])
    assert res1.exit_code == 0
    assert res2.exit_code == 0  # closing an already-closed session is fine

    with engine.connect() as conn:
        rows = conn.execute(
            select(paper_sessions).where(paper_sessions.c.session_id == sid)
        ).fetchall()
    assert len(rows) == 1  # no duplicate
