"""Tests for `bloasis.data.universe`."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bloasis.config import DataConfig, UniverseConfig
from bloasis.data.universe import sp500_historical as mod
from bloasis.data.universe.custom_csv import list_custom_csv
from bloasis.data.universe.loader import load_universe
from bloasis.data.universe.sp500_historical import (
    _CACHED,
    DEFAULT_DATASET_URL,
    _parse_dataset,
    _resolve_dataset_url,
    list_sp500_at,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# URL whose basename collapses to "sp500_historical.csv" so existing
# pre-write tests keep matching the resolved cache path.
_TEST_URL = "https://test.example/sp500_historical.csv"


def _write_dataset(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["date,tickers"] + [f'{d},"{t}"' for d, t in rows]
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_dataset_cache() -> None:
    _CACHED.clear()


@pytest.fixture(autouse=True)
def _clear_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-clear SP500_HISTORICAL_URL so resolver path is exercised."""
    monkeypatch.delenv("SP500_HISTORICAL_URL", raising=False)


@pytest.fixture
def stable_url(monkeypatch: pytest.MonkeyPatch) -> str:
    """Pin SP500_HISTORICAL_URL so cache path is `<cache_dir>/sp500_historical.csv`."""
    monkeypatch.setenv("SP500_HISTORICAL_URL", _TEST_URL)
    return _TEST_URL


# ---------------------------------------------------------------------------
# _resolve_dataset_url
# ---------------------------------------------------------------------------


def test_resolve_url_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SP500_HISTORICAL_URL", "https://x.test/foo.csv")
    with patch("bloasis.data.universe.sp500_historical.httpx.get") as get:
        url = _resolve_dataset_url()
    assert url == "https://x.test/foo.csv"
    get.assert_not_called()


def test_default_dataset_url_points_at_current_upstream() -> None:
    """PR59 — upstream reorganised to `(Updated).csv` (canonical, live-updated)
    from the old `(MM-DD-YYYY).csv` naming. The frozen default MUST match the
    file the maintainer keeps alive so a network-free / API-down environment
    still lands on an existing URL."""
    assert "(Updated).csv" in DEFAULT_DATASET_URL
    assert "raw.githubusercontent.com/fja05680/sp500" in DEFAULT_DATASET_URL


def test_resolve_url_picks_latest_from_github_api() -> None:
    api_response = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "name": "S&P 500 Historical Components & Changes(02-21-2025).csv",
                "download_url": "https://raw.test/sp500-2025-02-21.csv",
                "type": "file",
            },
            {
                "name": "S&P 500 Historical Components & Changes(05-04-2026).csv",
                "download_url": "https://raw.test/sp500-2026-05-04.csv",
                "type": "file",
            },
            {
                "name": "README.md",
                "download_url": "https://raw.test/README.md",
                "type": "file",
            },
        ],
    )
    api_response.raise_for_status = MagicMock()
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=api_response,
    ) as get:
        url = _resolve_dataset_url()
    assert url == "https://raw.test/sp500-2026-05-04.csv"
    get.assert_called_once()
    assert "api.github.com" in get.call_args.args[0]


def test_resolve_url_falls_back_on_api_failure() -> None:
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        side_effect=httpx.RequestError("network down"),
    ):
        url = _resolve_dataset_url()
    assert url == DEFAULT_DATASET_URL


def test_resolve_url_prefers_updated_csv_over_bare() -> None:
    """PR59 — upstream reorganised: (Updated).csv is the actively-maintained
    file, bare .csv is the frozen historical snapshot. Prefer Updated."""
    api_response = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "name": "S&P 500 Historical Components & Changes.csv",
                "download_url": "https://raw.test/bare.csv",
                "type": "file",
            },
            {
                "name": "S&P 500 Historical Components & Changes (Updated).csv",
                "download_url": "https://raw.test/updated.csv",
                "type": "file",
            },
            {"name": "README.md", "download_url": "x", "type": "file"},
        ],
    )
    api_response.raise_for_status = MagicMock()
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=api_response,
    ):
        url = _resolve_dataset_url()
    assert url == "https://raw.test/updated.csv"


def test_resolve_url_falls_back_to_bare_csv_when_updated_missing() -> None:
    """If only the frozen historical file is present, use it."""
    api_response = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "name": "S&P 500 Historical Components & Changes.csv",
                "download_url": "https://raw.test/bare.csv",
                "type": "file",
            },
        ],
    )
    api_response.raise_for_status = MagicMock()
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=api_response,
    ):
        url = _resolve_dataset_url()
    assert url == "https://raw.test/bare.csv"


def test_resolve_url_updated_beats_dated_legacy() -> None:
    """If both new-format (Updated) and legacy dated files coexist, prefer Updated —
    the maintainer's canonical live copy."""
    api_response = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "name": "S&P 500 Historical Components & Changes(02-21-2025).csv",
                "download_url": "https://raw.test/legacy-dated.csv",
                "type": "file",
            },
            {
                "name": "S&P 500 Historical Components & Changes (Updated).csv",
                "download_url": "https://raw.test/updated.csv",
                "type": "file",
            },
        ],
    )
    api_response.raise_for_status = MagicMock()
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=api_response,
    ):
        url = _resolve_dataset_url()
    assert url == "https://raw.test/updated.csv"


