"""SEC EDGAR 10-K Risk Factors fetcher.

Fetches:
- ticker → CIK mapping (cached)
- list of 10-K filings per CIK with filing dates
- 10-K HTML → Item 1A "Risk Factors" plaintext

Used by Phase 3 Candidate D (`docs/research/Phase3_Modern_Candidates_2026-05-08.md`).

EDGAR rate limit: 10 req/sec. We sleep 0.15s after every request (failed
ones too); refetches hit parquet/text caches keyed by (cik, accession).

`tickers.json` and the submissions snapshots expire after `max_age_hours`
(issue #72); a failed refresh serves the stale copy with a warning.

References:
- https://www.sec.gov/os/accessing-edgar-data
- Cohen-Malloy-Nguyen "Lazy Prices" 2020 — risk factors diff signal.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

USER_AGENT = "BSVibe Bloasis Research bloasis@bsvibe.dev"
BASE_DELAY = 0.15  # 10 req/sec cap → 0.15s headroom
DEFAULT_MAX_AGE_HOURS = 24
# SEC throttling answers: once seen, more requests this run only dig deeper.
_THROTTLED = (403, 429)


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
    - tickers.json  — global ticker → CIK lookup (expires after max_age_hours)
    - filings/{cik}.json — submissions response (expires after max_age_hours)
    - filings/CIK…-submissions-NNN.json — older pages; valid only while no
      older than their snapshot, since page boundaries move with new filings
    - risk_factors/{cik}_{accession}.txt — extracted Item 1A text (immutable)
    """

    def __init__(
        self, cache_dir: Path | str, *, max_age_hours: float = DEFAULT_MAX_AGE_HOURS
    ) -> None:
        self._root = Path(cache_dir).expanduser() / "edgar"
        (self._root / "filings").mkdir(parents=True, exist_ok=True)
        (self._root / "risk_factors").mkdir(parents=True, exist_ok=True)
        self._tickers: dict[str, str] | None = None
        self._max_age_s = max_age_hours * 3600
        self._refresh_disabled = False

    # ------------------------------------------------------------------
    # expiring JSON cache
    # ------------------------------------------------------------------
    def _cached_json(self, path: Path, url: str, *, kind: str, valid_since: float | None) -> Any:
        """Cached JSON at `path`, refetched from `url` when invalid.

        The copy is valid while its mtime is at/after `valid_since` (None:
        within max age). A failed refetch serves the invalid copy with a
        warning; with no copy on disk the failure propagates.
        """
        if not path.exists():
            data = self._fetch_json(url)
            path.write_text(json.dumps(data))
            return data
        mtime = path.stat().st_mtime
        if valid_since is None:
            valid_since = time.time() - self._max_age_s
        if mtime >= valid_since or self._refresh_disabled:
            return json.loads(path.read_text())
        try:
            data = self._fetch_json(url)
        except (OSError, ValueError) as exc:
            age_h = round((time.time() - mtime) / 3600, 1)
            logger.warning(
                "edgar_refresh_failed kind=%s path=%s age_hours=%s error=%r",
                kind,
                path,
                age_h,
                exc,
                extra={"edgar_kind": kind, "edgar_path": str(path), "edgar_age_hours": age_h},
            )
            code = getattr(exc, "code", None)
            if not isinstance(exc, urllib.error.HTTPError) or code in _THROTTLED:
                # Network down or SEC throttling: every further stale file
                # would wait out its own timeout. Serve stale for the run.
                self._refresh_disabled = True
                logger.warning(
                    "edgar_refresh_disabled reason=%r; serving stale EDGAR cache for this run",
                    exc,
                    extra={"edgar_kind": kind},
                )
            return json.loads(path.read_text())
        path.write_text(json.dumps(data))
        return data

    @staticmethod
    def _fetch_json(url: str) -> Any:
        try:
            return json.loads(_http_get(url))
        finally:
            time.sleep(BASE_DELAY)

    def _submissions(self, cik: str) -> tuple[dict[str, Any], float]:
        """Submissions snapshot and the mtime its pages must not predate."""
        path = self._root / "filings" / f"{cik}.json"
        sub: dict[str, Any] = self._cached_json(
            path,
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            kind="submissions",
            valid_since=None,
        )
        return sub, path.stat().st_mtime

    # ------------------------------------------------------------------
    # ticker → CIK
    # ------------------------------------------------------------------
    def _load_tickers(self) -> dict[str, str]:
        data = self._cached_json(
            self._root / "tickers.json",
            "https://www.sec.gov/files/company_tickers.json",
            kind="tickers",
            valid_since=None,
        )
        return {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}

    def cik(self, ticker: str) -> str | None:
        if self._tickers is None:
            self._tickers = self._load_tickers()
        upper = ticker.upper()
        # SEC spells share classes "BRK-B"; index constituents spell them "BRK.B".
        return self._tickers.get(upper) or self._tickers.get(upper.replace(".", "-"))

    # ------------------------------------------------------------------
    # 10-K list
    # ------------------------------------------------------------------
    def list_10k(self, ticker: str, *, since: date | None = None) -> list[TenKFiling]:
        """10-K filings, newest first.

        The submissions API `recent` block holds only the latest ~1000+
        filings; for heavy filers (big banks issue thousands of 424B2 notes a
        year) that is a few months, so older 10-Ks live in the paginated
        `filings.files` pages. Pages whose `filingTo` is on/after `since`
        (all pages when `since` is None) are read too; a cached page older
        than its snapshot is refetched, because new filings shift the page
        boundaries and a stale page can miss rows the snapshot moved out.
        """
        cik = self.cik(ticker)
        if cik is None:
            return []
        sub, snapshot_mtime = self._submissions(cik)
        filings = sub.get("filings", {})
        blocks = [filings.get("recent", {})]
        for page in filings.get("files", []):
            name = str(page.get("name", ""))
            if not name:
                continue
            if since is not None:
                try:
                    if date.fromisoformat(str(page["filingTo"])) < since:
                        continue
                except (KeyError, ValueError):
                    pass
            blocks.append(self._submissions_page(name, snapshot_mtime))
        # Page boundaries shift as new filings arrive, so a snapshot cached
        # earlier can overlap a page fetched later — keep each accession once.
        by_accession: dict[str, TenKFiling] = {}
        for block in blocks:
            for row in _tenk_rows(block):
                by_accession.setdefault(row["accession"], row)
        out = list(by_accession.values())
        # sort by filing date descending
        out.sort(key=lambda f: f["filed"], reverse=True)
        return out

    def _submissions_page(self, name: str, snapshot_mtime: float) -> dict[str, list[str]]:
        page: dict[str, list[str]] = self._cached_json(
            self._root / "filings" / name,
            f"https://data.sec.gov/submissions/{name}",
            kind="submissions_page",
            valid_since=snapshot_mtime,
        )
        return page

    # ------------------------------------------------------------------
    # Generic form list — Form 4 (insider trades), 8-K (events)
    # ------------------------------------------------------------------
    def list_filings(self, ticker: str, *, form_type: str) -> list[dict[str, object]]:
        """Return all filings of `form_type` (e.g. "4", "8-K") for ticker.

        Lightweight — returns dicts with `accession`, `primary_doc`, `filed`
        (date). The submissions API "recent" payload is shared with
        list_10k so the cache hit is free after one fetch.
        """
        cik = self.cik(ticker)
        if cik is None:
            return []
        sub, _snapshot_mtime = self._submissions(cik)
        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        out: list[dict[str, object]] = []
        for i, form in enumerate(forms):
            if form != form_type:
                continue
            try:
                filed = date.fromisoformat(recent["filingDate"][i])
            except (KeyError, ValueError):
                continue
            out.append(
                {
                    "accession": recent["accessionNumber"][i],
                    "primary_doc": recent.get("primaryDocument", [""] * len(forms))[i],
                    "filed": filed,
                }
            )
        out.sort(key=lambda f: f["filed"], reverse=True)  # type: ignore[arg-type, return-value]
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


