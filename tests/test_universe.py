"""Tests for `bloasis.data.universe`."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from bloasis.config import DataConfig, UniverseConfig
from bloasis.data.universe.custom_csv import list_custom_csv
from bloasis.data.universe.loader import load_universe
from bloasis.data.universe.sp500_historical import (
    _CACHED,
    _parse_dataset,
    list_sp500_at,
)

# ---------------------------------------------------------------------------
# sp500_historical
# ---------------------------------------------------------------------------


def _write_dataset(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["date,tickers"] + [f'{d},"{t}"' for d, t in rows]
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_dataset_cache() -> None:
    _CACHED.clear()


def test_parse_dataset_skips_bad_rows(tmp_path: Path) -> None:
    path = tmp_path / "ds.csv"
    path.write_text(
        'date,tickers\n2020-01-01,"A,B,C"\nnot-a-date,"X,Y"\n2021-06-15,"A,B,D"\n',
        encoding="utf-8",
    )
    rows = _parse_dataset(path)
    assert [r[0] for r in rows] == [date(2020, 1, 1), date(2021, 6, 15)]
    assert rows[1][1] == ["A", "B", "D"]


def test_parse_dataset_rejects_bad_header(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n2020-01-01,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected dataset header"):
        _parse_dataset(path)


def test_parse_dataset_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("date,tickers\n", encoding="utf-8")
    with pytest.raises(ValueError, match="zero rows"):
        _parse_dataset(path)


def test_list_sp500_at_picks_most_recent_row(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(
        ds,
        [
            ("2020-01-01", "A,B"),
            ("2020-06-01", "A,B,C"),
            ("2021-01-01", "A,C"),
        ],
    )
    out = list_sp500_at(date(2020, 8, 1), cache_dir=tmp_path)
    assert out == ["A", "B", "C"]


def test_list_sp500_at_uses_exact_match(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B"), ("2020-06-01", "A,B,C")])
    out = list_sp500_at(date(2020, 6, 1), cache_dir=tmp_path)
    assert out == ["A", "B", "C"]


def test_list_sp500_at_predates_dataset_raises(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B")])
    with pytest.raises(ValueError, match="predates dataset"):
        list_sp500_at(date(2019, 1, 1), cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# custom_csv
# ---------------------------------------------------------------------------


def test_custom_csv_reads_symbol_column(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("symbol,name\nAAPL,Apple\nMSFT,Microsoft\n", encoding="utf-8")
    assert list_custom_csv(path) == ["AAPL", "MSFT"]


def test_custom_csv_case_insensitive_column(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("Symbol\naapl\ngoog\n", encoding="utf-8")
    assert list_custom_csv(path) == ["AAPL", "GOOG"]


def test_custom_csv_dedups_preserve_order(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("symbol\nAAPL\nMSFT\nAAPL\nGOOG\n", encoding="utf-8")
    assert list_custom_csv(path) == ["AAPL", "MSFT", "GOOG"]


def test_custom_csv_skips_comments_and_blanks(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("# this is a comment\nsymbol\n# another\nAAPL\n\nMSFT\n", encoding="utf-8")
    assert list_custom_csv(path) == ["AAPL", "MSFT"]


def test_custom_csv_missing_symbol_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("ticker\nAAPL\n", encoding="utf-8")
    with pytest.raises(ValueError, match="symbol' column"):
        list_custom_csv(path)


def test_custom_csv_empty_raises(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text("symbol\n\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no symbols found"):
        list_custom_csv(path)


def test_custom_csv_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_custom_csv(tmp_path / "nope.csv")


# ---------------------------------------------------------------------------
# loader (dispatch)
# ---------------------------------------------------------------------------


def test_loader_dispatches_sp500(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B,C")])
    cfg = UniverseConfig(source="sp500")
    data_cfg = DataConfig(cache_dir=tmp_path)
    out = load_universe(cfg, data_cfg, as_of=date(2020, 6, 1))
    assert out == ["A", "B", "C"]


def test_loader_dispatches_sp500_historical(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "X,Y")])
    cfg = UniverseConfig(source="sp500_historical")
    data_cfg = DataConfig(cache_dir=tmp_path)
    out = load_universe(cfg, data_cfg, as_of=date(2020, 1, 1))
    assert out == ["X", "Y"]


def test_loader_sp500_historical_requires_as_of(tmp_path: Path) -> None:
    cfg = UniverseConfig(source="sp500_historical")
    data_cfg = DataConfig(cache_dir=tmp_path)
    with pytest.raises(ValueError, match="requires as_of"):
        load_universe(cfg, data_cfg, as_of=None)


def test_loader_dispatches_custom_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("symbol\nAAA\nBBB\n", encoding="utf-8")
    cfg = UniverseConfig(source="custom_csv", custom_csv_path=csv_path)
    data_cfg = DataConfig(cache_dir=tmp_path)
    out = load_universe(cfg, data_cfg)
    assert out == ["AAA", "BBB"]


def test_loader_uses_today_for_sp500_when_as_of_none(tmp_path: Path) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B,C")])
    cfg = UniverseConfig(source="sp500")
    data_cfg = DataConfig(cache_dir=tmp_path)
    # Patch list_sp500_at via the import in sp500.py to avoid using today's date noise.
    with patch("bloasis.data.universe.sp500.list_sp500_at", return_value=["A", "B", "C"]):
        out = load_universe(cfg, data_cfg, as_of=None)
    assert out == ["A", "B", "C"]
