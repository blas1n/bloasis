"""Combinatorial backtest grid runner.

Reads an axes spec YAML, takes the Cartesian product of axis values, and
runs one backtest per combination — sharing a single pre-fetched
``BacktestData`` panel across all runs so cold-cache cost is paid once.

Spec format::

    name: pr21-edgar-rolling
    base: configs/edgar-rolling2.yaml
    walk_forward:
      start: 2022-07-01
      end: 2024-10-17
      train_days: 365
      test_days: 120
      step_days: 120
    universe: sp500          # OR: symbols: [AAPL, MSFT]
    axes:
      - path: scorer.edgar_rolling_window
        values: [1, 2, 3, 5]
      - path: signal.rebalance_days
        values: [1, 5, 21, 42]

Out of scope (PR21):
- Parallel execution (sequential keeps SQLite simple).
- Bayesian / Optuna search — see ``docs/tune.md``.
"""

from __future__ import annotations

import itertools
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from bloasis.backtest.engine import Backtester
from bloasis.backtest.result import BacktestData, BacktestResult
from bloasis.config import StrategyConfig


@dataclass(frozen=True, slots=True)
class Axis:
    """One named search axis: a config path + the values to sweep."""

    path: str
    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class GridSpec:
    """Parsed axes spec.

    ``universe`` and ``symbols`` are mutually exclusive — exactly one is
    populated. ``walk_forward`` mirrors ``backtest()`` CLI options.
    """

    name: str
    base_config_path: Path
    walk_forward: dict[str, Any]
    universe: str | None
    symbols: list[str] | None
    axes: tuple[Axis, ...]

    def n_combinations(self) -> int:
        n = 1
        for ax in self.axes:
            n *= max(len(ax.values), 1)
        return n


@dataclass(slots=True)
class GridRunResult:
    """Outcome of a single combination's backtest."""

    run_name: str
    overrides: dict[str, Any]
    config: StrategyConfig
    run_id: int | None = None
    result: BacktestResult | None = None
    error: str | None = None


_REQUIRED_WF_KEYS = ("start", "end", "train_days", "test_days", "step_days")


def load_grid_spec(path: Path) -> GridSpec:
    """Parse a grid spec YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"grid spec not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"grid spec root must be a mapping, got {type(raw).__name__}")

    name = raw.get("name")
    if not name:
        raise ValueError("grid spec missing required 'name'")
    base = raw.get("base")
    if not base:
        raise ValueError("grid spec missing required 'base' (path to base StrategyConfig YAML)")
    wf = raw.get("walk_forward")
    if not isinstance(wf, dict):
        raise ValueError("grid spec missing required 'walk_forward' mapping")
    missing = [k for k in _REQUIRED_WF_KEYS if k not in wf]
    if missing:
        raise ValueError(f"walk_forward missing keys: {missing}")

    universe = raw.get("universe")
    symbols = raw.get("symbols")
    if not universe and not symbols:
        raise ValueError("grid spec must provide either 'universe' or 'symbols'")

    axes_raw = raw.get("axes") or []
    axes: list[Axis] = []
    for entry in axes_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"axis must be a mapping, got {type(entry).__name__}")
        ap = entry.get("path")
        if not ap:
            raise ValueError("axis missing 'path'")
        avs = entry.get("values")
        if not avs:
            raise ValueError(f"axis '{ap}' missing or empty 'values'")
        axes.append(Axis(path=str(ap), values=tuple(avs)))

    return GridSpec(
        name=str(name),
        base_config_path=Path(base),
        walk_forward=dict(wf),
        universe=str(universe) if universe else None,
        symbols=list(symbols) if symbols else None,
        axes=tuple(axes),
    )


def expand_combinations(spec: GridSpec) -> list[dict[str, Any]]:
    """Cartesian product of axis values → list of override dicts.

    Empty axes returns ``[{}]`` so the runner still executes the base config
    once (useful for re-running an existing config under a grid name).
    """
    if not spec.axes:
        return [{}]
    keys = [ax.path for ax in spec.axes]
    value_lists = [list(ax.values) for ax in spec.axes]
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*value_lists)]


def apply_overrides(base: StrategyConfig, overrides: dict[str, Any]) -> StrategyConfig:
    """Return a new ``StrategyConfig`` with dotted-path overrides applied.

    Round-trips through ``model_dump`` → mutate → ``model_validate`` so
    pydantic re-validates the merged shape. Original ``base`` is unchanged.
    """
    if not overrides:
        return base.model_copy(deep=True)
    raw = base.model_dump(mode="python")
    for path, value in overrides.items():
        _set_nested(raw, path, value)
    return StrategyConfig.model_validate(raw)


def _set_nested(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cursor: dict[str, Any] = data
    for key in parts[:-1]:
        node = cursor.get(key)
        if not isinstance(node, dict):
            new: dict[str, Any] = {}
            cursor[key] = new
            cursor = new
        else:
            cursor = node
    cursor[parts[-1]] = value


def format_run_name(grid_name: str, overrides: dict[str, Any]) -> str:
    """``{grid_name}#k1=v1,k2=v2`` — short keys (last segment of dotted path)."""
    if not overrides:
        return grid_name
    parts = []
    for path, val in overrides.items():
        short = path.rsplit(".", 1)[-1]
        parts.append(f"{short}={_fmt(val)}")
    return f"{grid_name}#{','.join(parts)}"


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # Trim noise like 0.6499999 — preserve up to 6 sig figs.
        return f"{value:.6g}"
    return str(value)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


