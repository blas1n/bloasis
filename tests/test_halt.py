"""Tests for `bloasis.runtime.halt` — live-trading halt-condition gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import insert

from bloasis.config import RiskConfig
from bloasis.runtime.halt import evaluate_halt
from bloasis.storage import (
    backtest_runs as br_table,
)
from bloasis.storage import (
    create_all,
    get_engine,
    trades,
)


def _seed_run(engine: object) -> int:
    """Insert a finished backtest_runs row so trades have a valid FK."""
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:  # type: ignore[attr-defined]
        result = conn.execute(
            insert(br_table)
            .values(
                user_id=0,
                config_hash="abc",
                config_json="{}",
                scorer_type="rule",
                feature_version=1,
                start_date=now - timedelta(days=400),
                end_date=now - timedelta(days=300),
                initial_capital=100_000.0,
                status="completed",
                started_at=now,
            )
            .returning(br_table.c.run_id)
        )
        run_id = int(result.scalar_one())
    return run_id


def _insert_live_trade(engine: object, *, ts: datetime, realized_pnl: float) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            insert(trades).values(
                user_id=0,
                run_id=None,
                timestamp=ts,
                symbol="AAPL",
                side="sell",
                quantity=1.0,
                price=100.0,
                fees=0.0,
                realized_pnl=realized_pnl,
            )
        )


def _insert_backtest_trade(
    engine: object, *, run_id: int, ts: datetime, realized_pnl: float
) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            insert(trades).values(
                user_id=0,
                run_id=run_id,
                timestamp=ts,
                symbol="AAPL",
                side="sell",
                quantity=1.0,
                price=100.0,
                fees=0.0,
                realized_pnl=realized_pnl,
            )
        )


def test_disabled_when_pct_zero(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    risk = RiskConfig(halt_drawdown_pct=0.0)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=datetime.now(tz=UTC))
    assert decision.should_halt is False
    assert "disabled" in decision.reason


def test_no_trades_means_no_halt(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    risk = RiskConfig(halt_drawdown_pct=0.10, halt_drawdown_lookback_days=30)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=datetime.now(tz=UTC))
    assert decision.should_halt is False
    assert decision.realized_pnl == 0.0
    assert decision.threshold == -10_000.0


def test_halt_trips_when_realized_below_floor(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(tz=UTC)
    _insert_live_trade(engine, ts=now - timedelta(days=2), realized_pnl=-12_000.0)

    risk = RiskConfig(halt_drawdown_pct=0.10, halt_drawdown_lookback_days=30)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now)
    assert decision.should_halt is True
    assert decision.realized_pnl == -12_000.0
    assert decision.threshold == -10_000.0
    assert "below halt floor" in decision.reason


def test_halt_does_not_trip_when_realized_above_floor(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(tz=UTC)
    _insert_live_trade(engine, ts=now - timedelta(days=2), realized_pnl=-5_000.0)

    risk = RiskConfig(halt_drawdown_pct=0.10, halt_drawdown_lookback_days=30)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now)
    assert decision.should_halt is False
    assert decision.realized_pnl == -5_000.0


def test_lookback_excludes_old_trades(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(tz=UTC)
    # Big loss 60 days ago — outside the 30-day window.
    _insert_live_trade(engine, ts=now - timedelta(days=60), realized_pnl=-50_000.0)
    # Small gain inside the window.
    _insert_live_trade(engine, ts=now - timedelta(days=5), realized_pnl=+1_000.0)

    risk = RiskConfig(halt_drawdown_pct=0.10, halt_drawdown_lookback_days=30)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now)
    assert decision.should_halt is False
    assert decision.realized_pnl == 1_000.0


def test_halt_ignores_backtest_trades(tmp_db_path: Path) -> None:
    """Trades with a non-NULL run_id belong to backtests and must not affect
    the live halt check."""
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = _seed_run(engine)
    now = datetime.now(tz=UTC)
    _insert_backtest_trade(
        engine, run_id=run_id, ts=now - timedelta(days=2), realized_pnl=-20_000.0
    )

    risk = RiskConfig(halt_drawdown_pct=0.10, halt_drawdown_lookback_days=30)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now)
    assert decision.should_halt is False
    assert decision.realized_pnl == 0.0


def test_threshold_scales_with_initial_capital(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    risk = RiskConfig(halt_drawdown_pct=0.05)  # 5%
    d50k = evaluate_halt(engine, risk, initial_capital=50_000.0, now=datetime.now(tz=UTC))
    d200k = evaluate_halt(engine, risk, initial_capital=200_000.0, now=datetime.now(tz=UTC))
    assert d50k.threshold == -2_500.0
    assert d200k.threshold == -10_000.0


def test_per_user_isolation(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(tz=UTC)
    # User 0 has a big loss; user 1 should be clean.
    _insert_live_trade(engine, ts=now - timedelta(days=1), realized_pnl=-50_000.0)

    risk = RiskConfig(halt_drawdown_pct=0.10)
    for_user_1 = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now, user_id=1)
    assert for_user_1.should_halt is False
    assert for_user_1.realized_pnl == 0.0


def test_null_realized_pnl_skipped(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(tz=UTC)
    # Open trade (no realized_pnl yet).
    with engine.begin() as conn:
        conn.execute(
            insert(trades).values(
                user_id=0,
                run_id=None,
                timestamp=now - timedelta(days=1),
                symbol="AAPL",
                side="buy",
                quantity=10.0,
                price=150.0,
                fees=0.0,
                realized_pnl=None,
            )
        )
    risk = RiskConfig(halt_drawdown_pct=0.10)
    decision = evaluate_halt(engine, risk, initial_capital=100_000.0, now=now)
    assert decision.should_halt is False
    assert decision.realized_pnl == 0.0
