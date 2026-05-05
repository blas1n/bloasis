"""End-to-end CLI integration test against committed real OHLCV fixtures.

The synthetic random-walk in `test_cli_backtest_smoke.py` hits the same code
path but never surfaces real-world edge cases (split days, holiday gaps,
unadjusted Close jumps, `^VIX` quirks). This module replays the same CLI flow
against parquet fixtures captured from yfinance via:

    bloasis fetch fixtures -s AAPL -s MSFT -s GOOGL -s NVDA -s JPM \\
                           -s SPY -s '^VIX' \\
                           --start 2019-01-01 --end 2024-12-31 \\
                           --out-dir tests/fixtures/ohlcv

Skips when fixtures are absent so the suite stays green on a fresh clone.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.data.fetchers import yfinance_ohlcv
from bloasis.storage import backtest_runs, equity_curve, get_engine

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ohlcv"
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "NVDA", "JPM"]
MARKET_SYMBOLS = ["SPY", "^VIX"]
ALL_SYMBOLS = SYMBOLS + MARKET_SYMBOLS


def _safe(symbol: str) -> str:
    return symbol.replace("^", "IDX_")


def _fixture_path(symbol: str) -> Path:
    return FIXTURES_DIR / f"{_safe(symbol)}.parquet"


def _all_fixtures_present() -> bool:
    return all(_fixture_path(s).is_file() for s in ALL_SYMBOLS)


pytestmark = pytest.mark.skipif(
    not _all_fixtures_present(),
    reason=(
        "real-data fixtures missing — run 'bloasis fetch fixtures "
        "-s AAPL -s MSFT -s GOOGL -s NVDA -s JPM -s SPY -s ^VIX "
        "--start 2019-01-01 --end 2024-12-31 --out-dir tests/fixtures/ohlcv'"
    ),
)


def _load_fixture(symbol: str, start: date, end: date) -> pd.DataFrame:
    df = pd.read_parquet(_fixture_path(symbol))
    mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
    return df.loc[mask]


@pytest.fixture
def patched_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `YfOhlcvFetcher.fetch` with a fixture-loading replay."""

    def fake_fetch(self: object, symbol: str, start: date, end: date) -> pd.DataFrame:
        return _load_fixture(symbol, start, end)

    monkeypatch.setattr(yfinance_ohlcv.YfOhlcvFetcher, "fetch", fake_fetch)


@pytest.fixture
def smoke_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db_path))
    return db_path


def _smoke_config(baseline_path: Path, tmp_path: Path) -> Path:
    raw = yaml.safe_load(baseline_path.read_text())
    raw["acceptance_criteria"]["walk_forward_min_folds"] = 1
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    raw["data"]["cache_dir"] = str(cache_dir)
    out = tmp_path / "smoke.yaml"
    out.write_text(yaml.safe_dump(raw))
    return out


def test_real_data_backtest_completes_and_writes_equity_curve(
    smoke_db: Path,
    patched_yfinance: None,
    baseline_config_path: Path,
    tmp_path: Path,
) -> None:
    """Full CLI backtest path runs cleanly on real OHLCV.

    Strict assertions: exit 0, run row written with status='completed',
    final_equity non-null, acceptance gate ran, equity_curve populated.
    """
    runner.invoke(app, ["init-db"])
    cfg = _smoke_config(baseline_config_path, tmp_path)

    result = runner.invoke(
        app,
        [
            "backtest",
            "--config",
            str(cfg),
            "--start",
            "2020-01-01",
            "--end",
            "2024-12-31",
            *[arg for s in SYMBOLS for arg in ("-s", s)],
            "--train-days",
            "365",
            "--test-days",
            "120",
            "--step-days",
            "120",
            "--name",
            "real-smoke",
        ],
    )
    assert result.exit_code == 0, result.output

    engine = get_engine(smoke_db)
    with engine.connect() as conn:
        row = conn.execute(
            select(backtest_runs).where(backtest_runs.c.name == "real-smoke")
        ).first()
        assert row is not None, "backtest_runs row missing"
        assert row.status == "completed", f"unexpected status: {row.status}"
        assert row.config_hash is not None
        assert row.final_equity is not None
        assert row.passed_acceptance is not None
        assert row.acceptance_reasons_json is not None

        ec_rows = conn.execute(
            select(equity_curve).where(equity_curve.c.run_id == row.run_id)
        ).fetchall()
    assert len(ec_rows) > 0, "equity_curve must be populated for completed run"
