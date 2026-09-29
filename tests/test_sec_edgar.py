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


def test_list_filings_filters_by_form_type(tmp_path: Path) -> None:
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
                        "form": ["10-K", "8-K", "4", "8-K", "10-Q"],
                        "filingDate": [
                            "2024-11-01",
                            "2024-10-01",
                            "2024-09-15",
                            "2024-08-01",
                            "2024-07-01",
                        ],
                        "reportDate": [""] * 5,
                        "accessionNumber": ["a1", "a2", "a3", "a4", "a5"],
                        "primaryDocument": ["d1", "d2", "d3", "d4", "d5"],
                    }
                }
            }
        )
    )
    client = EdgarClient(tmp_path)

    eight_ks = client.list_filings("AAPL", form_type="8-K")
    assert len(eight_ks) == 2
    assert {f["accession"] for f in eight_ks} == {"a2", "a4"}

    form_4s = client.list_filings("AAPL", form_type="4")
    assert len(form_4s) == 1
    assert form_4s[0]["accession"] == "a3"

    none_match = client.list_filings("AAPL", form_type="ZZZ")
    assert none_match == []


def test_list_filings_unknown_ticker_returns_empty(tmp_path: Path) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "tickers.json").write_text(json.dumps({}))
    client = EdgarClient(tmp_path)
    assert client.list_filings("ZZZZ", form_type="8-K") == []


# ---------------------------------------------------------------------------
# Issue #70 — coverage gaps that left ~5% of SP500 without a cosine
# ---------------------------------------------------------------------------

_LONG_RISK = "Risk content. " * 200


def _write_tickers(edgar: Path, rows: dict[str, int]) -> None:
    edgar.mkdir(parents=True, exist_ok=True)
    (edgar / "tickers.json").write_text(
        json.dumps(
            {
                str(i): {"ticker": t, "cik_str": c, "title": t}
                for i, (t, c) in enumerate(rows.items())
            }
        )
    )


def test_cik_resolves_dot_class_ticker_to_sec_dash_form(tmp_path: Path) -> None:
    # SEC lists share classes as "BRK-B"; the SP500 universe spells them "BRK.B".
    _write_tickers(tmp_path / "edgar", {"BRK-B": 1067983})
    client = EdgarClient(tmp_path)
    assert client.cik("BRK.B") == "0001067983"


def _filings_block(forms: list[str], dates: list[str]) -> dict[str, list[str]]:
    return {
        "form": forms,
        "filingDate": dates,
        "reportDate": dates,
        "accessionNumber": [f"acc-{d}" for d in dates],
        "primaryDocument": [f"doc-{d}.htm" for d in dates],
    }


def test_list_10k_reads_older_submission_pages(tmp_path: Path) -> None:
    # Big banks file thousands of 424B2s a year, so the submissions API
    # `recent` block covers only months; older 10-Ks live in `filings.files`.
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    _write_tickers(edgar, {"JPM": 19617})
    (edgar / "filings" / "0000019617.json").write_text(
        json.dumps(
            {
                "filings": {
                    "recent": _filings_block(["10-K", "424B2"], ["2026-02-13", "2026-01-02"]),
                    "files": [
                        {"name": "CIK0000019617-submissions-001.json", "filingTo": "2025-12-30"},
                        {"name": "CIK0000019617-submissions-002.json", "filingTo": "2019-01-01"},
                    ],
                }
            }
        )
    )
    page1 = _filings_block(["10-K", "424B2", "10-K"], ["2025-02-14", "2025-01-02", "2024-02-16"])
    served: list[str] = []

    def fake_get(url: str, *, accept: str = "text/html") -> bytes:
        served.append(url)
        assert url.endswith("CIK0000019617-submissions-001.json"), url
        return json.dumps(page1).encode()

    client = EdgarClient(tmp_path)
    with (
        patch("bloasis.data.fetchers.sec_edgar._http_get", side_effect=fake_get),
        patch("bloasis.data.fetchers.sec_edgar.time.sleep"),
    ):
        out = client.list_10k("JPM", since=date(2020, 1, 1))
        again = client.list_10k("JPM", since=date(2020, 1, 1))  # page served from cache

    assert [f["filed"] for f in out] == [date(2026, 2, 13), date(2025, 2, 14), date(2024, 2, 16)]
    assert again == out
    # Page 002 ends before `since` → never fetched; page 001 fetched once.
    assert len(served) == 1


def test_extract_item_1a_parenthesised_item_numbers() -> None:
    # HAL: "Item 1(a). Risk Factors" ... "Item 1(b). Unresolved Staff Comments"
    html = (
        f"<p>Item 1(a). Risk Factors</p><p>{_LONG_RISK}</p>"
        "<p>Item 1(b). Unresolved Staff Comments</p><p>None.</p>"
    )
    section = _extract_item_1a(html)
    assert section is not None and "Risk content" in section


def test_extract_item_1a_dotted_item_numbers() -> None:
    # ROL: "Item 1.A. Risk Factors" ... "Item 1.B. Unresolved Staff Comments"
    html = f"<p>Item 1.A. Risk Factors</p><p>{_LONG_RISK}</p><p>Item 1.B. Unresolved</p>"
    section = _extract_item_1a(html)
    assert section is not None and "Risk content" in section


def test_extract_item_1a_drop_cap_split_heading() -> None:
    # CHD: drop-cap styling renders "<span>I</span><span>TEM</span> 1A" → "I TEM 1A",
    # and the section ends at Item 1C (Item 1B heading is styled the same way).
    html = (
        f"<h2><span>I</span><span>TEM</span> 1A. RISK FACTORS</h2><p>{_LONG_RISK}</p>"
        "<h2><span>I</span><span>TEM</span> 1C. CYBERSECURITY</h2>"
    )
    section = _extract_item_1a(html)
    assert section is not None and "Risk content" in section


def test_extract_item_1a_strict_result_wins_over_fallback() -> None:
    # Filings the strict parser already handles must extract byte-identically,
    # so cached texts and backtests on those names do not move. The relaxed
    # pattern alone would start at the earlier "Item 1(a)" cross-reference.
    html = (
        f"<p>As discussed in Item 1(a) below. {'Business prose. ' * 100}</p>"
        f"<h2>Item 1A. Risk Factors</h2><p>{_LONG_RISK}</p>"
        "<h2>Item 1B. Unresolved Staff Comments</h2>"
    )
    section = _extract_item_1a(html)
    assert section is not None
    assert section.startswith("Item 1A. Risk Factors")


def test_list_10k_dedupes_filings_seen_in_recent_and_a_page(tmp_path: Path) -> None:
    # Page boundaries move as new filings arrive: a submissions snapshot cached
    # earlier overlaps a page fetched later. A duplicated 10-K would be compared
    # with itself (cosine 1.0) and look like the most stable filer in the index.
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    _write_tickers(edgar, {"USB": 36104})
    (edgar / "filings" / "0000036104.json").write_text(
        json.dumps(
            {
                "filings": {
                    "recent": _filings_block(["10-K", "10-K"], ["2026-02-23", "2025-02-21"]),
                    "files": [
                        {"name": "CIK0000036104-submissions-001.json", "filingTo": "2025-03-01"}
                    ],
                }
            }
        )
    )
    (edgar / "filings" / "CIK0000036104-submissions-001.json").write_text(
        json.dumps(_filings_block(["10-K", "10-K"], ["2025-02-21", "2024-02-20"]))
    )
    out = EdgarClient(tmp_path).list_10k("USB", since=date(2020, 1, 1))
    assert [f["filed"] for f in out] == [date(2026, 2, 23), date(2025, 2, 21), date(2024, 2, 20)]
