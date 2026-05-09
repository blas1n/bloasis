"""Tests for `bloasis.data.fetchers.sec_edgar`.

Network-free: covers the HTML parser, ticker→CIK loader (via mock), and
cache hit paths. The HTTP path (`_http_get`) is exercised through patches
that simulate the SEC EDGAR responses.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bloasis.data.fetchers.sec_edgar import (
    EdgarClient,
    _extract_item_1a,
    _strip_html,
)

# ---------------------------------------------------------------------------
# pure parser
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags_and_entities() -> None:
    html = "<p>Hello&nbsp;<b>world</b>&#160;test &amp; more</p>"
    assert _strip_html(html) == " Hello world test & more "


def test_strip_html_collapses_whitespace() -> None:
    html = "<div>a\n\n\nb\t\tc</div>"
    assert _strip_html(html) == " a b c "


def test_extract_item_1a_picks_longest_span() -> None:
    # Build a synthetic 10-K with a TOC reference + a real Item 1A section.
    long_risk_section = "Risk content. " * 200  # ~3000 chars
    html = (
        "<html><body>"
        "<table><tr><td>Item 1A. Risk Factors</td><td>5</td></tr></table>"  # TOC
        "<p>Item 1B. Unresolved Staff Comments</p>"
        f"<h2>Item 1A. Risk Factors</h2><p>{long_risk_section}</p>"
        "<h2>Item 1B. Unresolved Staff Comments</h2>"
        "<p>None.</p>"
        "</body></html>"
    )
    section = _extract_item_1a(html)
    assert section is not None
    assert len(section) > 1000
    assert "Risk content" in section


def test_extract_item_1a_returns_none_when_no_1a() -> None:
    html = "<html><body><p>No risk factors here.</p></body></html>"
    assert _extract_item_1a(html) is None


def test_extract_item_1a_returns_none_when_section_too_short() -> None:
    # Item 1A → Item 1B but very short body — below the 500-char min.
    html = "<p>Item 1A. Risk Factors</p><p>Brief.</p><p>Item 1B. Comments</p>"
    assert _extract_item_1a(html) is None


# ---------------------------------------------------------------------------
# EdgarClient — cached paths
# ---------------------------------------------------------------------------


def test_cik_lookup_uses_cached_tickers(tmp_path: Path) -> None:
    cache = tmp_path / "edgar"
    cache.mkdir(parents=True)
    (cache / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}})
    )
    client = EdgarClient(tmp_path)
    assert client.cik("AAPL") == "0000320193"
    assert client.cik("aapl") == "0000320193"  # case-insensitive
    assert client.cik("UNKNOWN") is None


def test_list_10k_filters_to_form_and_sorts_desc(tmp_path: Path) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}})
    )
    (edgar / "filings" / "0000320193.json").write_text(
        json.dumps(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K", "8-K", "10-K", "10-Q"],
                        "filingDate": [
                            "2024-11-01",
                            "2024-10-01",
                            "2023-11-03",
                            "2024-08-01",
                        ],
                        "reportDate": [
                            "2024-09-28",
                            "2024-09-30",
                            "2023-09-30",
                            "2024-06-30",
                        ],
                        "accessionNumber": ["a1", "a2", "a3", "a4"],
                        "primaryDocument": ["d1", "d2", "d3", "d4"],
                    }
                }
            }
        )
    )
    client = EdgarClient(tmp_path)
    out = client.list_10k("AAPL")
    assert len(out) == 2
    assert out[0]["filed"] == date(2024, 11, 1)  # newer first
    assert out[1]["filed"] == date(2023, 11, 3)
    assert out[0]["accession"] == "a1"


def test_list_10k_returns_empty_for_unknown_ticker(tmp_path: Path) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "tickers.json").write_text(json.dumps({}))
    client = EdgarClient(tmp_path)
    assert client.list_10k("ZZZZ") == []


def test_risk_factors_serves_text_cache(tmp_path: Path) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "risk_factors").mkdir(parents=True)
    (edgar / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}})
    )
    cached_text = "Cached risk factors content " * 50
    (edgar / "risk_factors" / "0000320193_a1.txt").write_text(cached_text)

    client = EdgarClient(tmp_path)
    filing = {
        "accession": "a1",
        "primary_doc": "d1",
        "filed": date(2024, 11, 1),
        "period": date(2024, 9, 28),
    }
    out = client.risk_factors("AAPL", filing)  # type: ignore[arg-type]
    assert out == cached_text


def test_risk_factors_fetches_and_caches_when_absent(tmp_path: Path) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "risk_factors").mkdir(parents=True)
    (edgar / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}})
    )

    long_risk = "Risk content. " * 200
    fake_html = (
        f"<html><body><h2>Item 1A. Risk Factors</h2><p>{long_risk}</p>"
        "<h2>Item 1B. Comments</h2></body></html>"
    )

    client = EdgarClient(tmp_path)
    filing = {
        "accession": "a1",
        "primary_doc": "d1",
        "filed": date(2024, 11, 1),
        "period": date(2024, 9, 28),
    }
    with patch(
        "bloasis.data.fetchers.sec_edgar._http_get",
        return_value=fake_html.encode(),
    ):
        out = client.risk_factors("AAPL", filing)  # type: ignore[arg-type]
    assert out is not None
    assert "Risk content" in out
    # Cache file written
    cache_file = edgar / "risk_factors" / "0000320193_a1.txt"
    assert cache_file.exists()
