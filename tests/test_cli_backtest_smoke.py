"""End-to-end CLI integration test for `bloasis backtest`.

Patches `YfOhlcvFetcher.fetch` to return synthetic OHLCV — all per-symbol
fetches and the SPY/^VIX market context fetch flow through the same
patched method, so no other monkeypatching is needed.

The point isn't to assert specific PnL numbers; it's to exercise the full
glue path (CLI → fetch → BacktestData → engine → folds → AcceptanceEvaluator
→ writers → DB) and surface integration bugs the unit tests don't catch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.data.fetchers import yfinance_ohlcv
from bloasis.storage import backtest_runs, get_engine

runner = CliRunner()


def _synthetic_ohlcv(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Geometric random walk with mild upward drift, seeded by symbol.

    Different symbols get different seeds so cross-section z-scoring sees
    real variance instead of a flat panel.
    """
    seed = abs(hash(symbol)) % (2**31)
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, end)
    n = len(days)
    if n == 0:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], name="timestamp"),
        )

    drift = 0.0003 if symbol != "^VIX" else 0.0
    vol = 0.012 if symbol != "^VIX" else 0.04
    base = 100.0 if symbol != "^VIX" else 18.0

    log_returns = rng.normal(drift, vol, n)
    close = base * np.exp(np.cumsum(log_returns))
    intraday = rng.normal(0, vol / 2, n)
    open_ = close * (1 - intraday / 2)
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 4, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 4, n)))
    volume = rng.integers(1_000_000, 50_000_000, n).astype(float)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=pd.DatetimeIndex(days, name="timestamp"),
    )
    return df


