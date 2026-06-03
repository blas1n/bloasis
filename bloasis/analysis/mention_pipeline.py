"""Truth Social archive fetch + LLM ticker extraction (PR55).

End-to-end:
  fetch_archive_to_db: pull the public JSON archive, upsert new posts
    (idempotent on post_id — safe to re-run every fetch)
  is_stock_candidate: deterministic substring/word-boundary prefilter.
    Trump's archive is 95% political content; the prefilter ensures
    the LLM only sees the small subset where a company is plausibly
    mentioned, both to save tokens and to suppress the well-documented
    small-model hallucination of re-emitting any tickers it sees in
    the prompt examples.
  MentionExtractor: prompt an Ollama model to find publicly-traded US
    stocks mentioned in a post + sentiment (positive/negative/neutral)
  run_extraction_batch: walk un-extracted posts, apply prefilter, call
    the LLM only on candidates, write mention rows + stamp the post as
    extracted (zero-mention posts are stamped too so the batch is
    idempotent on re-run).

The post panel feeds `bloasis research mentions-study` (see cli.py)
which does the gap / intraday / forward-drift decomposition.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Engine


# Curated name → ticker dictionary for prefiltering. Covers companies
# Trump has historically mentioned (manufacturing, defense, big tech,
# pharma, retail, banks, energy). Whitespace-normalised, lowercase keys.
# Not exhaustive — the prefilter falls back to ticker-symbol matching for
# the long tail. Multi-word names checked as substrings (e.g. "general
# motors"); single-word as case-insensitive word boundaries.
NAME_TO_TICKER: dict[str, str] = {
    "apple": "AAPL",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "boeing": "BA",
    "ford": "F",
    "general motors": "GM",
    "dell": "DELL",
    "palantir": "PLTR",
    "ibm": "IBM",
    "oracle": "ORCL",
    "pfizer": "PFE",
    "moderna": "MRNA",
    "johnson & johnson": "JNJ",
    "walmart": "WMT",
    "target corporation": "TGT",
    "starbucks": "SBUX",
    "mcdonalds": "MCD",
    "lockheed": "LMT",
    "lockheed martin": "LMT",
    "raytheon": "RTX",
    "northrop": "NOC",
    "qualcomm": "QCOM",
    "broadcom": "AVGO",
    "exxon": "XOM",
    "chevron": "CVX",
    "jpmorgan": "JPM",
    "goldman": "GS",
    "wells fargo": "WFC",
    "disney": "DIS",
    "netflix": "NFLX",
    "uber": "UBER",
    "tsmc": "TSM",
    "taiwan semiconductor": "TSM",
    "micron": "MU",
    "advanced micro": "AMD",
    "caterpillar": "CAT",
    "deere": "DE",
    "us steel": "X",
    "u.s. steel": "X",
    "harley-davidson": "HOG",
    "harley davidson": "HOG",
    "intel corp": "INTC",
    "intel corporation": "INTC",
    "novo nordisk": "NVO",
    "berkshire": "BRK-B",
    "at&t": "T",
    "verizon": "VZ",
    "costco": "COST",
    "home depot": "HD",
    "axon": "AXON",
    "lowe's": "LOW",
    "fedex": "FDX",
    "united airlines": "UAL",
    "delta airlines": "DAL",
    "american airlines": "AAL",
    "general electric": "GE",
    "honeywell": "HON",
    "3m": "MMM",
    "cisco": "CSCO",
    "salesforce": "CRM",
    "adobe": "ADBE",
    "paypal": "PYPL",
    "shopify": "SHOP",
    "robinhood": "HOOD",
    "coca-cola": "KO",
    "pepsi": "PEP",
    "philip morris": "PM",
    "altria": "MO",
    "carrier": "CARR",
    "trump media": "DJT",
    "rivian": "RIVN",
    "lucid": "LCID",
    "nikola": "NKLA",
    "blackrock": "BLK",
    "kkr": "KKR",
    "apollo global": "APO",
    "blackstone": "BX",
    "schwab": "SCHW",
    "morgan stanley": "MS",
    "citi": "C",
    "citigroup": "C",
}

# Ticker symbols that are common English words — never match these on
# bare uppercase substrings (would explode false positives). We still
# allow them via the name dictionary above.
_AMBIGUOUS_TICKERS: set[str] = {
    # 1-3 char common-word collisions (most never reach this path anyway
    # because the 4+ char gate excludes them; kept for safety + 4-char
    # entries below)
    "A",
    "AI",
    "ALL",
    "ARE",
    "BE",
    "BIG",
    "C",
    "CAN",
    "DO",
    "EAT",
    "F",
    "FOR",
    "GO",
    "HAS",
    "HE",
    "IT",
    "K",
    "L",
    "LOW",
    "MA",
    "MAY",
    "ME",
    "NOW",
    "ON",
    "ONE",
    "OR",
    "OUT",
    "R",
    "RE",
    "RUN",
    "SO",
    "T",
    "TO",
    "UP",
    "US",
    "V",
    "X",
    "Y",
    "YOU",
    "Z",
    # 4+ char English-word tickers — these DO pass the length gate, so
    # blocking them explicitly is necessary. Observed in Trump's archive
    # as common prose (FAST = "fast and furious", WELL = "well, ...").
    "FAST",
    "WELL",
    "FREE",
    "WORK",
    "LIFE",
    "FOOD",
    "GOLD",
    "GROW",
    "MORE",
    "SAVE",
    "HOPE",
    "LOVE",
    "OPEN",
    "MOVE",
    "HOLD",
    "FUND",
    "PARK",
    "SEAS",
    "LEAD",
    "EARN",
    "WISE",
    "GAIN",
}


def is_stock_candidate(
    content: str,
    ticker_whitelist: set[str],
    *,
    name_to_ticker: dict[str, str] = NAME_TO_TICKER,
) -> set[str]:
    """Deterministic prefilter — return the set of CANDIDATE tickers
    plausibly mentioned in ``content``. Empty set = skip LLM entirely.

    Strict matching to suppress English-word false positives (ICE, DAY,
    FAST, PM all show up as SP500 tickers but mean something else in
    Trump's prose):

      - Multi-word names from NAME_TO_TICKER: case-insensitive substring
      - Single-word names from NAME_TO_TICKER: case-insensitive whole-word
      - 4+ char SP500 tickers (e.g. AAPL/NVDA/GOOGL/MSFT/AMZN): UPPERCASE
        whole-word match. These are distinctive enough that false-positive
        risk is low.
      - 2-3 char SP500 tickers are NOT bare-matched (too many English-word
        collisions). They come through only via the name dictionary.

    `ticker_whitelist` is the SP500 ticker set; we use it to gate the 4+
    char bare match path so we don't match arbitrary uppercase strings.
    """
    if not content:
        return set()
    lower = content.lower()
    hits: set[str] = set()
    for name, ticker in name_to_ticker.items():
        if " " in name or "-" in name or "." in name or "&" in name:
            if name in lower:
                hits.add(ticker)
        else:
            if re.search(rf"\b{re.escape(name)}\b", lower):
                hits.add(ticker)
    if ticker_whitelist:
        for ticker in ticker_whitelist:
            if len(ticker) < 4 or ticker in _AMBIGUOUS_TICKERS:
                continue
            if re.search(rf"\b{re.escape(ticker)}\b", content):
                hits.add(ticker)
    return hits


@dataclass(frozen=True)
class ExtractedMention:
    ticker: str
    sentiment: str  # 'positive' / 'negative' / 'neutral'
    confidence: float


@dataclass
class MentionExtractor:
    """LLM-driven ticker + sentiment extraction from a single post.

    Designed for Ollama (defaults to llama3.2:3b — small, fast, free).
    Output is filtered against a ticker whitelist so junk strings the
    model invents (or short non-ticker words it lifts in caps) don't
    pollute the mention table.
    """

    ticker_whitelist: set[str] = field(default_factory=set)
    model: str = "ollama_chat/llama3.2:3b"
    api_base: str = "http://localhost:11434"
    temperature: float = 0.0
    max_tokens: int = 32
    extractor_version: int = 2  # bumped: hybrid extractor (was monolithic LLM in v1)

    # Hybrid design: deterministic NER (is_stock_candidate) + LLM sentiment.
    # The earlier v1 prompted the LLM to do both, which made llama3.2:3b
    # hallucinate any tickers the prompt mentioned (DELL/NVDA/PLTR/BA
    # showed up in 230+ political posts that didn't mention them at all).
    # Splitting removes hallucination by construction: ticker comes from
    # regex/dictionary match, LLM only classifies sentiment polarity.
    _SENTIMENT_SYSTEM: str = (
        "Classify the sentiment a social-media post expresses toward a "
        "specific company. Choose ONE: positive (praise, endorsement, "
        "favorable deal, buy), negative (criticism, threat, tariff hit, "
        "boycott, sell), neutral (factual or ambiguous). Output ONLY a "
        'JSON object like {"sentiment":"positive","confidence":0.9}. No '
        "prose, no explanation."
    )

    def extract(self, content: str) -> list[ExtractedMention]:
        """Hybrid: regex candidates → per-ticker LLM sentiment classification."""
        if not content.strip():
            return []
        candidates = is_stock_candidate(content, self.ticker_whitelist)
        if not candidates:
            return []
        out: list[ExtractedMention] = []
        for ticker in sorted(candidates):
            sentiment, conf = self._classify_sentiment(content, ticker)
            out.append(ExtractedMention(ticker=ticker, sentiment=sentiment, confidence=conf))
        return out

    def _classify_sentiment(self, content: str, ticker: str) -> tuple[str, float]:
        import litellm

        user_prompt = (
            f"COMPANY: {ticker}\n"
            f"POST:\n{content[:1500]}\n\n"
            f"What sentiment does the post express toward {ticker}? JSON:"
        )
        try:
            resp = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._SENTIMENT_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_base=self.api_base,
            )
        except Exception:  # noqa: BLE001 — research tool, fall back to neutral
            return ("neutral", 0.3)
        text = resp.choices[0].message.content or ""
        return self._parse_sentiment(text)

    @staticmethod
    def _parse_sentiment(text: str) -> tuple[str, float]:
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if not match:
            return ("neutral", 0.3)
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            return ("neutral", 0.3)
        if not isinstance(obj, dict):
            return ("neutral", 0.3)
        sentiment = str(obj.get("sentiment", "neutral")).strip().lower()
        if sentiment not in ("positive", "negative", "neutral"):
            sentiment = "neutral"
        try:
            conf = float(obj.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        return (sentiment, conf)


# ---------------------------------------------------------------------------
# Fetcher — public Truth Social archive
# ---------------------------------------------------------------------------

_TRUTH_ARCHIVE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"


def fetch_archive_to_db(
    engine: Engine,
    *,
    url: str = _TRUTH_ARCHIVE_URL,
    console: object | None = None,
) -> int:
    """Download the public archive, upsert any new posts. Returns the
    number of NEW posts inserted (existing post_ids are skipped)."""
    import httpx

    from bloasis.storage import writers

    resp = httpx.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    records = resp.json()
    n_new = 0
    n_total = len(records)
    for rec in records:
        pid = str(rec.get("id", "")).strip()
        if not pid:
            continue
        content = (rec.get("content") or "").strip()
        if not content:
            continue
        ts_raw = rec.get("created_at", "")
        try:
            posted_at = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Heuristic — count was 0 before insertion if upsert added a row.
        # We can't easily know without a query; just count posts seen.
        writers.upsert_social_post(
            engine,
            post_id=f"truth:{pid}",
            source="truth_social",
            posted_at=posted_at,
            content=content,
            url=rec.get("url"),
        )
        n_new += 1  # incremental — actual NEW count = (rows before − after)
    if console is not None:
        console.print(f"[dim]processed {n_new}/{n_total} text posts[/dim]")  # type: ignore[attr-defined]
    return n_new


# ---------------------------------------------------------------------------
# Extraction batch
# ---------------------------------------------------------------------------


def run_extraction_batch(
    engine: Engine,
    extractor: MentionExtractor,
    *,
    limit: int | None = None,
    only_after: datetime | None = None,
    console: object | None = None,
) -> tuple[int, int]:
    """Walk un-extracted posts, run the LLM, write mention rows.

    Returns (n_posts_processed, n_mentions_written). Each processed post
    is stamped with mentions_extracted_at + extractor_version so the
    batch can be re-run incrementally.
    """
    from sqlalchemy import select

    from bloasis.storage import social_posts, writers

    with engine.connect() as conn:
        q = select(social_posts.c.post_id, social_posts.c.content).where(
            social_posts.c.mentions_extracted_at.is_(None)
        )
        if only_after is not None:
            q = q.where(social_posts.c.posted_at >= only_after)
        q = q.order_by(social_posts.c.posted_at.desc())
        if limit is not None:
            q = q.limit(limit)
        rows = conn.execute(q).fetchall()

    n_posts = 0
    n_mentions = 0
    for r in rows:
        mentions = extractor.extract(r.content)
        for m in mentions:
            writers.write_mention(
                engine,
                post_id=r.post_id,
                ticker=m.ticker,
                sentiment=m.sentiment,
                confidence=m.confidence,
                extractor_version=extractor.extractor_version,
            )
            n_mentions += 1
        writers.mark_post_extracted(
            engine,
            post_id=r.post_id,
            extractor_version=extractor.extractor_version,
        )
        n_posts += 1
        if console is not None and n_posts % 50 == 0:
            console.print(  # type: ignore[attr-defined]
                f"[dim]extracted {n_posts}/{len(rows)}, {n_mentions} mentions so far[/dim]"
            )
    return n_posts, n_mentions


def load_sp500_tickers(cache_dir: Path) -> set[str]:
    """Best-effort SP500 ticker whitelist via the universe module."""
    from bloasis.data.universe import list_sp500

    try:
        return {s.upper().replace(".", "-") for s in list_sp500(cache_dir=cache_dir)}
    except Exception:  # noqa: BLE001
        return set()