def test_resolve_url_falls_back_when_no_csv_in_api_response() -> None:
    api_response = MagicMock(
        status_code=200,
        json=lambda: [
            {"name": "README.md", "download_url": "x", "type": "file"},
        ],
    )
    api_response.raise_for_status = MagicMock()
    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=api_response,
    ):
        url = _resolve_dataset_url()
    assert url == DEFAULT_DATASET_URL


# ---------------------------------------------------------------------------
# Cache keying by source filename
# ---------------------------------------------------------------------------


def test_cache_keyed_by_source_filename(tmp_path: Path) -> None:
    """Different URLs produce different cache files — no stale-cache reuse."""
    p1 = mod._dataset_path(tmp_path, "https://x.test/v1.csv")
    p2 = mod._dataset_path(tmp_path, "https://y.test/v2.csv")
    assert p1.name == "v1.csv"
    assert p2.name == "v2.csv"
    assert p1 != p2


def test_cache_path_unquotes_url_chars(tmp_path: Path) -> None:
    """URL-encoded chars (%26 → &) decoded so the on-disk name is readable."""
    url = "https://raw.test/S%26P%20500%20Historical(02-21-2025).csv"
    p = mod._dataset_path(tmp_path, url)
    assert p.name == "S&P 500 Historical(02-21-2025).csv"


# ---------------------------------------------------------------------------
# Actionable error on download failure
# ---------------------------------------------------------------------------


def test_download_failure_raises_actionable(tmp_path: Path) -> None:
    fake_request = MagicMock()
    fake_response = MagicMock(status_code=404)
    with (
        patch(
            "bloasis.data.universe.sp500_historical.httpx.get",
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=fake_request,
                response=fake_response,
            ),
        ),
        pytest.raises(RuntimeError) as excinfo,
    ):
        list_sp500_at(date(2024, 1, 1), cache_dir=tmp_path)
    msg = str(excinfo.value)
    assert "SP500_HISTORICAL_URL" in msg
    assert "--refresh" in msg


# ---------------------------------------------------------------------------
# Existing parse / lookup tests
# ---------------------------------------------------------------------------


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


def test_list_sp500_at_picks_most_recent_row(tmp_path: Path, stable_url: str) -> None:
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


def test_list_sp500_at_uses_exact_match(tmp_path: Path, stable_url: str) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B"), ("2020-06-01", "A,B,C")])
    out = list_sp500_at(date(2020, 6, 1), cache_dir=tmp_path)
    assert out == ["A", "B", "C"]


def test_list_sp500_at_predates_dataset_raises(tmp_path: Path, stable_url: str) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B")])
    with pytest.raises(ValueError, match="predates dataset"):
        list_sp500_at(date(2019, 1, 1), cache_dir=tmp_path)


def test_list_sp500_at_refresh_redownloads(tmp_path: Path, stable_url: str) -> None:
    """`refresh=True` should bypass the on-disk cache and re-download."""
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "OLD")])
    out1 = list_sp500_at(date(2020, 1, 1), cache_dir=tmp_path)
    assert out1 == ["OLD"]
    _CACHED.clear()

    new_csv = b'date,tickers\n2020-01-01,"NEW"\n'
    fake = MagicMock()
    fake.content = new_csv
    fake.raise_for_status = MagicMock()

    with patch(
        "bloasis.data.universe.sp500_historical.httpx.get",
        return_value=fake,
    ) as get:
        out2 = list_sp500_at(date(2020, 1, 1), cache_dir=tmp_path, refresh=True)
    assert out2 == ["NEW"]
    get.assert_called_once()


# ---------------------------------------------------------------------------
# custom_csv (unchanged)
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


def test_loader_dispatches_sp500(tmp_path: Path, stable_url: str) -> None:
    ds = tmp_path / "sp500_historical.csv"
    _write_dataset(ds, [("2020-01-01", "A,B,C")])
    cfg = UniverseConfig(source="sp500")
    data_cfg = DataConfig(cache_dir=tmp_path)
    out = load_universe(cfg, data_cfg, as_of=date(2020, 6, 1))
    assert out == ["A", "B", "C"]


def test_loader_dispatches_sp500_historical(tmp_path: Path, stable_url: str) -> None:
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
    cfg = UniverseConfig(source="sp500")
    data_cfg = DataConfig(cache_dir=tmp_path)
    with patch("bloasis.data.universe.sp500.list_sp500_at", return_value=["A", "B", "C"]):
        out = load_universe(cfg, data_cfg, as_of=None)
    assert out == ["A", "B", "C"]


def test_loader_propagates_refresh_flag(tmp_path: Path, stable_url: str) -> None:
    """`load_universe(..., refresh=True)` reaches `list_sp500_at`."""
    cfg = UniverseConfig(source="sp500_historical")
    data_cfg = DataConfig(cache_dir=tmp_path)
    with patch(
        "bloasis.data.universe.loader.list_sp500_at",
        return_value=["A", "B"],
    ) as fake:
        out = load_universe(cfg, data_cfg, as_of=date(2020, 1, 1), refresh=True)
    assert out == ["A", "B"]
    assert fake.call_args.kwargs.get("refresh") is True
