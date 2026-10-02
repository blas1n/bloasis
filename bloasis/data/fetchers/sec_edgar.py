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
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, NotRequired, TypedDict

logger = logging.getLogger(__name__)

USER_AGENT = "BSVibe Bloasis Research bloasis@bsvibe.dev"
# Extracted Item 1A text is cached per filing and the filing never changes,
# so a parser fix would never reach a text already on disk. The cache is
# keyed by this version — bump it whenever `_extract_item_1a` changes what
# it returns. "v2" = heading-anchored span (issue #83); the unversioned
# files below it are the pre-#83 spans, left for rollback.
ITEM_1A_PARSER_VERSION = "v2"
BASE_DELAY = 0.15  # 10 req/sec cap → 0.15s headroom
DEFAULT_MAX_AGE_HOURS = 24
# SEC throttling answers: once seen, more requests this run only dig deeper.
_THROTTLED = (403, 429)


class TenKFiling(TypedDict):
    accession: str  # "0000320193-25-000079"
    primary_doc: str  # "aapl-20250927.htm"
    filed: date
    period: date  # report period end (fiscal year end)
    cik: NotRequired[str]  # registrant whose archive holds the filing


# Forms by which a new registrant takes over a predecessor's registration
# (Exchange Act Rule 12g-3). Amendments keep the evidence.
_SUCCESSION_FORMS = frozenset({"8-K12B", "8-K12B/A", "8-K12G3", "8-K12G3/A"})


def _normalize_cik(value: object) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError(f"CIK must be up to 10 digits, got {value!r}")
    return text.zfill(10)


@dataclass(frozen=True)
class CikSuccession:
    """`successor_cik` took over `predecessor_cik`'s registration.

    EDGAR's submissions JSON has no predecessor field, so the link is
    declared here and cites the successor's 8-K12B / 8-K12G3. It is followed
    only while the successor's own submissions list that accession under a
    succession form — never because a ticker used to map elsewhere, since
    tickers get reused by unrelated companies (issue #75).
    """

    # YAML spells a CIK as a bare number; pydantic reads this when the
    # table comes from config.
    __pydantic_config__ = {"coerce_numbers_to_str": True, "extra": "forbid"}

    successor_cik: str
    predecessor_cik: str
    evidence_accession: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "successor_cik", _normalize_cik(self.successor_cik))
        object.__setattr__(self, "predecessor_cik", _normalize_cik(self.predecessor_cik))


# ExxonMobil Holdings Corp (2115436) became the successor registrant of
# Exxon Mobil Corp (34088) in the 2026-07-01 redomiciliation merger; its
# 8-K12B says so under Rule 12g-3(a). Every Exxon 10-K through 2026-02-18
# is filed under 34088.
#
# Deliberately absent: Paramount Skydance (PSKY, 2041610) over Paramount
# Global (813828). Its 8-K12B names Paramount Global as sole predecessor and
# would pass verification, but it is a merger of two businesses, not one
# company re-registering — the rolling cosine would compare different firms'
# risk factors (0.720, rank 482/483). Founder decision 2026-10-02 (#82).
DEFAULT_SUCCESSIONS: tuple[CikSuccession, ...] = (
    CikSuccession(
        successor_cik="0002115436",
        predecessor_cik="0000034088",
        evidence_accession="0001193125-26-291990",
    ),
)


@dataclass(frozen=True)
class TickerRename:
    """A constituent source still lists `listed`; the company trades as `current`.

    Index constituent lists lag ticker changes and carry no CIK, so the link
    is declared here and cites an SEC filing whose cover page shows
    `current` as the registrant's trading symbol (issue #80). It is followed
    only while SEC's current ticker map says `current` belongs to `cik` and
    `listed` belongs to no other registrant — never by name matching.

    `current` is the canonical symbol from then on: data fetches, candidates,
    broker orders and the paper session DB all use it, since it is the only
    one the broker trades and reports positions under.
    """

    # YAML spells a CIK as a bare number; pydantic reads this when the
    # table comes from config.
    __pydantic_config__ = {"coerce_numbers_to_str": True, "extra": "forbid"}

    listed: str
    current: str
    cik: str
    evidence_accession: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "listed", self.listed.strip().upper())
        object.__setattr__(self, "current", self.current.strip().upper())
        object.__setattr__(self, "cik", _normalize_cik(self.cik))


