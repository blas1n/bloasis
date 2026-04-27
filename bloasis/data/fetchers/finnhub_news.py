"""Finnhub-backed news headline fetcher.

Free-tier policy:
    60 calls / minute, 1 year of historical headlines.

We respect both via:
- `RateLimiter` for in-process throttling.
- `news_sentiment_cache` table TTL (configured via
  `data.sentiment_cache_max_age_hours`) so warm starts skip network.

The fetcher writes headline metadata to `news_sentiment_cache` only when
the sentiment scorer attaches a score. Raw fetch results live in memory
within this module — they're cheap to refetch and clutter the DB if
persisted unscored.

Limitation L005 — see `docs/limitations.md`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from bloasis.data.fetchers._rate_limit import RateLimiter
from bloasis.data.fetchers.protocols import NewsItem


class FinnhubNewsFetcher:
    """News fetcher using `finnhub-python`'s `company_news` endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_per_minute: int = 60,
        client: object | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is required")
        self._client = client or self._make_client(api_key)
        self._limiter = RateLimiter(max_calls=rate_per_minute, period_seconds=60)

    @staticmethod
    def _make_client(api_key: str) -> object:
        import finnhub

        return finnhub.Client(api_key=api_key)

    def fetch(self, symbol: str, since: datetime) -> list[NewsItem]:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        now = datetime.now(tz=UTC)
        if since > now:
            raise ValueError(f"since={since} is in the future")

        self._limiter.acquire()
        # finnhub-python returns a list of dicts. Sync call; `getattr` to
        # keep the type-stubless import isolated.
        client_call = cast(
            object, getattr(self._client, "company_news")
        )
        raw = cast(
            list[dict[str, Any]],
            client_call(  # type: ignore[operator]
                symbol,
                _from=since.date().isoformat(),
                to=now.date().isoformat(),
            ),
        )
        return [self._parse_item(symbol, entry) for entry in raw]

    @staticmethod
    def _parse_item(symbol: str, entry: dict[str, Any]) -> NewsItem:
        ts = entry.get("datetime")
        published = (
            datetime.fromtimestamp(int(ts), tz=UTC) if ts else datetime.now(tz=UTC)
        )
        return NewsItem(
            symbol=symbol.upper(),
            published_at=published,
            headline=str(entry.get("headline") or "").strip(),
            url=str(entry.get("url") or ""),
            source=(str(entry.get("source")) if entry.get("source") else None),
        )


# ----- helpers shared with sentiment scorer cache writes -----

def serialize_headlines(items: list[NewsItem]) -> str:
    """JSON-encode items for `news_sentiment_cache.headlines_json`."""
    return json.dumps(
        [
            {
                "published_at": i.published_at.isoformat(),
                "headline": i.headline,
                "url": i.url,
                "source": i.source,
            }
            for i in items
        ],
        ensure_ascii=False,
    )