@pytest.fixture
def patched_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `YfOhlcvFetcher.fetch` with the synthetic generator."""

    def fake_fetch(self: object, symbol: str, start: date, end: date) -> pd.DataFrame:
        return _synthetic_ohlcv(symbol, start, end)

    monkeypatch.setattr(yfinance_ohlcv.YfOhlcvFetcher, "fetch", fake_fetch)


@pytest.fixture
def smoke_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db_path))
    return db_path


def _smoke_config(baseline_path: Path, tmp_path: Path) -> Path:
    """Write a smoke-friendly config: 1-fold acceptance + tmp cache_dir."""
    raw = yaml.safe_load(baseline_path.read_text())
    raw["acceptance_criteria"]["walk_forward_min_folds"] = 1
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    raw["data"]["cache_dir"] = str(cache_dir)
    out = tmp_path / "smoke.yaml"
    out.write_text(yaml.safe_dump(raw))
    return out


def test_cli_backtest_smoke_completes_and_persists_run(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """The whole CLI path runs without error and writes a completed row."""
    runner.invoke(app, ["init-db"])
    cfg = _smoke_config(baseline_config_path, tmp_path)

    result = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(cfg),
            "--start",
            "2022-06-01",
            "--end",
            "2024-12-31",
            "-s",
            "AAA",
            "-s",
            "BBB",
            "-s",
            "CCC",
            "-s",
            "DDD",
            "-s",
            "EEE",
            "--train-days",
            "180",
            "--test-days",
            "60",
            "--step-days",
            "60",
            "--name",
            "smoke",
        ],
    )
    assert result.exit_code == 0, result.output

    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.name == "smoke")).first()
    assert row is not None
    assert row.status == "completed"
    assert row.config_hash is not None
    assert row.final_equity is not None
    # Acceptance gate ran (whether it passed depends on synthetic noise).
    assert row.passed_acceptance is not None
    assert row.acceptance_reasons_json is not None


def test_cli_backtest_smoke_writes_equity_curve(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """Engine should populate equity_curve for completed folds."""
    from bloasis.storage import equity_curve

    runner.invoke(app, ["init-db"])
    cfg = _smoke_config(baseline_config_path, tmp_path)

    result = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(cfg),
            "--start",
            "2022-06-01",
            "--end",
            "2024-12-31",
            "-s",
            "AAA",
            "-s",
            "BBB",
            "-s",
            "CCC",
            "-s",
            "DDD",
            "-s",
            "EEE",
            "--train-days",
            "180",
            "--test-days",
            "60",
            "--step-days",
            "60",
            "--name",
            "smoke-curve",
        ],
    )
    assert result.exit_code == 0, result.output

    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row = conn.execute(
            select(backtest_runs).where(backtest_runs.c.name == "smoke-curve")
        ).first()
        assert row is not None
        run_id = row.run_id
        ec_count = conn.execute(
            select(equity_curve).where(equity_curve.c.run_id == run_id)
        ).fetchall()
    assert len(ec_count) > 0, "equity_curve should be populated for a completed run"


def test_cli_backtest_baseline_v2_smoke(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """`baseline-v2.yaml` (PR12 weights + regime overlay) loads + runs end-to-end."""

    runner.invoke(app, ["init-db"])
    # Use the actual baseline-v2.yaml from the repo (relative to baseline.yaml dir)
    baseline_v2_src = baseline_config_path.parent / "baseline-v2.yaml"
    if not baseline_v2_src.exists():
        pytest.skip("baseline-v2.yaml not present")

    raw = yaml.safe_load(baseline_v2_src.read_text())
    raw["acceptance_criteria"]["walk_forward_min_folds"] = 1
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    raw["data"]["cache_dir"] = str(cache_dir)
    out = tmp_path / "smoke-v2.yaml"
    out.write_text(yaml.safe_dump(raw))

    result = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(out),
            "--start",
            "2022-06-01",
            "--end",
            "2024-12-31",
            "-s",
            "AAA",
            "-s",
            "BBB",
            "-s",
            "CCC",
            "-s",
            "DDD",
            "-s",
            "EEE",
            "--train-days",
            "180",
            "--test-days",
            "60",
            "--step-days",
            "60",
            "--name",
            "smoke-v2",
        ],
    )
    assert result.exit_code == 0, result.output
    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.name == "smoke-v2")).first()
    assert row is not None
    assert row.status == "completed"


def test_cli_backtest_overlay_changes_equity(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """Enabling regime overlay should change the realized equity curve.

    Smoke test: same data + symbols, two configs differing only in
    `regime_overlay.enabled`. The two runs should produce different
    final_equity (overlay scales position sizes).
    """
    runner.invoke(app, ["init-db"])

    def make_cfg(name: str, overlay_enabled: bool) -> Path:
        raw = yaml.safe_load(baseline_config_path.read_text())
        raw["acceptance_criteria"]["walk_forward_min_folds"] = 1
        cache_dir = tmp_path / f"cache-{name}"
        cache_dir.mkdir(exist_ok=True)
        raw["data"]["cache_dir"] = str(cache_dir)
        raw["regime_overlay"] = {
            "enabled": overlay_enabled,
            "sigma_target": 0.12,
            "vol_lookback_days": 60,  # smaller for synthetic data
            "bear_lookback_days": 120,
            "bear_scale": 0.5,
            "scale_clip": [0.0, 1.5],
        }
        out = tmp_path / f"{name}.yaml"
        out.write_text(yaml.safe_dump(raw))
        return out

    syms = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    sym_args: list[str] = []
    for s in syms:
        sym_args.extend(["-s", s])

    base_args = [
        "backtest",
        "--start",
        "2022-06-01",
        "--end",
        "2024-12-31",
        *sym_args,
        "--train-days",
        "180",
        "--test-days",
        "60",
        "--step-days",
        "60",
    ]

    cfg_off = make_cfg("off", overlay_enabled=False)
    r_off = runner.invoke(app, [*base_args, "--config", str(cfg_off), "--name", "ovr-off"])
    assert r_off.exit_code == 0, r_off.output

    cfg_on = make_cfg("on", overlay_enabled=True)
    r_on = runner.invoke(app, [*base_args, "--config", str(cfg_on), "--name", "ovr-on"])
    assert r_on.exit_code == 0, r_on.output

    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row_off = conn.execute(
            select(backtest_runs).where(backtest_runs.c.name == "ovr-off")
        ).first()
        row_on = conn.execute(select(backtest_runs).where(backtest_runs.c.name == "ovr-on")).first()
    assert row_off is not None and row_on is not None
    # At least one realized metric must differ — proves the overlay touches
    # actual position sizing, not just config plumbing. Synthetic-data trades
    # are sparse so final_equity may collide; total_return / alpha won't.
    diffs = (
        abs(row_off.total_return - row_on.total_return),
        abs(row_off.alpha_vs_spy - row_on.alpha_vs_spy),
        abs(row_off.sharpe - row_on.sharpe),
    )
    assert max(diffs) > 1e-6, (
        f"overlay had no effect on any fold metric: "
        f"return diff={diffs[0]} alpha diff={diffs[1]} sharpe diff={diffs[2]}"
    )


def test_cli_backtest_skips_unfetchable_symbols(
    smoke_db: Path,
    baseline_config_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delisted/404 symbol shouldn't crash the run — it gets skipped with a warning."""

    def fake_fetch(self: object, symbol: str, start: date, end: date) -> pd.DataFrame:
        if symbol == "DEAD":
            raise ValueError(f"yfinance 404 for {symbol}")
        return _synthetic_ohlcv(symbol, start, end)

    monkeypatch.setattr(yfinance_ohlcv.YfOhlcvFetcher, "fetch", fake_fetch)
    runner.invoke(app, ["init-db"])
    cfg = _smoke_config(baseline_config_path, tmp_path)

    result = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(cfg),
            "--start",
            "2022-06-01",
            "--end",
            "2024-12-31",
            "-s",
            "AAA",
            "-s",
            "DEAD",
            "-s",
            "BBB",
            "-s",
            "CCC",
            "-s",
            "DDD",
            "--train-days",
            "180",
            "--test-days",
            "60",
            "--step-days",
            "60",
            "--name",
            "skip-dead",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "DEAD" in result.output
    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row = conn.execute(select(backtest_runs).where(backtest_runs.c.name == "skip-dead")).first()
    assert row is not None
    assert row.status == "completed"


def test_cli_runs_show_after_smoke_backtest(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """`bloasis runs show` should render a freshly-completed backtest."""
    runner.invoke(app, ["init-db"])
    cfg = _smoke_config(baseline_config_path, tmp_path)

    bt = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(cfg),
            "--start",
            "2023-01-01",
            "--end",
            "2024-06-30",
            "-s",
            "AAA",
            "-s",
            "BBB",
            "--train-days",
            "120",
            "--test-days",
            "60",
            "--step-days",
            "60",
            "--name",
            "show-test",
        ],
    )
    assert bt.exit_code == 0, bt.output

    show = runner.invoke(app, ["runs", "show", "1"])
    assert show.exit_code == 0, show.output
    assert "passed_acceptance" in show.output
    assert "show-test" in show.output
