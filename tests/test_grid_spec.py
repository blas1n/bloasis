"""Tests for `bloasis.backtest.grid` spec parsing + combination expansion."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bloasis.backtest.grid import (
    Axis,
    GridSpec,
    expand_combinations,
    format_run_name,
    load_grid_spec,
)


def _write_spec(tmp_path: Path, payload: dict, name: str = "spec.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload))
    return path


# ---------------------------------------------------------------------------
# load_grid_spec
# ---------------------------------------------------------------------------


def test_load_grid_spec_minimal(tmp_path: Path) -> None:
    payload = {
        "name": "pr21-test",
        "base": "configs/edgar-rolling2.yaml",
        "walk_forward": {
            "start": "2022-07-01",
            "end": "2024-10-17",
            "train_days": 365,
            "test_days": 120,
            "step_days": 120,
        },
        "universe": "sp500",
        "axes": [
            {"path": "scorer.edgar_rolling_window", "values": [1, 2, 3]},
            {"path": "signal.rebalance_days", "values": [1, 21]},
        ],
    }
    path = _write_spec(tmp_path, payload)

    spec = load_grid_spec(path)

    assert spec.name == "pr21-test"
    assert spec.base_config_path == Path("configs/edgar-rolling2.yaml")
    assert spec.walk_forward["train_days"] == 365
    assert spec.universe == "sp500"
    assert len(spec.axes) == 2
    assert spec.axes[0].path == "scorer.edgar_rolling_window"
    assert spec.axes[0].values == (1, 2, 3)


def test_load_grid_spec_explicit_symbols(tmp_path: Path) -> None:
    payload = {
        "name": "smoke",
        "base": "configs/edgar-rolling2.yaml",
        "walk_forward": {
            "start": "2022-01-01",
            "end": "2023-01-01",
            "train_days": 90,
            "test_days": 30,
            "step_days": 30,
        },
        "symbols": ["AAPL", "MSFT"],
        "axes": [],
    }
    path = _write_spec(tmp_path, payload)

    spec = load_grid_spec(path)

    assert spec.universe is None
    assert spec.symbols == ["AAPL", "MSFT"]
    assert spec.axes == ()


def test_load_grid_spec_missing_name_raises(tmp_path: Path) -> None:
    payload = {
        "base": "configs/edgar-rolling2.yaml",
        "walk_forward": {
            "start": "2022-07-01",
            "end": "2024-10-17",
            "train_days": 365,
            "test_days": 120,
            "step_days": 120,
        },
        "universe": "sp500",
        "axes": [],
    }
    path = _write_spec(tmp_path, payload)

    with pytest.raises(ValueError, match="name"):
        load_grid_spec(path)


def test_load_grid_spec_missing_universe_and_symbols_raises(tmp_path: Path) -> None:
    payload = {
        "name": "x",
        "base": "configs/edgar-rolling2.yaml",
        "walk_forward": {
            "start": "2022-07-01",
            "end": "2024-10-17",
            "train_days": 365,
            "test_days": 120,
            "step_days": 120,
        },
        "axes": [],
    }
    path = _write_spec(tmp_path, payload)

    with pytest.raises(ValueError, match="universe"):
        load_grid_spec(path)


def test_load_grid_spec_axis_must_have_values(tmp_path: Path) -> None:
    payload = {
        "name": "x",
        "base": "configs/edgar-rolling2.yaml",
        "walk_forward": {
            "start": "2022-07-01",
            "end": "2024-10-17",
            "train_days": 365,
            "test_days": 120,
            "step_days": 120,
        },
        "universe": "sp500",
        "axes": [{"path": "scorer.foo", "values": []}],
    }
    path = _write_spec(tmp_path, payload)

    with pytest.raises(ValueError, match="values"):
        load_grid_spec(path)


def test_load_grid_spec_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_grid_spec(tmp_path / "missing.yaml")


# ---------------------------------------------------------------------------
# expand_combinations
# ---------------------------------------------------------------------------


def _spec(*axes: Axis) -> GridSpec:
    return GridSpec(
        name="x",
        base_config_path=Path("base.yaml"),
        walk_forward={
            "start": "2022-07-01",
            "end": "2024-10-17",
            "train_days": 365,
            "test_days": 120,
            "step_days": 120,
        },
        universe="sp500",
        symbols=None,
        axes=axes,
    )


def test_expand_combinations_cartesian_product() -> None:
    spec = _spec(
        Axis(path="a.x", values=(1, 2, 3)),
        Axis(path="b.y", values=(True, False)),
    )

    combos = expand_combinations(spec)

    assert len(combos) == 6
    assert {"a.x": 1, "b.y": True} in combos
    assert {"a.x": 3, "b.y": False} in combos


def test_expand_combinations_empty_axes_yields_single_empty() -> None:
    spec = _spec()

    combos = expand_combinations(spec)

    assert combos == [{}]


def test_expand_combinations_single_axis() -> None:
    spec = _spec(Axis(path="a.x", values=(1, 2)))

    combos = expand_combinations(spec)

    assert combos == [{"a.x": 1}, {"a.x": 2}]


# ---------------------------------------------------------------------------
# format_run_name
# ---------------------------------------------------------------------------


def test_format_run_name_short_keys() -> None:
    name = format_run_name("pr21", {"scorer.edgar_rolling_window": 2, "signal.rebalance_days": 21})
    assert name == "pr21#edgar_rolling_window=2,rebalance_days=21"


def test_format_run_name_bool_and_float() -> None:
    name = format_run_name("g", {"a.b.c": True, "x.y": 0.15})
    assert name == "g#c=True,y=0.15"


def test_format_run_name_no_overrides() -> None:
    name = format_run_name("g", {})
    assert name == "g"
