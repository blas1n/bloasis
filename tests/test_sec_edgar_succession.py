"""Issue #75 — a successor registrant keeps its predecessor's 10-K history.

ExxonMobil's 2026-07-01 holding-company reorganization moved the `XOM`
ticker to a new CIK (2115436) that has an 8-K12B and no 10-K; every Exxon
10-K sits under the predecessor CIK (34088). EDGAR's JSON carries no
predecessor field, so the link comes from an explicit table — and it is
followed only while the successor's own submissions list the cited
succession filing. A ticker that merely moved to another CIK is never
stitched: tickers get reused by unrelated companies.

Network-free: `_http_get` is patched.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pydantic import ValidationError

from bloasis.config import StrategyConfig
from bloasis.data.fetchers.sec_edgar import (
    ITEM_1A_PARSER_VERSION,
    CikSuccession,
    EdgarClient,
)

_HTTP = "bloasis.data.fetchers.sec_edgar._http_get"
_SLEEP = "bloasis.data.fetchers.sec_edgar.time.sleep"

SUCCESSOR = "0002115436"
PREDECESSOR = "0000034088"
EVIDENCE = "0001193125-26-291990"
XOM = CikSuccession(
    successor_cik=SUCCESSOR, predecessor_cik=PREDECESSOR, evidence_accession=EVIDENCE
)


def _block(rows: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    """Submissions block from (form, filed, accession) rows."""
    return {
        "form": [r[0] for r in rows],
        "filingDate": [r[1] for r in rows],
        "reportDate": [r[1] for r in rows],
        "accessionNumber": [r[2] for r in rows],
        "primaryDocument": [f"doc-{r[2]}.htm" for r in rows],
    }


_PREDECESSOR_10KS = [
    ("10-K", "2026-02-18", "0000034088-26-000045"),
    ("8-K", "2025-10-31", "0000034088-25-000090"),
    ("10-K", "2025-02-19", "0000034088-25-000010"),
    ("10-K", "2024-02-28", "0000034088-24-000018"),
]


def _seed(tmp_path: Path, subs: dict[str, dict[str, Any]], ticker_cik: int) -> None:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "XOM", "cik_str": ticker_cik, "title": "Exxon"}})
    )
    for cik, body in subs.items():
        (edgar / "filings" / f"{cik}.json").write_text(json.dumps(body))


def _sub(rows: list[tuple[str, str, str]], files: list[dict[str, str]] | None = None) -> Any:
    filings: dict[str, Any] = {"recent": _block(rows)}
    if files is not None:
        filings["files"] = files
    return {"filings": filings}


def _successor_only_8k12b(form: str = "8-K12B") -> Any:
    return _sub(
        [
            ("8-K", "2026-07-31", "0002115436-26-000006"),
            (form, "2026-07-01", EVIDENCE),
        ]
    )


def _no_network(url: str, *, accept: str = "text/html") -> bytes:
    raise AssertionError(f"unexpected fetch {url}")


# ---------------------------------------------------------------------------
# list_10k
# ---------------------------------------------------------------------------


def test_successor_with_only_an_8k12b_reads_the_predecessor_10ks(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b(), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert [f["filed"] for f in out] == [date(2026, 2, 18), date(2025, 2, 19), date(2024, 2, 28)]
    assert {f["cik"] for f in out} == {PREDECESSOR}


def test_8k12g3_is_succession_evidence_too(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b("8-K12G3"), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert len(out) == 3


def test_reused_ticker_without_a_succession_entry_is_not_stitched(tmp_path: Path) -> None:
    # The ticker used to map to 34088 and now maps to a new CIK. Nothing in
    # the table links them, so the old CIK's 10-Ks must not be borrowed —
    # the predecessor snapshot is never even read.
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b(), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path).list_10k("XOM")

    assert out == []


def test_entry_is_ignored_when_the_successor_never_filed_the_cited_filing(
    tmp_path: Path,
) -> None:
    # A table entry is a claim; the successor's own submissions must back it.
    # Here the CIK was reassigned to a company with no succession filing.
    _seed(
        tmp_path,
        {
            SUCCESSOR: _sub([("8-K", "2026-07-31", "0002115436-26-000006")]),
            PREDECESSOR: _sub(_PREDECESSOR_10KS),
        },
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert out == []


def test_entry_is_ignored_when_the_cited_filing_is_not_a_succession_form(
    tmp_path: Path,
) -> None:
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b("8-K"), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert out == []


def test_succession_evidence_in_an_older_submissions_page_counts(tmp_path: Path) -> None:
    # Heavy filers push the 8-K12B out of `recent` within months.
    page = "CIK0002115436-submissions-001.json"
    _seed(
        tmp_path,
        {
            SUCCESSOR: _sub(
                [("424B2", "2027-01-05", "0001193125-27-000001")],
                files=[{"name": page, "filingFrom": "2026-07-01", "filingTo": "2026-12-31"}],
            ),
            PREDECESSOR: _sub(_PREDECESSOR_10KS),
        },
        ticker_cik=2115436,
    )
    (tmp_path / "edgar" / "filings" / page).write_text(
        json.dumps(_block([("8-K12B", "2026-07-01", EVIDENCE)]))
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert len(out) == 3


def test_successor_10k_takes_over_and_joint_filings_are_kept_once(tmp_path: Path) -> None:
    # Once the successor files its own 10-K it is the newest row, so the
    # rolling cosine pairs it with the predecessor's last 10-K. A 10-K filed
    # jointly by both registrants shows up in both snapshots — keep it once.
    joint = "0000034088-27-000012"
    _seed(
        tmp_path,
        {
            SUCCESSOR: _sub(
                [
                    ("10-K", "2027-02-17", joint),
                    ("8-K12B", "2026-07-01", EVIDENCE),
                ]
            ),
            PREDECESSOR: _sub([("10-K", "2027-02-17", joint), *_PREDECESSOR_10KS]),
        },
        ticker_cik=2115436,
    )
    with patch(_HTTP, side_effect=_no_network):
        out = EdgarClient(tmp_path, successions=[XOM]).list_10k("XOM")

    assert [f["accession"] for f in out] == [
        joint,
        "0000034088-26-000045",
        "0000034088-25-000010",
        "0000034088-24-000018",
    ]
    assert out[0]["cik"] == SUCCESSOR


# ---------------------------------------------------------------------------
# risk_factors reads the filing from the registrant that filed it
# ---------------------------------------------------------------------------


def test_predecessor_filing_text_is_fetched_under_the_predecessor_cik(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b(), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    served: list[str] = []
    item_1a = "<h2>Item 1A. Risk Factors</h2><p>" + "Oil. " * 200 + "</p><h2>Item 1B.</h2>"

    def fake_get(url: str, *, accept: str = "text/html") -> bytes:
        served.append(url)
        return item_1a.encode()

    client = EdgarClient(tmp_path, successions=[XOM])
    with patch(_HTTP, side_effect=fake_get), patch(_SLEEP):
        filing = client.list_10k("XOM")[0]
        text = client.risk_factors("XOM", filing)

    assert text is not None and "Oil." in text
    assert served == [
        "https://www.sec.gov/Archives/edgar/data/34088/000003408826000045/"
        "doc-0000034088-26-000045.htm"
    ]
    cached = (
        tmp_path
        / "edgar"
        / "risk_factors"
        / ITEM_1A_PARSER_VERSION
        / f"{PREDECESSOR}_000003408826000045.txt"
    )
    assert cached.exists()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_default_config_carries_the_exxon_succession() -> None:
    assert XOM in StrategyConfig().data.edgar_successions


def test_succession_ciks_are_normalized_to_ten_digits() -> None:
    cfg = StrategyConfig.model_validate(
        {
            "data": {
                "edgar_successions": [
                    {
                        "successor_cik": "2115436",
                        "predecessor_cik": 34088,
                        "evidence_accession": EVIDENCE,
                    }
                ]
            }
        }
    )
    assert cfg.data.edgar_successions == [XOM]


def test_succession_rejects_a_non_numeric_cik() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(
            {
                "data": {
                    "edgar_successions": [
                        {
                            "successor_cik": "XOM",
                            "predecessor_cik": "34088",
                            "evidence_accession": EVIDENCE,
                        }
                    ]
                }
            }
        )


# ---------------------------------------------------------------------------
# call site: live paper path → prefetch → real EdgarClient
# ---------------------------------------------------------------------------


def _live_history(tmp_path: Path, fake_get: Callable[..., bytes]) -> Any:
    from bloasis.cli import _build_live_candidates

    cfg = StrategyConfig.model_validate(
        {"scorer": {"type": "edgar_textdiff"}, "data": {"cache_dir": str(tmp_path)}}
    )
    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = pd.DataFrame({"close": [1.0]}, index=[today])
    captured: list[Any] = []

    def fake_backtester(_cfg: StrategyConfig, data: Any) -> MagicMock:
        captured.append(data)
        bt = MagicMock()
        bt._build_candidates.return_value = ([], [])
        return bt

    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher"),
        patch("bloasis.backtest.engine.Backtester", side_effect=fake_backtester),
        patch(_HTTP, side_effect=fake_get),
        patch(_SLEEP),
    ):
        _build_live_candidates(cfg, ["XOM"], days=400)
    return captured[0].risk_factors_history


def test_live_candidates_get_the_predecessor_history_from_the_default_config(
    tmp_path: Path,
) -> None:
    # No succession passed anywhere by hand: the default config's table must
    # reach the client the live path builds.
    _seed(
        tmp_path,
        {SUCCESSOR: _successor_only_8k12b(), PREDECESSOR: _sub(_PREDECESSOR_10KS)},
        ticker_cik=2115436,
    )
    item_1a = "<h2>Item 1A. Risk Factors</h2><p>" + "Oil. " * 200 + "</p><h2>Item 1B.</h2>"

    def fake_get(url: str, *, accept: str = "text/html") -> bytes:
        assert "/Archives/edgar/data/34088/" in url, url
        return item_1a.encode()

    history = _live_history(tmp_path, fake_get)

    assert [filed for filed, _p, _t in history["XOM"]] == [
        date(2024, 2, 28),
        date(2025, 2, 19),
        date(2026, 2, 18),
    ]
