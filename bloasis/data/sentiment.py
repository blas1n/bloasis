"""LLM-based news sentiment scorer.

Pipeline:
    1. Fetch recent headlines from a `NewsFetcher`.
    2. Check `news_sentiment_cache` (DB) for a fresh score.
    3. If miss, send headlines to LiteLLM with a structured JSON prompt.
    4. Parse the response, persist to cache, return.

The scorer is decoupled from the data layer's caching primitives because
the sentiment cache lives in SQLite (auditability) rather than parquet
(price data). Each cache row stores both the score and the raw headlines
list as JSON, so we can audit "what did the LLM see when it returned -0.3
for AAPL on day X?".

Output range: [-1.0, +1.0]. Negative = bearish, positive = bullish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, insert, select

from bloasis.data.fetchers.finnhub_news import serialize_headlines
from bloasis.data.fetchers.protocols import NewsFetcher, NewsItem
from bloasis.runtime.llm import LLMSettings, complete
from bloasis.storage import news_sentiment_cache

SYSTEM_PROMPT = (
    "You score the aggregate market sentiment of news headlines about a "
    "single stock. Output one JSON object: "
    '{"score": <float in [-1.0, 1.0]>, "rationale": <short string>}. '
    "Negative = bearish, 0 = neutral, positive = bullish. "
    "Be conservative; only assign |score| > 0.5 when headlines are clearly "
    "and consistently directional."
)


@dataclass(frozen=True, slots=True)
class SentimentResult:
    symbol: str
    score: float
    article_count: int
    rationale: str
    fetched_at: datetime


class SentimentScorer:
    def __init__(
        self,
        news_fetcher: NewsFetcher,
        db_engine: Engine,
        *,
        cache_ttl_hours: int = 6,
        lookback_days: int = 7,
        llm_settings: LLMSettings | None = None,
    ) -> None:
        self._news = news_fetcher
        self._db = db_engine
        self._ttl = timedelta(hours=cache_ttl_hours)
        self._lookback = timedelta(days=lookback_days)
        self._llm = llm_settings

    def score(self, symbol: str, *, force_refresh: bool = False) -> SentimentResult:
        symbol = symbol.upper()
        now = datetime.now(tz=UTC)

        if not force_refresh:
            cached = self._read_cache(symbol, now)
            if cached is not None:
                return cached

        items = self._news.fetch(symbol, since=now - self._lookback)
        if not items:
            result = SentimentResult(
                symbol=symbol,
                score=0.0,
                article_count=0,
                rationale="no recent headlines",
                fetched_at=now,
            )
            self._write_cache(symbol, result, items)
            return result

        score, rationale = self._call_llm(symbol, items)
        result = SentimentResult(
            symbol=symbol,
            score=score,
            article_count=len(items),
            rationale=rationale,
            fetched_at=now,
        )
        self._write_cache(symbol, result, items)
        return result

    # ---- LLM ----

    def _call_llm(self, symbol: str, items: list[NewsItem]) -> tuple[float, str]:
        prompt = _build_prompt(symbol, items)
        raw = complete(
            prompt,
            system_prompt=SYSTEM_PROMPT,
            settings=self._llm,
            response_format="json",
            max_tokens=400,
            temperature=0.0,
        )
        return _parse_response(raw)

    # ---- DB cache ----

    def _read_cache(self, symbol: str, now: datetime) -> SentimentResult | None:
        stmt = (
            select(
                news_sentiment_cache.c.score,
                news_sentiment_cache.c.article_count,
                news_sentiment_cache.c.fetched_at,
                news_sentiment_cache.c.expires_at,
            )
            .where(news_sentiment_cache.c.symbol == symbol)
            .order_by(news_sentiment_cache.c.fetched_at.desc())
            .limit(1)
        )
        with self._db.connect() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            return None
        # SQLite drops tzinfo round-trip; restore to UTC for comparison.
        expires_at = _ensure_utc(row.expires_at)
        if expires_at <= now:
            return None
        return SentimentResult(
            symbol=symbol,
            score=row.score,
            article_count=row.article_count,
            rationale="(cached)",
            fetched_at=_ensure_utc(row.fetched_at),
        )

    def _write_cache(
        self,
        symbol: str,
        result: SentimentResult,
        items: list[NewsItem],
    ) -> None:
        with self._db.begin() as conn:
            conn.execute(
                insert(news_sentiment_cache).values(
                    symbol=symbol,
                    fetched_at=result.fetched_at,
                    score=result.score,
                    article_count=result.article_count,
                    headlines_json=serialize_headlines(items),
                    expires_at=result.fetched_at + self._ttl,
                )
            )


def _ensure_utc(dt: datetime) -> datetime:
    """Restore tz info on a naive datetime (SQLite drops tzinfo round-trip)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _build_prompt(symbol: str, items: list[NewsItem]) -> str:
    lines = [f"Symbol: {symbol}", "", "Headlines (most recent first):"]
    # Keep prompt compact: top 20 headlines, oldest at bottom.
    sorted_items = sorted(items, key=lambda i: i.published_at, reverse=True)[:20]
    for i in sorted_items:
        lines.append(f"- [{i.published_at.date().isoformat()}] {i.headline}")
    lines.append("")
    lines.append("Return JSON with `score` and `rationale` only.")
    return "\n".join(lines)


def _parse_response(raw: str) -> tuple[float, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"sentiment LLM returned non-JSON: {raw!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"sentiment JSON must be an object, got: {data!r}")
    score = data.get("score")
    rationale = data.get("rationale", "")
    try:
        score_f = float(score)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"sentiment score not numeric: {score!r}") from exc
    score_f = max(-1.0, min(1.0, score_f))
    return score_f, str(rationale)