# EchoStar Corp (CIK 1415404) moved from SATS to ECHO on Nasdaq in June 2026:
# its 8-K 0001415404-26-000027 (filed 2026-06-18) lists "SATS" as the trading
# symbol, the next one, 0001415404-26-000030 (filed 2026-06-25), lists "ECHO".
# The fja05680 S&P 500 list still prints SATS.
DEFAULT_TICKER_RENAMES: tuple[TickerRename, ...] = (
    TickerRename(
        listed="SATS",
        current="ECHO",
        cik="0001415404",
        evidence_accession="0001415404-26-000030",
    ),
    # Historical S&P 500 constituents listed under a retired ticker (#103),
    # verified 2026-10-02. For each: SEC's ticker map gives the current
    # symbol to this CIK, the CIK itself filed 10-Ks while the old ticker was
    # in the index, the old ticker belongs to no other registrant today, and
    # the cited 10-K tags the current symbol as dei:TradingSymbol on its
    # cover. Excluded on purpose: new registrants (PX->Linde, KRFT->KHC,
    # MYL->VTRS, HFC->DINO), re-issued equity (ESV->VAL), another share class
    # (DISCK), successors that no longer trade (CBS/VIAC, CDAY), and
    # spin-off look-alikes (BXLT is not BAX).
    TickerRename(
        listed="ANTM",
        current="ELV",
        cik="0001156039",
        evidence_accession="0001156039-26-000013",
    ),  # Elevance Health, Inc.
    TickerRename(
        listed="BLL",
        current="BALL",
        cik="0000009389",
        evidence_accession="0001104659-26-017410",
    ),  # BALL Corp
    TickerRename(
        listed="ABC",
        current="COR",
        cik="0001140859",
        evidence_accession="0001140859-25-000131",
    ),  # Cencora, Inc.
    TickerRename(
        listed="FB",
        current="META",
        cik="0001326801",
        evidence_accession="0001628280-26-003942",
    ),  # Meta Platforms, Inc.
    TickerRename(
        listed="PKI",
        current="RVTY",
        cik="0000031791",
        evidence_accession="0000031791-26-000012",
    ),  # REVVITY, INC.
    TickerRename(
        listed="HCP",
        current="DOC",
        cik="0000765880",
        evidence_accession="0001628280-26-005044",
    ),  # HEALTHPEAK PROPERTIES, INC.
    TickerRename(
        listed="PEAK",
        current="DOC",
        cik="0000765880",
        evidence_accession="0001628280-26-005044",
    ),  # HEALTHPEAK PROPERTIES, INC.
    TickerRename(
        listed="JEC",
        current="J",
        cik="0000052988",
        evidence_accession="0001628280-25-053316",
    ),  # JACOBS SOLUTIONS INC.
    TickerRename(
        listed="KORS",
        current="CPRI",
        cik="0001530721",
        evidence_accession="0001530721-26-000047",
    ),  # Capri Holdings Ltd
    TickerRename(
        listed="SYMC",
        current="GEN",
        cik="0000849399",
        evidence_accession="0000849399-26-000017",
    ),  # Gen Digital Inc.
    TickerRename(
        listed="NLOK",
        current="GEN",
        cik="0000849399",
        evidence_accession="0000849399-26-000017",
    ),  # Gen Digital Inc.
    TickerRename(
        listed="UTX",
        current="RTX",
        cik="0000101829",
        evidence_accession="0000101829-26-000006",
    ),  # RTX Corp
    TickerRename(
        listed="WLTW",
        current="WTW",
        cik="0001140536",
        evidence_accession="0001193125-26-069307",
    ),  # WILLIS TOWERS WATSON PLC
    TickerRename(
        listed="FLT",
        current="CPAY",
        cik="0001175454",
        evidence_accession="0001175454-26-000018",
    ),  # CORPAY, INC.
    TickerRename(
        listed="GPS",
        current="GAP",
        cik="0000039911",
        evidence_accession="0001628280-26-018573",
    ),  # GAP INC
    TickerRename(
        listed="ARNC",
        current="HWM",
        cik="0000004281",
        evidence_accession="0000004281-26-000012",
    ),  # Howmet Aerospace Inc.
    TickerRename(
        listed="BHGE",
        current="BKR",
        cik="0001701605",
        evidence_accession="0001701605-26-000007",
    ),  # Baker Hughes Co
    TickerRename(
        listed="DWDP",
        current="DD",
        cik="0001666700",
        evidence_accession="0001666700-26-000013",
    ),  # DuPont de Nemours, Inc.
    TickerRename(
        listed="CTL",
        current="LUMN",
        cik="0000018926",
        evidence_accession="0000018926-26-000014",
    ),  # Lumen Technologies, Inc.
    TickerRename(
        listed="HRS",
        current="LHX",
        cik="0000202058",
        evidence_accession="0000202058-26-000015",
    ),  # L3HARRIS TECHNOLOGIES, INC. /DE/
    TickerRename(
        listed="RE",
        current="EG",
        cik="0001095073",
        evidence_accession="0001095073-26-000006",
    ),  # EVEREST GROUP, LTD.
    TickerRename(
        listed="TMK",
        current="GL",
        cik="0000320335",
        evidence_accession="0000320335-26-000090",
    ),  # GLOBE LIFE INC.
    TickerRename(
        listed="ADS",
        current="BFH",
        cik="0001101215",
        evidence_accession="0001101215-26-000016",
    ),  # BREAD FINANCIAL HOLDINGS, INC.
    TickerRename(
        listed="FBHS",
        current="FBIN",
        cik="0001519751",
        evidence_accession="0001193125-26-063960",
    ),  # Fortune Brands Innovations, Inc.
    TickerRename(
        listed="DISCA",
        current="WBD",
        cik="0001437107",
        evidence_accession="0001437107-26-000020",
    ),  # Warner Bros. Discovery, Inc.
)


