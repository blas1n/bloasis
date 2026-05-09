"""CLI smoke tests for `bloasis grid run` and `bloasis grid show`.

Mocks `prefetch_backtest_data` and `Backtester` so no network or yfinance
calls are made. Verifies the runner persists per-combination rows to the
runs table and that `grid show` filters by name prefix.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from bloasis.backtest.result import BacktestData, BacktestResult, FoldResult
from bloasis.cli import app
from bloasis.storage import create_all, get_engine, writers

runner = CliRunner()


def _fold(idx: int, *, sharpe: float = 1.0) -> FoldResult:
    return FoldResult(
        fold_index=idx,
        train_start=date(2022, 1, 1),
        train_end=date(2022, 4, 1),
        test_start=date(2022, 4, 2),
        test_end=date(2022, 5, 2),
        final_equity=110_000.0,
        spy_final_equity=105_000.0,
        total_return=0.10,
        spy_total_return=0.05,
        annualized_return=0.20,
        annualized_alpha=0.05,
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


def _result(run_id: int, sharpe: float, alpha: float) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        config_hash="abcd1234",
        start_date=date(2022, 1, 1),
        end_date=date(2023, 1, 1),
        initial_capital=10_000.0,
        fold_results=[_fold(0, sharpe=sharpe)],
        median_alpha_annualized=alpha,
        median_sharpe_vs_spy=sharpe,
        median_max_dd_ratio_to_spy=0.6,
        median_total_return=0.10,
        median_spy_total_return=0.05,
        median_win_rate=0.55,
        median_months_beating_spy_pct=0.66,
        n_folds=1,
        n_trades_total=10,
        passed_acceptance=True,
        acceptance_reasons=("PASS",),
    )


@pytest.fixture
def grid_spec(tmp_path: Path) -> Path:
    payload = {
        "name": "smoke-grid",
        "base": "configs/baseline.yaml",
        "walk_forward": {
            "start": "2022-01-01",
            "end": "2023-01-01",
            "train_days": 90,
            "test_days": 30,
            "step_days": 30,
        },
        "symbols": ["AAPL", "MSFT"],
        "axes": [
            {"path": "scorer.entry_threshold", "values": [0.6, 0.7]},
        ],
    }
    p = tmp_path / "smoke.yaml"
    p.write_text(yaml.safe_dump(payload))
    return p


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "grid.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(p))
    create_all(get_engine(p))
    return p


def _fake_backtest_data() -> BacktestData:
    return BacktestData(
        symbols=["AAPL", "MSFT"],
        bars={},
        vix_series=pd.Series(dtype=float),
        spy_close_series=pd.Series(dtype=float),
    )


def test_grid_run_creates_one_row_per_combination(
    grid_spec: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sharpes = iter([1.5, 0.9])

    def fake_prefetch(*a: object, **k: object) -> BacktestData:
        return _fake_backtest_data()

    def fake_backtester(cfg: object, data: object, **k: object) -> object:
        bt = MagicMock()

        def _run(start: date, end: date, *, run_id: int = 0, **_: object) -> BacktestResult:
            return _result(run_id, sharpe=next(sharpes), alpha=0.04)

        bt.run.side_effect = _run
        return bt

    monkeypatch.setattr("bloasis.backtest.prefetch.prefetch_backtest_data", fake_prefetch)
    monkeypatch.setattr("bloasis.backtest.grid.Backtester", fake_backtester)

    res = runner.invoke(app, ["grid", "run", str(grid_spec)])

    assert res.exit_code == 0, res.output
    # Both combo names should have been created
    from sqlalchemy import select

    from bloasis.storage import backtest_runs as br_table

    engine = get_engine(db_path)
    with engine.connect() as conn:
        names = [
            row.name
            for row in conn.execute(select(br_table.c.name).order_by(br_table.c.run_id)).fetchall()
        ]
    assert names == ["smoke-grid#entry_threshold=0.6", "smoke-grid#entry_threshold=0.7"]


def test_grid_show_filters_by_grid_name(db_path: Path) -> None:
    engine = get_engine(db_path)
    for label, sharpe in [
        ("smoke-grid#entry_threshold=0.6", 1.5),
        ("smoke-grid#entry_threshold=0.7", 0.9),
        ("other-grid#x=1", 2.0),
    ]:
        run_id = writers.create_backtest_run(
            engine,
            name=label,
            config_hash="abcd",
            config_json="{}",
            scorer_type="rule",
            feature_version=2,
            start_date=datetime(2022, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 1, 1, tzinfo=UTC),
            initial_capital=10_000.0,
        )
        writers.finalize_backtest_run(engine, run_id, replace(_result(run_id, sharpe, 0.04)))

    res = runner.invoke(app, ["grid", "show", "smoke-grid"])

    assert res.exit_code == 0, res.output
    assert "entry_threshold=0.6" in res.output
    assert "entry_threshold=0.7" in res.output
    assert "other-grid" not in res.output
    # Higher-sharpe row should appear above the lower one (sorted desc).
    idx_high = res.output.index("entry_threshold=0.6")
    idx_low = res.output.index("entry_threshold=0.7")
    assert idx_high < idx_low


def test_grid_show_missing_grid_name_errors(db_path: Path) -> None:
    res = runner.invoke(app, ["grid", "show", "nonexistent-grid"])

    assert res.exit_code != 0
    assert "no runs" in res.output.lower()


# ---------------------------------------------------------------------------
# PR42 ergonomics fixes
# ---------------------------------------------------------------------------


def test_grid_run_prints_failed_combo_traceback_to_stderr(
    grid_spec: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed combos should surface their traceback to the user, not bury it
    in GridRunResult.error only."""

    def fake_prefetch(*a: object, **k: object) -> BacktestData:
        return _fake_backtest_data()

    def fake_backtester(cfg: object, data: object, **k: object) -> object:
        bt = MagicMock()

        def _run(*a: object, **k: object) -> BacktestResult:
            raise RuntimeError("synthetic-explosion-marker")

        bt.run.side_effect = _run
        return bt

    monkeypatch.setattr("bloasis.backtest.prefetch.prefetch_backtest_data", fake_prefetch)
    monkeypatch.setattr("bloasis.backtest.grid.Backtester", fake_backtester)

    # CliRunner with mix_stderr=False to separate stdout and stderr.
    runner_split = CliRunner(mix_stderr=False)
    res = runner_split.invoke(app, ["grid", "run", str(grid_spec)])

    assert res.exit_code == 0  # grid run continues past combo failures
    # The synthetic error message MUST appear somewhere visible — either
    # stderr (preferred) or stdout. Currently it's hidden in memory only.
    combined = (res.output or "") + (res.stderr or "")
    assert "synthetic-explosion-marker" in combined, combined


