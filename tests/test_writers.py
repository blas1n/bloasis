"""Round-trip tests for `bloasis.storage.writers` — backtest run lifecycle."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from bloasis.backtest.portfolio import Fill
from bloasis.backtest.result import BacktestResult, FoldResult
from bloasis.scoring.rationale import FactorContribution, Rationale
from bloasis.storage import (
    backtest_runs,
    create_all,
    equity_curve,
    get_engine,
    trades,
    writers,
)


def _fold(idx: int, *, alpha: float = 0.05, sharpe: float = 1.0) -> FoldResult:
    return FoldResult(
        fold_index=idx,
        train_start=date(2023, 1, 1),
        train_end=date(2023, 6, 30),
        test_start=date(2023, 7, 1),
        test_end=date(2023, 12, 31),
        final_equity=110_000.0,
        spy_final_equity=105_000.0,
        total_return=0.10,
        spy_total_return=0.05,
        annualized_return=0.20,
        annualized_alpha=alpha,
        sharpe=sharpe,
        spy_sharpe=0.8,
        sortino=1.2,
        max_drawdown=-0.10,
        spy_max_drawdown=-0.15,
        max_dd_ratio_to_spy=0.66,
        win_rate=0.55,
        n_trades=20,
        months_beating_spy=4,
        months_total=6,
        equity_curve=pd.Series([100.0, 110.0]),
    )


def _result(run_id: int) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        config_hash="abcd1234",
        start_date=date(2023, 7, 1),
        end_date=date(2023, 12, 31),
        initial_capital=100_000.0,
        fold_results=[_fold(0), _fold(1, alpha=0.07, sharpe=1.2)],
        median_alpha_annualized=0.06,
        median_sharpe_vs_spy=1.1,
        median_max_dd_ratio_to_spy=0.7,
        median_total_return=0.10,
        median_spy_total_return=0.05,
        median_win_rate=0.55,
        median_months_beating_spy_pct=0.66,
        n_folds=2,
        n_trades_total=40,
        passed_acceptance=True,
        acceptance_reasons=("PASS alpha", "PASS sharpe"),
    )


def test_create_backtest_run_returns_int_id(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name="r1",
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
        initial_capital=100_000.0,
    )
    assert isinstance(run_id, int)
    assert run_id > 0


def test_create_backtest_run_writes_running_status(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name="r1",
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
        initial_capital=10_000.0,
    )
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.run_id == run_id)).first()
    assert row is not None
    assert row.status == "running"
    assert row.user_id == 0
    assert row.config_hash == "abc"
    assert row.initial_capital == 10_000.0


def test_finalize_backtest_run_writes_metrics(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name="r",
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2023, 7, 1, tzinfo=UTC),
        end_date=datetime(2023, 12, 31, tzinfo=UTC),
        initial_capital=100_000.0,
    )
    writers.finalize_backtest_run(engine, run_id, _result(run_id))

    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.run_id == run_id)).first()
    assert row is not None
    assert row.status == "completed"
    assert row.alpha_vs_spy == 0.06
    assert row.n_trades == 40
    assert row.final_equity == 110_000.0  # last fold
    assert row.finished_at is not None
    # Acceptance persisted (PR7 polish).
    assert row.passed_acceptance is True
    assert row.acceptance_reasons_json is not None
    import json as _json

    reasons = _json.loads(row.acceptance_reasons_json)
    assert reasons == ["PASS alpha", "PASS sharpe"]


def test_finalize_persists_failed_acceptance(tmp_db_path: Path) -> None:
    """A run with passed_acceptance=False should be queryable as such — the
    `bloasis trade live` gate refuses to promote runs where this is not True.
    """
    from dataclasses import replace

    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name="r",
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2023, 7, 1, tzinfo=UTC),
        end_date=datetime(2023, 12, 31, tzinfo=UTC),
        initial_capital=100_000.0,
    )
    failed = replace(
        _result(run_id),
        passed_acceptance=False,
        acceptance_reasons=("FAIL alpha < 0", "PASS sharpe"),
    )
    writers.finalize_backtest_run(engine, run_id, failed)
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.run_id == run_id)).first()
    assert row is not None
    assert row.passed_acceptance is False
    import json as _json

    assert _json.loads(row.acceptance_reasons_json)[0].startswith("FAIL")


def test_fail_backtest_run_marks_failed(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name=None,
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
        initial_capital=10_000.0,
    )
    writers.fail_backtest_run(engine, run_id, "boom" * 500)
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.run_id == run_id)).first()
    assert row is not None
    assert row.status == "failed"
    # Truncated to 1000 chars.
    assert row.error_message is not None
    assert len(row.error_message) <= 1000


def test_write_equity_curve_inserts_rows(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name=None,
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
        initial_capital=10_000.0,
    )
    rows = [
        {
            "timestamp": datetime(2024, 1, d, tzinfo=UTC),
            "cash": 1000 + d,
            "invested": 100 * d,
            "total_equity": 10_000 + d,
        }
        for d in (1, 2, 3)
    ]
    writers.write_equity_curve(engine, run_id, rows)
    with engine.connect() as conn:
        out = conn.execute(select(equity_curve).where(equity_curve.c.run_id == run_id)).fetchall()
    assert len(out) == 3


def test_write_equity_curve_no_op_on_empty(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    # Should not raise even without an existing run.
    writers.write_equity_curve(engine, run_id=999, rows=[])


def test_write_trade_serializes_rationale(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    run_id = writers.create_backtest_run(
        engine,
        name=None,
        config_hash="abc",
        config_json="{}",
        scorer_type="rule",
        feature_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
        initial_capital=10_000.0,
    )
    fill = Fill(
        timestamp=datetime(2024, 2, 1, tzinfo=UTC),
        symbol="AAPL",
        side="buy",
        quantity=10.0,
        price=150.0,
        fees=0.5,
        slippage_bps=2.0,
        realized_pnl=0.0,
    )
    rationale = Rationale(
        contributions=(
            FactorContribution(
                name="momentum_z",
                composite_score=0.7,
                weight=0.7,
                contribution=0.49,
            ),
        ),
        triggers=("trend up",),
        risks=(),
    )
    writers.write_trade(engine, run_id, fill, rationale)
    with engine.connect() as conn:
        row = conn.execute(select(trades).where(trades.c.run_id == run_id)).first()
    assert row is not None
    assert row.symbol == "AAPL"
    assert row.side == "buy"
    assert row.rationale_json is not None
    assert "momentum_z" in row.rationale_json
