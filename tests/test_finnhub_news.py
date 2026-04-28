"""Tests for Finnhub news fetcher and rate limiter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from bloasis.data.fetchers._rate_limit import RateLimiter
from bloasis.data.fetchers.finnhub_news import FinnhubNewsFetcher, serialize_headlines
from bloasis.data.fetchers.protocols import NewsItem

# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_below_threshold() -> None:
    sleeper = MagicMock()
    rl = RateLimiter(max_calls=3, period_seconds=10, sleep_func=sleeper)
    for _ in range(3):
        rl.acquire()
    sleeper.assert_not_called()


def test_rate_limiter_sleeps_when_over_threshold() -> None:
    sleeper = MagicMock()
    rl = RateLimiter(max_calls=2, period_seconds=10, sleep_func=sleeper)
    rl.acquire()
    rl.acquire()
    rl.acquire()  # third should sleep
    sleeper.assert_called_once()
    args = sleeper.call_args.args
    assert args[0] > 0


def test_rate_limiter_invalid_args_rejected() -> None:
    with pytest.raises(ValueError):
        RateLimiter(max_calls=0)
    with pytest.raises(ValueError):
        RateLimiter(max_calls=1, period_seconds=0)


# ---------------------------------------------------------------------------
# FinnhubNewsFetcher
# ---------------------------------------------------------------------------


def test_fetcher_requires_api_key() -> None:
    with pytest.raises(ValueError, match="FINNHUB_API_KEY"):
        FinnhubNewsFetcher(api_key="")


def test_fetcher_calls_company_news_with_date_range() -> None:
    now = datetime.now(tz=UTC)
    fake_client = MagicMock()
    fake_client.company_news.return_value = [
        {
            "datetime": int((now - timedelta(days=1)).timestamp()),
            "headline": "Apple reports earnings",
            "url": "https://example.com/a",
            "source": "Reuters",
        },
        {
            "datetime": int((now - timedelta(days=2)).timestamp()),
            "headline": "Apple stock rises",
            "url": "https://example.com/b",
            "source": None,
        },
    ]
    fetcher = FinnhubNewsFetcher(api_key="x", rate_per_minute=60, client=fake_client)
    items = fetcher.fetch("AAPL", since=now - timedelta(days=7))

    assert len(items) == 2
    assert items[0].headline == "Apple reports earnings"
    assert items[0].url == "https://example.com/a"
    assert items[0].source == "Reuters"
    assert items[1].source is None
    fake_client.company_news.assert_called_once()
    kwargs = fake_client.company_news.call_args.kwargs
    assert kwargs.get("_from") == (now - timedelta(days=7)).date().isoformat()


def test_fetcher_rejects_empty_symbol() -> None:
    fake_client = MagicMock()
    fetcher = FinnhubNewsFetcher(api_key="x", client=fake_client)
    with pytest.raises(ValueError, match="non-empty"):
        fetcher.fetch("", since=datetime.now(tz=UTC))


def test_fetcher_rejects_future_since() -> None:
    fake_client = MagicMock()
    fetcher = FinnhubNewsFetcher(api_key="x", client=fake_client)
    future = datetime.now(tz=UTC) + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        fetcher.fetch("AAPL", since=future)


def test_fetcher_handles_missing_datetime_field() -> None:
    fake_client = MagicMock()
    fake_client.company_news.return_value = [{"headline": "no timestamp", "url": "x"}]
    fetcher = FinnhubNewsFetcher(api_key="x", client=fake_client)
    items = fetcher.fetch("AAPL", since=datetime.now(tz=UTC) - timedelta(days=1))
    assert len(items) == 1
    assert items[0].headline == "no timestamp"


# ---------------------------------------------------------------------------
# serialize_headlines
# ---------------------------------------------------------------------------


def test_serialize_headlines_round_trip() -> None:
    import json

    items = [
        NewsItem(
            symbol="AAPL",
            published_at=datetime(2024, 1, 2, tzinfo=UTC),
            headline="Hello",
            url="https://x",
            source="A",
        )
    ]
    s = serialize_headlines(items)
    parsed = json.loads(s)
    assert parsed[0]["headline"] == "Hello"
    assert parsed[0]["source"] == "A"
