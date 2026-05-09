"""Tests for `bloasis.data.universe.russell2000`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bloasis.data.universe.russell2000 import _parse, list_russell2000

SAMPLE_CSV = """iShares Russell 2000 ETF
Fund Holdings as of,Mar 1, 2025
,
"Ticker","Name","Asset Class","Market Value","Sector"
"AAPL","Apple","Equity","1000","Tech"
"MSFT","Microsoft","Equity","2000","Tech"
"-","Cash","Cash","100","-"
"USDM","USD Money Market","Money Market","50","Cash"
"BRK.B","Berkshire B","Equity","500","Financials"
"""


def test_parse_filters_to_alphabetic_equity_tickers() -> None:
    out = _parse(SAMPLE_CSV)
    # Cash placeholder ("-"), Money Market (non-Equity Asset Class), and
    # "BRK.B" (non-alpha) all dropped.
    assert out == ["AAPL", "MSFT"]


def test_parse_raises_when_header_missing() -> None:
    bad = "no header row in this csv body"
    try:
        _parse(bad)
    except ValueError as e:
        assert "Ticker" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_list_russell2000_uses_cache_when_fresh(tmp_path: Path) -> None:
    cache_path = tmp_path / "universe" / "russell2000.csv"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(SAMPLE_CSV)
    # No download patch — cache hit must short-circuit
    out = list_russell2000(cache_dir=tmp_path)
    assert "AAPL" in out


def test_list_russell2000_refreshes_when_forced(tmp_path: Path) -> None:
    cache_path = tmp_path / "universe" / "russell2000.csv"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("stale")
    fake_response = type("R", (), {"read": lambda self: SAMPLE_CSV.encode()})()
    with patch("urllib.request.urlopen", return_value=fake_response):
        out = list_russell2000(cache_dir=tmp_path, refresh=True)
    assert "MSFT" in out


def test_list_russell2000_downloads_on_cache_miss(tmp_path: Path) -> None:
    fake_response = type("R", (), {"read": lambda self: SAMPLE_CSV.encode()})()
    with patch("urllib.request.urlopen", return_value=fake_response):
        out = list_russell2000(cache_dir=tmp_path)
    assert out == ["AAPL", "MSFT"]
    # Cache file written
    assert (tmp_path / "universe" / "russell2000.csv").exists()
