"""Persistence helpers for backtest runs.

Wrap the SQLAlchemy core inserts so the engine doesn't sprinkle SQL all
over the place. Each write is a small transaction; the backtester calls
these inline. For ~100 trading days × ~500 symbols this is fine; if the
volume grows, batch via `execute_many` here without the engine caring.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import insert, update

from bloasis.backtest.portfolio import Fill
from bloasis.backtest.result import BacktestResult
from bloasis.scoring.rationale import Rationale
from bloasis.storage import backtest_runs, equity_curve, trades

if TYPE_CHECKING:
    from sqlalchemy import Engine

USER_ID_DEFAULT = 0  # single-user CLI; column kept for future multi-user


def create_backtest_run(
    engine: Engine,
    *,
    name: str | None,
    config_hash: str,
    config_json: str,
    scorer_type: str,
    feature_version: int,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    git_sha: str | None = None,
) -> int:
    """Insert a `running` backtest_runs row and return its run_id."""
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        result = conn.execute(
            insert(backtest_runs)
            .values(
                user_id=USER_ID_DEFAULT,
                name=name,
                config_hash=config_hash,
                config_json=config_json,
                scorer_type=scorer_type,
                feature_version=feature_version,
                git_sha=git_sha,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                status="running",
                started_at=now,
            )
            .returning(backtest_runs.c.run_id)
        )
        row = result.fetchone()
        assert row is not None
        return int(row[0])


def finalize_backtest_run(
    engine: Engine,
    run_id: int,
    result: BacktestResult,
) -> None:
    """Update the row with final metrics and status='completed'."""
    now = datetime.now(tz=UTC)
    final_equity = (
        result.fold_results[-1].final_equity if result.fold_results else result.initial_capital
    )
    reasons_json = json.dumps(list(result.acceptance_reasons))
    with engine.begin() as conn:
        conn.execute(
            update(backtest_runs)
            .where(backtest_runs.c.run_id == run_id)
            .values(
                final_equity=final_equity,
                total_return=result.median_total_return,
                annualized_return=_avg_annualized(result),
                sharpe=_avg_sharpe(result),
                max_drawdown=_avg_max_dd(result),
                win_rate=result.median_win_rate,
                n_trades=result.n_trades_total,
                alpha_vs_spy=result.median_alpha_annualized,
                passed_acceptance=result.passed_acceptance,
                acceptance_reasons_json=reasons_json,
                status="completed",
                finished_at=now,
            )
        )


def fail_backtest_run(engine: Engine, run_id: int, error_message: str) -> None:
    """Mark the run as failed."""
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            update(backtest_runs)
            .where(backtest_runs.c.run_id == run_id)
            .values(status="failed", finished_at=now, error_message=error_message[:1000])
        )


def write_equity_curve(
    engine: Engine,
    run_id: int,
    rows: list[dict[str, object]],
) -> None:
    """Bulk-insert equity_curve rows.

    `rows` is a list of dicts with keys timestamp/cash/invested/total_equity.
    """
    if not rows:
        return
    payload = [
        {
            "user_id": USER_ID_DEFAULT,
            "run_id": run_id,
            **r,
        }
        for r in rows
    ]
    with engine.begin() as conn:
        conn.execute(insert(equity_curve), payload)


def write_trade(
    engine: Engine,
    run_id: int,
    fill: Fill,
    rationale: Rationale | None,
    feature_ts: datetime | None = None,
) -> None:
    """Insert one trade row, optionally with a serialized rationale."""
    rationale_json = json.dumps(_serialize_rationale(rationale)) if rationale is not None else None
    with engine.begin() as conn:
        conn.execute(
            insert(trades).values(
                user_id=USER_ID_DEFAULT,
                run_id=run_id,
                timestamp=fill.timestamp,
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                slippage_bps=fill.slippage_bps,
                feature_ts=feature_ts,
                rationale_json=rationale_json,
                realized_pnl=fill.realized_pnl,
            )
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _serialize_rationale(rationale: Rationale) -> dict[str, object]:
    return {
        "contributions": [asdict(c) for c in rationale.contributions],
        "triggers": list(rationale.triggers),
        "risks": list(rationale.risks),
    }


def _avg_annualized(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.annualized_return for f in result.fold_results) / len(result.fold_results)


def _avg_sharpe(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.sharpe for f in result.fold_results) / len(result.fold_results)


def _avg_max_dd(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.max_drawdown for f in result.fold_results) / len(result.fold_results)