def _tenk_rows(block: dict[str, list[str]]) -> list[TenKFiling]:
    forms = block.get("form", [])
    out: list[TenKFiling] = []
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        try:
            filed = date.fromisoformat(block["filingDate"][i])
            period = date.fromisoformat(block["reportDate"][i])
        except (KeyError, ValueError, IndexError):
            continue
        out.append(
            TenKFiling(
                accession=block["accessionNumber"][i],
                primary_doc=block["primaryDocument"][i],
                filed=filed,
                period=period,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Item 1A parser — finds the longest "Item 1A → Item 1B/Item 2" span. The
# longest span heuristic dodges TOC and cross-references, which are short.
# ---------------------------------------------------------------------------


_STRICT_START = re.compile(r"(?i)item\s*1a\b")
_STRICT_END = re.compile(r"(?i)item\s*1b\b|item\s*2\.")
# Fallback spellings seen in SP500 10-Ks (issue #70): "Item 1(a)" (HAL),
# "Item 1.A." (ROL), drop-cap "I TEM 1A" (CHD), and sections that close at
# Item 1C or at "Item 2" without a period.
_RELAXED_START = re.compile(r"(?i)\bi\s?tem\s*1\s*\.?\s*(?:a|\(a\))(?![a-z0-9])")
_RELAXED_END = re.compile(
    r"(?i)\bi\s?tem\s*1\s*\.?\s*(?:[bc]|\([bc]\))(?![a-z0-9])"
    r"|\bi\s?tem\s*2(?![0-9])\s*[.:|(]"
)


def _extract_item_1a(html: str) -> str | None:
    """Item 1A text. The strict pattern runs first so every filing it already
    parsed extracts byte-identically; the relaxed one only rescues misses."""
    text = _strip_html(html)
    return _longest_span(text, _STRICT_START, _STRICT_END) or _longest_span(
        text, _RELAXED_START, _RELAXED_END
    )


def _longest_span(text: str, start_re: re.Pattern[str], end_re: re.Pattern[str]) -> str | None:
    starts = [m.start() for m in start_re.finditer(text)]
    ends = [m.start() for m in end_re.finditer(text)]
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
