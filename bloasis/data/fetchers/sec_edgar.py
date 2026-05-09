"""SEC EDGAR 10-K Risk Factors fetcher.

Fetches:
- ticker → CIK mapping (cached)
- list of 10-K filings per CIK with filing dates
- 10-K HTML → Item 1A "Risk Factors" plaintext

Used by Phase 3 Candidate D (`~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md`).

EDGAR rate limit: 10 req/sec. We sleep 0.15s between calls; refetches
hit parquet/text caches keyed by (cik, accession).

References:
- https://www.sec.gov/os/accessing-edgar-data
- Cohen-Malloy-Nguyen "Lazy Prices" 2020 — risk factors diff signal.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import TypedDict

USER_AGENT = "BSVibe Bloasis Research bloasis@bsvibe.dev"
BASE_DELAY = 0.15  # 10 req/sec cap → 0.15s headroom


class TenKFiling(TypedDict):
    accession: str  # "0000320193-25-000079"
    primary_doc: str  # "aapl-20250927.htm"
    filed: date
    period: date  # report period end (fiscal year end)


def _http_get(url: str, *, accept: str = "text/html") -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    return bytes(urllib.request.urlopen(req, timeout=30).read())


class EdgarClient:
    """EDGAR HTTP client + ticker→CIK + 10-K list + Item 1A extraction.

    All disk caches under `cache_dir/edgar/`:
    - tickers.json  — global ticker → CIK lookup (refreshed every N days)
    - filings/{cik}.json — submissions response
    - risk_factors/{cik}_{accession}.txt — extracted Item 1A text
    """

    def __init__(self, cache_dir: Path | str) -> None:
        self._root = Path(cache_dir).expanduser() / "edgar"
        (self._root / "filings").mkdir(parents=True, exist_ok=True)
        (self._root / "risk_factors").mkdir(parents=True, exist_ok=True)
        self._tickers: dict[str, str] | None = None

    # ------------------------------------------------------------------
    # ticker → CIK
    # ------------------------------------------------------------------
    def _load_tickers(self) -> dict[str, str]:
        path = self._root / "tickers.json"
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = json.loads(_http_get("https://www.sec.gov/files/company_tickers.json"))
            path.write_text(json.dumps(data))
            time.sleep(BASE_DELAY)
        return {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}

    def cik(self, ticker: str) -> str | None:
        if self._tickers is None:
            self._tickers = self._load_tickers()
        return self._tickers.get(ticker.upper())

    # ------------------------------------------------------------------
    # 10-K list
    # ------------------------------------------------------------------
    def list_10k(self, ticker: str) -> list[TenKFiling]:
        cik = self.cik(ticker)
        if cik is None:
            return []
        cache = self._root / "filings" / f"{cik}.json"
        if cache.exists():
            sub = json.loads(cache.read_text())
        else:
            sub = json.loads(_http_get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            cache.write_text(json.dumps(sub))
            time.sleep(BASE_DELAY)
        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        out: list[TenKFiling] = []
        for i, form in enumerate(forms):
            if form != "10-K":
                continue
            try:
                filed = date.fromisoformat(recent["filingDate"][i])
                period = date.fromisoformat(recent["reportDate"][i])
            except (KeyError, ValueError):
                continue
            out.append(
                TenKFiling(
                    accession=recent["accessionNumber"][i],
                    primary_doc=recent["primaryDocument"][i],
                    filed=filed,
                    period=period,
                )
            )
        # sort by filing date descending
        out.sort(key=lambda f: f["filed"], reverse=True)
        return out

    # ------------------------------------------------------------------
    # Item 1A extraction
    # ------------------------------------------------------------------
    def risk_factors(self, ticker: str, filing: TenKFiling) -> str | None:
        cik = self.cik(ticker)
        if cik is None:
            return None
        acc_clean = filing["accession"].replace("-", "")
        cache = self._root / "risk_factors" / f"{cik}_{acc_clean}.txt"
        if cache.exists():
            return cache.read_text()

        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_clean}/{filing['primary_doc']}"
        )
        try:
            html = _http_get(url, accept="text/html").decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            return None
        time.sleep(BASE_DELAY)

        section = _extract_item_1a(html)
        if section is None:
            return None
        cache.write_text(section)
        return section


# ---------------------------------------------------------------------------
# Item 1A parser — finds the longest "Item 1A → Item 1B/Item 2" span. The
# longest span heuristic dodges TOC and cross-references, which are short.
# ---------------------------------------------------------------------------


def _extract_item_1a(html: str) -> str | None:
    text = _strip_html(html)
    starts = [m.start() for m in re.finditer(r"(?i)item\s*1a\b", text)]
    ends = [m.start() for m in re.finditer(r"(?i)item\s*1b\b|item\s*2\.", text)]
    best: tuple[int, int] | None = None
    best_len = 0
    for s in starts:
        valid = [e for e in ends if e > s]
        if not valid:
            continue
        e = min(valid)
        if e - s > best_len:
            best_len = e - s
            best = (s, e)
    if best is None or best_len < 500:
        return None
    return text[best[0] : best[1]]


_HTML_ENTITIES = {
    "&#8217;": "'",
    "&rsquo;": "'",
    "&#8220;": '"',
    "&#8221;": '"',
    "&ldquo;": '"',
    "&rdquo;": '"',
    "&#160;": " ",
    "&nbsp;": " ",
    "&amp;": "&",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    for k, v in _HTML_ENTITIES.items():
        text = text.replace(k, v)
    text = re.sub(r"\s+", " ", text)
    return text
