"""Tests for `bloasis.backtest.grid.run_grid` execution."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bloasis.backtest.grid import (
    Axis,
    GridSpec,
    apply_overrides,
    run_grid,
)
from bloasis.backtest.result import BacktestResult
from bloasis.config import StrategyConfig


@pytest.fixture
def base_cfg() -> StrategyConfig:
    return StrategyConfig()


@pytest.fixture
def fake_data() -> object:
    # Backtester is mocked, so the data sentinel just needs to be an object.
    return object()


def _spec(*axes: Axis) -> GridSpec:
    return GridSpec(
        name="t",
        base_config_path=Path("base.yaml"),
        walk_forward={
            "start": date(2022, 1, 1),
            "end": date(2023, 1, 1),
            "train_days": 90,
            "test_days": 30,
            "step_days": 30,
        },
        universe="sp500",
        symbols=None,
        axes=axes,
    )


def _fake_result() -> BacktestResult:
    """Minimal fake result for runner tests — avoids reconstructing full schema."""
    result = MagicMock(spec=BacktestResult)
    result.median_alpha_annualized = 0.04
    result.median_sharpe_vs_spy = 2.0
    result.median_max_dd_ratio_to_spy = 0.6
    result.n_trades_total = 5
    result.passed_acceptance = True
    result.config_hash = "abc123"
    return result


def test_run_grid_invokes_backtester_per_combination(
    base_cfg: StrategyConfig, fake_data: object
) -> None:
    spec = _spec(
        Axis(path="scorer.edgar_rolling_window", values=(1, 2, 3)),
        Axis(path="signal.rebalance_days", values=(1, 21)),
    )

    factory_calls: list[tuple[StrategyConfig, object]] = []
    run_calls: list[tuple[date, date]] = []

    def factory(cfg: StrategyConfig, data: object) -> object:
        factory_calls.append((cfg, data))
        bt = MagicMock()

        def _run(start: date, end: date, **_: object) -> BacktestResult:
            run_calls.append((start, end))
            return _fake_result()

        bt.run.side_effect = _run
        return bt

    results = run_grid(
        spec,
        base_cfg,
        fake_data,
        backtester_factory=factory,
    )

    assert len(results) == 6
    assert len(factory_calls) == 6
    assert len(run_calls) == 6
    # Walk-forward window propagates to .run()
    assert all(call == (date(2022, 1, 1), date(2023, 1, 1)) for call in run_calls)
    # Each combination gets a distinct config (rolling_window applied)
    rolling_windows = {cfg.scorer.edgar_rolling_window for cfg, _ in factory_calls}
    assert rolling_windows == {1, 2, 3}


def test_run_grid_shares_backtest_data_across_combinations(
    base_cfg: StrategyConfig, fake_data: object
) -> None:
    spec = _spec(Axis(path="scorer.edgar_rolling_window", values=(1, 2)))

    seen_data_ids: list[int] = []

    def factory(cfg: StrategyConfig, data: object) -> object:
        seen_data_ids.append(id(data))
        bt = MagicMock()
        bt.run.return_value = _fake_result()
        return bt

    run_grid(spec, base_cfg, fake_data, backtester_factory=factory)

    assert len(seen_data_ids) == 2
    assert len(set(seen_data_ids)) == 1, "BacktestData must be shared across combos"


def test_run_grid_attaches_run_name_and_overrides(
    base_cfg: StrategyConfig, fake_data: object
) -> None:
    spec = _spec(Axis(path="scorer.edgar_rolling_window", values=(2,)))

    def factory(cfg: StrategyConfig, data: object) -> object:
        bt = MagicMock()
        bt.run.return_value = _fake_result()
        return bt

    results = run_grid(spec, base_cfg, fake_data, backtester_factory=factory)

    assert results[0].run_name == "t#edgar_rolling_window=2"
    assert results[0].overrides == {"scorer.edgar_rolling_window": 2}


def test_run_grid_continues_on_single_failure(base_cfg: StrategyConfig, fake_data: object) -> None:
    spec = _spec(Axis(path="scorer.edgar_rolling_window", values=(1, 2, 3)))

    invocations = {"n": 0}

    def factory(cfg: StrategyConfig, data: object) -> object:
        bt = MagicMock()

        def _run(*a: object, **k: object) -> BacktestResult:
            invocations["n"] += 1
            if invocations["n"] == 2:
                raise RuntimeError("boom")
            return _fake_result()

        bt.run.side_effect = _run
        return bt

    results = run_grid(spec, base_cfg, fake_data, backtester_factory=factory)

    assert len(results) == 3
    assert results[0].error is None
    assert results[1].error is not None and "boom" in results[1].error
    assert results[1].result is None
    assert results[2].error is None


def test_apply_overrides_sets_dotted_path(base_cfg: StrategyConfig) -> None:
    cfg = apply_overrides(base_cfg, {"scorer.edgar_rolling_window": 4, "signal.rebalance_days": 21})

    assert cfg.scorer.edgar_rolling_window == 4
    assert cfg.signal.rebalance_days == 21
    # original untouched
    assert base_cfg.scorer.edgar_rolling_window != 4 or base_cfg.signal.rebalance_days != 21
