"""CLI smoke tests for `bloasis runs {list,show,compare}`.

These commands only touch the local SQLite DB (no network), so we point
the CLI at a tmp DB via `BLOASIS_DB_PATH`, seed a couple of fake runs
through the public writer API, and assert the rendered output.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from bloasis.backtest.result import BacktestResult, FoldResult
from bloasis.cli import app
from bloasis.storage import create_all, get_engine, writers

runner = CliRunner()


def _fold(idx: int) -> FoldResult:
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
        annualized_alpha=0.05,
        sharpe=1.0,
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


def _result(run_id: int, *, passed: bool = True) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        config_hash="abcd1234",
        start_date=date(2023, 7, 1),
        end_date=date(2023, 12, 31),
        initial_capital=100_000.0,
        fold_results=[_fold(0), _fold(1)],
        median_alpha_annualized=0.06,
        median_sharpe_vs_spy=1.1,
        median_max_dd_ratio_to_spy=0.7,
        median_total_return=0.10,
        median_spy_total_return=0.05,
        median_win_rate=0.55,
        median_months_beating_spy_pct=0.66,
        n_folds=2,
        n_trades_total=40,
        passed_acceptance=passed,
        acceptance_reasons=(
            ("PASS alpha", "PASS sharpe") if passed else ("FAIL alpha < 0", "PASS sharpe")
        ),
    )


@pytest.fixture
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A DB with two finalized runs at $tmp_path/test.db, exposed via env."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db_path))
    engine = get_engine(db_path)
    create_all(engine)

    for label, passed in [("fail-r", False), ("pass-r", True)]:
        run_id = writers.create_backtest_run(
            engine,
            name=label,
            config_hash="abcd1234" if passed else "deadbeef",
            config_json="{}",
            scorer_type="rule",
            feature_version=1,
            start_date=datetime(2023, 7, 1, tzinfo=UTC),
            end_date=datetime(2023, 12, 31, tzinfo=UTC),
            initial_capital=100_000.0,
        )
        writers.finalize_backtest_run(engine, run_id, replace(_result(run_id, passed=passed)))
    return db_path


def test_runs_list_renders_both_runs(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "list"])
    assert result.exit_code == 0, result.output
    assert "pass-r" in result.output
    assert "fail-r" in result.output


def test_runs_show_renders_acceptance_pass(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "show", "2"])
    assert result.exit_code == 0, result.output
    assert "passed_acceptance" in result.output
    assert "YES" in result.output
    assert "PASS" in result.output
    assert "alpha" in result.output


def test_runs_show_renders_acceptance_fail(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "show", "1"])
    assert result.exit_code == 0, result.output
    assert "passed_acceptance" in result.output
    assert "NO" in result.output
    assert "FAIL" in result.output


def test_runs_show_missing_run_nonzero(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "show", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_runs_compare_two_runs(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "compare", "1", "2"])
    assert result.exit_code == 0, result.output
    assert "passed" in result.output
    assert "config_hash" in result.output


def test_runs_compare_missing_run_nonzero(seeded_db: Path) -> None:
    result = runner.invoke(app, ["runs", "compare", "1", "9999"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# trade live gate — refuses early without touching Alpaca
# ---------------------------------------------------------------------------


def test_trade_live_refuses_without_live_key(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALPACA_LIVE_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "trade",
            "live",
            "--from-run",
            "2",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "--i-am-sure",
        ],
    )
    assert result.exit_code != 0
    assert "ALPACA_LIVE_API_KEY" in result.output


def test_trade_live_refuses_failed_acceptance(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "fake")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "fake")
    result = runner.invoke(
        app,
        [
            "trade",
            "live",
            "--from-run",
            "1",  # fail-r
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "--i-am-sure",
        ],
    )
    assert result.exit_code != 0
    assert "did not pass acceptance" in result.output


def test_trade_live_refuses_missing_run(seeded_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "fake")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "fake")
    result = runner.invoke(
        app,
        [
            "trade",
            "live",
            "--from-run",
            "9999",
            "-s",
            "AAPL",
            "-s",
            "MSFT",
            "--i-am-sure",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_trade_dry_run_requires_two_symbols(seeded_db: Path) -> None:
    result = runner.invoke(app, ["trade", "dry-run", "-s", "AAPL"])
    assert result.exit_code != 0
    assert "at least 2" in result.output


def test_trade_paper_requires_two_symbols(seeded_db: Path) -> None:
    result = runner.invoke(app, ["trade", "paper", "-s", "AAPL"])
    assert result.exit_code != 0
    assert "at least 2" in result.output


def test_trade_live_requires_two_symbols(seeded_db: Path) -> None:
    result = runner.invoke(app, ["trade", "live", "--from-run", "2", "-s", "AAPL", "--i-am-sure"])
    assert result.exit_code != 0
    assert "at least 2" in result.output