BacktesterFactory = Callable[[StrategyConfig, BacktestData], Any]


def run_grid(
    spec: GridSpec,
    base_config: StrategyConfig,
    data: BacktestData,
    *,
    backtester_factory: BacktesterFactory | None = None,
    persist: Callable[[GridRunResult], None] | None = None,
    on_progress: Callable[[int, int, GridRunResult], None] | None = None,
) -> list[GridRunResult]:
    """Execute every combination sequentially against shared ``data``.

    - ``backtester_factory(cfg, data)`` defaults to ``Backtester(cfg, data)``;
      tests inject a mock factory.
    - ``persist`` (optional) is called with each result *before* progress —
      lets the CLI wire DB writes without leaking SQLAlchemy types here.
    - Failures in a single combo are captured into ``GridRunResult.error``;
      the loop continues so partial results are still recoverable.
    """
    if backtester_factory is None:

        def backtester_factory(cfg: StrategyConfig, d: BacktestData) -> Any:
            return Backtester(cfg, d)

    combos = expand_combinations(spec)
    results: list[GridRunResult] = []

    start = _coerce_date(spec.walk_forward["start"])
    end = _coerce_date(spec.walk_forward["end"])
    train_days = int(spec.walk_forward["train_days"])
    test_days = int(spec.walk_forward["test_days"])
    step_days = int(spec.walk_forward["step_days"])

    for idx, overrides in enumerate(combos):
        run_name = format_run_name(spec.name, overrides)
        cfg = apply_overrides(base_config, overrides)
        gr = GridRunResult(run_name=run_name, overrides=overrides, config=cfg)
        try:
            bt = backtester_factory(cfg, data)
            bt_result = bt.run(
                start,
                end,
                run_id=gr.run_id or 0,
                train_days=train_days,
                test_days=test_days,
                step_days=step_days,
            )
            gr.result = bt_result
        except Exception as exc:  # noqa: BLE001 — surface upstream failures, keep loop alive
            gr.error = f"{exc}\n{traceback.format_exc()}"
        if persist is not None:
            try:
                persist(gr)
            except Exception as exc:  # noqa: BLE001
                gr.error = (gr.error or "") + f"\npersist failed: {exc}"
        results.append(gr)
        if on_progress is not None:
            on_progress(idx + 1, len(combos), gr)
    return results


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"unsupported date value: {type(value).__name__}")


# Re-export field for convenience.
__all__ = [
    "Axis",
    "GridRunResult",
    "GridSpec",
    "apply_overrides",
    "expand_combinations",
    "field",
    "format_run_name",
    "load_grid_spec",
    "run_grid",
]
