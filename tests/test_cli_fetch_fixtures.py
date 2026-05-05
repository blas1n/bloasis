"""Tests for `bloasis fetch fixtures` — the parquet-snapshot capture command.

The capture command pulls real OHLCV via yfinance (mocked here) and writes one
flat parquet per symbol so committed test fixtures don't depend on the cache
layout. `^VIX` is rewritten to `IDX_VIX.parquet` (filesystem-safe).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
from typer.testing import CliRunner

from bloasis.cli import app

runner = CliRunner()


def _yf_history_df() -> pd.DataFrame:
    """Mimic yfinance ticker.history() output (titlecase columns)."""
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "Open": [10.0, 11, 12, 13, 14],
            "High": [11.0, 12, 13, 14, 15],
            "Low": [9.0, 10, 11, 12, 13],
            "Close": [10.5, 11.5, 12.5, 13.5, 14.5],
            "Volume": [1000.0, 1100, 1200, 1300, 1400],
        },
        index=idx,
    )


def _patch_yfinance(df: pd.DataFrame) -> object:
    """Patch the static `_download` so we don't go through the yfinance import.

    Going via `patch.dict("sys.modules", {"yfinance": MagicMock()})` triggers
    a pyarrow `pandas.period` type-extension double-registration across tests.
    """
    # Match _download's normalization: lowercase columns, named timestamp index.
    normalized = df.copy()
    normalized.columns = [str(c).lower() for c in normalized.columns]
    normalized = normalized[["open", "high", "low", "close", "volume"]]
    normalized.index.name = "timestamp"
    return patch(
        "bloasis.data.fetchers.yfinance_ohlcv.YfOhlcvFetcher._download",
        return_value=normalized,
    )


def test_fetch_fixtures_writes_one_parquet_per_symbol(tmp_path: Path) -> None:
    out_dir = tmp_path / "fixtures"
    with _patch_yfinance(_yf_history_df()):
        result = runner.invoke(
            app,
            [
                "fetch",
                "fixtures",
                "-s",
                "AAPL",
                "-s",
                "MSFT",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-05",
                "--out-dir",
                str(out_dir),
            ],
        )
    assert result.exit_code == 0, result.output
    assert (out_dir / "AAPL.parquet").is_file()
    assert (out_dir / "MSFT.parquet").is_file()


def test_fetch_fixtures_caret_symbol_safe_filename(tmp_path: Path) -> None:
    out_dir = tmp_path / "fixtures"
    with _patch_yfinance(_yf_history_df()):
        result = runner.invoke(
            app,
            [
                "fetch",
                "fixtures",
                "-s",
                "^VIX",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-05",
                "--out-dir",
                str(out_dir),
            ],
        )
    assert result.exit_code == 0, result.output
    assert (out_dir / "IDX_VIX.parquet").is_file()
    assert not (out_dir / "^VIX.parquet").exists()


def test_fetch_fixtures_parquet_has_canonical_schema(tmp_path: Path) -> None:
    """Output must round-trip through the same shape `YfOhlcvFetcher.fetch` returns:
    lowercase OHLCV columns, DatetimeIndex named 'timestamp'.
    """
    out_dir = tmp_path / "fixtures"
    with _patch_yfinance(_yf_history_df()):
        result = runner.invoke(
            app,
            [
                "fetch",
                "fixtures",
                "-s",
                "AAPL",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-05",
                "--out-dir",
                str(out_dir),
            ],
        )
    assert result.exit_code == 0, result.output

    df = pd.read_parquet(out_dir / "AAPL.parquet")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "timestamp"
    assert len(df) == 5


def test_fetch_fixtures_creates_out_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "does" / "not" / "exist"
    with _patch_yfinance(_yf_history_df()):
        result = runner.invoke(
            app,
            [
                "fetch",
                "fixtures",
                "-s",
                "AAPL",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-05",
                "--out-dir",
                str(out_dir),
            ],
        )
    assert result.exit_code == 0, result.output
    assert (out_dir / "AAPL.parquet").is_file()