def resolve_current_symbols(
    symbols: Iterable[str],
    renames: Iterable[TickerRename],
    cik_of: Callable[[str], str | None],
) -> list[str]:
    """Map listed constituents to the symbol they trade under today.

    `cik_of` is SEC's current ticker → CIK map (`EdgarClient.cik`). It is
    consulted only for symbols in `renames`; a rename it does not confirm,
    or a failed lookup, leaves the listed symbol as is. Order is kept and a
    symbol listed under both names appears once.
    """
    by_listed = {r.listed: r for r in renames}
    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        resolved = symbol
        rename = by_listed.get(symbol.upper())
        if rename is not None:
            try:
                confirmed = cik_of(rename.current) == rename.cik and cik_of(rename.listed) in (
                    None,
                    rename.cik,
                )
            except Exception as exc:  # noqa: BLE001 — any SEC map failure
                logger.warning(
                    "ticker_rename_unverified listed=%s current=%s error=%r",
                    rename.listed,
                    rename.current,
                    exc,
                )
                confirmed = False
            else:
                if not confirmed:
                    logger.warning(
                        "ticker_rename_refused listed=%s current=%s cik=%s: "
                        "SEC ticker map does not confirm it",
                        rename.listed,
                        rename.current,
                        rename.cik,
                    )
            if confirmed:
                resolved = rename.current
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


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
    - risk_factors/{parser_version}/{cik}_{accession}.txt — extracted Item 1A
      text. Immutable per parser version: the filing never changes, so a
      parser fix only reaches a cached text through a new version directory
      (issue #83).
    """

    def __init__(
        self,
        cache_dir: Path | str,
        *,
        max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
        successions: Iterable[CikSuccession] = (),
    ) -> None:
        self._root = Path(cache_dir).expanduser() / "edgar"
        (self._root / "filings").mkdir(parents=True, exist_ok=True)
        (self._root / "risk_factors" / ITEM_1A_PARSER_VERSION).mkdir(parents=True, exist_ok=True)
        self._tickers: dict[str, str] | None = None
        self._max_age_s = max_age_hours * 3600
        self._refresh_disabled = False
        self._predecessors: dict[str, CikSuccession] = {s.successor_cik: s for s in successions}

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

    def sic(self, ticker: str) -> str | None:
        """The registrant's 4-digit SIC code from its submissions snapshot.

        Resolves the ticker exactly as `list_10k` does, so the sector and the
        10-K text describe the same company. None for an unknown ticker or a
        blank code.
        """
        cik = self.cik(ticker)
        if cik is None:
            return None
        sub, _mtime = self._submissions(cik)
        code = str(sub.get("sic") or "").strip()
        return code or None

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

        When the ticker's CIK is a declared, verified successor
        (`CikSuccession`), the predecessor's 10-Ks are included, so a
        reorganized issuer keeps its history until it files its own.
        """
        cik = self.cik(ticker)
        if cik is None:
            return []
        # Page boundaries shift as new filings arrive, so a snapshot cached
        # earlier can overlap a page fetched later — and a 10-K filed jointly
        # by a successor and its predecessor sits in both registrants'
        # submissions. Keep each accession once, the newest registrant's copy.
        by_accession: dict[str, TenKFiling] = {}
        seen: set[str] = set()
        current: str | None = cik
        while current is not None and current not in seen:
            seen.add(current)
            blocks = self._submission_blocks(current, since)
            for block in blocks:
                for row in _tenk_rows(block, current):
                    by_accession.setdefault(row["accession"], row)
            current = self._verified_predecessor(current, blocks)
        out = list(by_accession.values())
        # sort by filing date descending
        out.sort(key=lambda f: f["filed"], reverse=True)
        return out

    def _submission_blocks(self, cik: str, since: date | None) -> list[dict[str, list[str]]]:
        sub, snapshot_mtime = self._submissions(cik)
        filings = sub.get("filings", {})
        blocks: list[dict[str, list[str]]] = [filings.get("recent", {})]
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
        return blocks

    def _verified_predecessor(self, cik: str, blocks: list[dict[str, list[str]]]) -> str | None:
        """Predecessor CIK when `cik` has a declared succession whose cited
        filing its own submissions list under a succession form."""
        succession = self._predecessors.get(cik)
        if succession is None:
            return None
        for block in blocks:
            accessions = block.get("accessionNumber", [])
            forms = block.get("form", [])
            for accession, form in zip(accessions, forms, strict=False):
                if accession == succession.evidence_accession and form in _SUCCESSION_FORMS:
                    return succession.predecessor_cik
        logger.warning(
            "edgar_succession_unverified successor=%s predecessor=%s evidence=%s",
            cik,
            succession.predecessor_cik,
            succession.evidence_accession,
        )
        return None

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
        # A successor's history includes filings in the predecessor's archive.
        cik = filing.get("cik") or self.cik(ticker)
        if cik is None:
            return None
        acc_clean = filing["accession"].replace("-", "")
        cache = self._root / "risk_factors" / ITEM_1A_PARSER_VERSION / f"{cik}_{acc_clean}.txt"
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


def _tenk_rows(block: dict[str, list[str]], cik: str) -> list[TenKFiling]:
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
                cik=cik,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Item 1A parser — anchors the section on its heading (issue #83).
#
# The old rule maximized `end - start` over every (start, nearest-end) pair.
# `_STRICT_START` also matches a cross-reference ("the risks described in
# Item 1A. Risk Factors"), and forward-looking-statements boilerplate carries
# one *before* Item 1 Business, so the longest span systematically won and
# swallowed the business description and the officer table. Measured on
# PARA FY2021-FY2024 and PSKY FY2025, every span started in that paragraph.
#
# Replacement, in order:
#   1. Parse block-aware text (`_block_text`), where a block-level tag
#      boundary is a newline, and collapse whitespace only on the extracted
#      slice — `_collapse_whitespace(_block_text(html)) == _strip_html(html)`
#      (guarded by a test), so a filing the old rule already read correctly
#      extracts byte-identically (issue #73).
#   2. A start counts only where it begins a line, preceded by heading noise
#      at most (page label, "PART I", "Table of Contents"). A mid-sentence
#      cross-reference can no longer anchor the span.
#   3. The terminator is the next `Item 1B` / `1C` / `2` *heading* too — a
#      mid-sentence "see Part I, Item 2. Management's Discussion" ended the
#      span after 738 chars for UHS FY2022 and 9,904 for AMGN FY2024, and
#      ALB sat at 780 chars for five straight years. A filing that styles no
#      terminator on its own line falls back to the next occurrence
#      anywhere (CEG FY2023).
#   4. Reject a candidate whose span contains an `Item 1 ... Business`
#      heading — this drops a table-of-contents entry whose nearest
#      terminator is the real Item 1B far downstream.
#   5. Only among the survivors does the longest span win; length is a
#      tie-break between heading-anchored candidates (a running header
#      repeating "Item 1A. Risk Factors" mid-section yields a shorter one),
#      never the reason a candidate is chosen.
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
# An Item 1 Business heading inside a span means the span opened before the
# business section: "Item 1. Business", "ITEM 1 - BUSINESS", "I TEM 1: BUSINESS".
_ITEM_1_BUSINESS = re.compile(r"(?i)\bi\s?tem\s*1\s*[.:)\-–—]*\s*business\b")
_MIN_SECTION_CHARS = 500

# Block-level markup — what the filer's layout renders as a line break, and
# therefore where a heading can start. `span` is excluded on purpose: CHD's
# drop-cap heading is spans inside one line ("I TEM 1A").
_BLOCK_TAG = re.compile(
    r"(?is)</?(?:p|div|br|hr|tr|td|th|table|tbody|thead|caption|h[1-6]|li|ul|ol|section)\b[^>]*>"
)
# Everything a heading is allowed to share its line with: page labels
# ("I-13", "F-2", "14"), roman numerals, and running-header words.
_HEADING_NOISE_WORDS = frozenset(
    {
        "table",
        "of",
        "contents",
        "content",
        "index",
        "page",
        "part",
        "item",
        "items",
        "continued",
        "cont",
        "form",
        "10",
        "k",
        "annual",
        "report",
    }
)
_PAGE_LABEL = re.compile(r"(?i)[a-z]?-?\d+|[ivxlcdm]{1,7}|10-k")
_WORD = re.compile(r"[\w\-]+")
_MAX_HEADING_PREFIX_CHARS = 60


def _extract_item_1a(html: str) -> str | None:
    """Item 1A text, anchored on the section heading.

    The strict spellings run first so every filing the strict pattern
    already parsed extracts byte-identically; the relaxed ones (issue #70)
    only rescue misses.
    """
    text = _block_text(html)
    span = _section_span(text, _STRICT_START, _STRICT_END) or _section_span(
        text, _RELAXED_START, _RELAXED_END
    )
    if span is None:
        return None
    return _collapse_whitespace(text[span[0] : span[1]])


def _section_span(
    text: str, start_re: re.Pattern[str], end_re: re.Pattern[str]
) -> tuple[int, int] | None:
    """Widest heading-anchored span that holds no Item 1 Business heading."""
    ends = [m.start() for m in end_re.finditer(text)]
    heading_ends = [e for e in ends if _starts_a_line(text, e)]
    best: tuple[int, int] | None = None
    for match in start_re.finditer(text):
        s = match.start()
        if not _starts_a_line(text, s):
            continue  # a cross-reference inside a sentence, not a heading
        # The section ends at the next terminator *heading*; a filing that
        # styles none on its own line (CEG FY2023) falls back to the next
        # occurrence anywhere.
        after = [e for e in heading_ends if e > s] or [e for e in ends if e > s]
        if not after:
            continue
        e = min(after)
        if e - s < _MIN_SECTION_CHARS:
            continue
        if _holds_item_1_business(text, s, e):
            continue
        if best is None or e - s > best[1] - best[0]:
            best = (s, e)
    return best


def _holds_item_1_business(text: str, start: int, end: int) -> bool:
    """True when `Item 1 Business` opens a line inside [start, end).

    Only a heading counts — Item 1A text may cross-reference Item 1 in
    prose, and that must not reject the real section.
    """
    return any(
        _starts_a_line(text, start + m.start()) for m in _ITEM_1_BUSINESS.finditer(text[start:end])
    )


def _starts_a_line(text: str, pos: int) -> bool:
    """True when nothing but heading noise precedes `pos` on its line."""
    prefix = text[text.rfind("\n", 0, pos) + 1 : pos].strip()
    if not prefix:
        return True
    if len(prefix) > _MAX_HEADING_PREFIX_CHARS:
        return False
    return all(
        word.lower() in _HEADING_NOISE_WORDS or _PAGE_LABEL.fullmatch(word)
        for word in _WORD.findall(prefix)
    )


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
    return _collapse_whitespace(text)


def _block_text(html: str) -> str:
    """`_strip_html` with one newline wherever the layout breaks a line."""
    text = _BLOCK_TAG.sub("\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    for k, v in _HTML_ENTITIES.items():
        text = text.replace(k, v)
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r" ?\n[\s\n]*", "\n", text)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text)