def test_grid_run_summary_n_pass_matches_actual_passed(
    grid_spec: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary line `N passed acceptance` must equal the number of combos
    whose backtest result has passed_acceptance=True AND no error."""

    # 1 combo passes acceptance, 1 fails by raising.
    call_count = {"n": 0}

    def fake_prefetch(*a: object, **k: object) -> BacktestData:
        return _fake_backtest_data()

    def fake_backtester(cfg: object, data: object, **k: object) -> object:
        bt = MagicMock()

        def _run(*a: object, **k: object) -> BacktestResult:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("expected-failure")
            return _result(0, sharpe=1.5, alpha=0.04)

        bt.run.side_effect = _run
        return bt

    monkeypatch.setattr("bloasis.backtest.prefetch.prefetch_backtest_data", fake_prefetch)
    monkeypatch.setattr("bloasis.backtest.grid.Backtester", fake_backtester)

    res = runner.invoke(app, ["grid", "run", str(grid_spec)])

    assert res.exit_code == 0, res.output
    # spec has 2 combos, 1 fails → summary should say "1 completed, 1 passed"
    # (n_pass = 1, not 2)
    import re

    m = re.search(r"(\d+)/2 completed,\s*(\d+) passed", res.output)
    assert m, f"summary line missing: {res.output}"
    n_completed, n_pass = int(m.group(1)), int(m.group(2))
    assert n_completed == 1, res.output
    assert n_pass == 1, res.output


def test_grid_show_sort_by_alpha(db_path: Path) -> None:
    """`bloasis grid show <name> --sort alpha` orders by median_alpha_annualized
    desc — so the row with highest alpha appears first regardless of sharpe."""
    engine = get_engine(db_path)
    # Two runs: run A has higher alpha, lower sharpe; run B has lower alpha,
    # higher sharpe. Default --sort sharpe puts B first; --sort alpha puts A first.
    for label, sharpe, alpha in [
        ("alpha-grid#cell=A", 1.0, 0.05),
        ("alpha-grid#cell=B", 1.5, 0.01),
    ]:
        run_id = writers.create_backtest_run(
            engine,
            name=label,
            config_hash="abcd",
            config_json="{}",
            scorer_type="rule",
            feature_version=2,
            start_date=datetime(2022, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 1, 1, tzinfo=UTC),
            initial_capital=10_000.0,
        )
        writers.finalize_backtest_run(engine, run_id, replace(_result(run_id, sharpe, alpha)))

    res = runner.invoke(app, ["grid", "show", "alpha-grid", "--sort", "alpha"])

    assert res.exit_code == 0, res.output
    idx_a = res.output.index("cell=A")
    idx_b = res.output.index("cell=B")
    assert idx_a < idx_b, f"--sort alpha should put A (α=0.05) before B (α=0.01)\n{res.output}"


def test_grid_show_sort_default_is_sharpe(db_path: Path) -> None:
    """Default sort remains sharpe (don't break existing users)."""
    engine = get_engine(db_path)
    for label, sharpe, alpha in [
        ("def-grid#cell=A", 1.0, 0.05),
        ("def-grid#cell=B", 1.5, 0.01),
    ]:
        run_id = writers.create_backtest_run(
            engine,
            name=label,
            config_hash="abcd",
            config_json="{}",
            scorer_type="rule",
            feature_version=2,
            start_date=datetime(2022, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 1, 1, tzinfo=UTC),
            initial_capital=10_000.0,
        )
        writers.finalize_backtest_run(engine, run_id, replace(_result(run_id, sharpe, alpha)))

    res = runner.invoke(app, ["grid", "show", "def-grid"])

    assert res.exit_code == 0, res.output
    idx_a = res.output.index("cell=A")
    idx_b = res.output.index("cell=B")
    assert idx_b < idx_a, f"default sort sharpe should put B (sharpe=1.5) first\n{res.output}"


def test_grid_show_invalid_sort_rejected(db_path: Path) -> None:
    """Unknown sort key should error out cleanly, not silently default."""
    res = runner.invoke(app, ["grid", "show", "anygrid", "--sort", "wibble"])

    assert res.exit_code != 0
    assert "wibble" in res.output.lower() or "invalid" in res.output.lower()
