"""Tests for `bloasis.data.sentiment`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bloasis.data.fetchers.protocols import NewsItem
from bloasis.data.sentiment import SentimentScorer, _parse_response
from bloasis.runtime.llm import LLMSettings
from bloasis.storage import create_all, get_engine


@pytest.fixture
def db_engine(tmp_path: Path):
    engine = get_engine(tmp_path / "test.db")
    create_all(engine)
    return engine


@pytest.fixture
def llm_settings() -> LLMSettings:
    return LLMSettings(api_key="sk-test", model="m", base_url=None)


def _news_item(symbol: str, headline: str, days_ago: int = 1) -> NewsItem:
    return NewsItem(
        symbol=symbol,
        published_at=datetime.now(tz=UTC) - timedelta(days=days_ago),
        headline=headline,
        url="https://example.com",
        source="Test",
    )


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------


def test_parse_response_clamps_score() -> None:
    score, _ = _parse_response('{"score": 5.0, "rationale": "x"}')
    assert score == 1.0
    score, _ = _parse_response('{"score": -5.0, "rationale": "x"}')
    assert score == -1.0


def test_parse_response_extracts_rationale() -> None:
    score, rationale = _parse_response('{"score": 0.5, "rationale": "bullish"}')
    assert score == 0.5
    assert rationale == "bullish"


def test_parse_response_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="non-JSON"):
        _parse_response("not json")


def test_parse_response_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        _parse_response("[1, 2, 3]")


def test_parse_response_rejects_non_numeric_score() -> None:
    with pytest.raises(ValueError, match="not numeric"):
        _parse_response('{"score": "high", "rationale": "x"}')


# ---------------------------------------------------------------------------
# SentimentScorer.score
# ---------------------------------------------------------------------------


def test_score_no_headlines_returns_neutral(db_engine, llm_settings) -> None:
    fake_news = MagicMock()
    fake_news.fetch.return_value = []

    scorer = SentimentScorer(
        news_fetcher=fake_news,
        db_engine=db_engine,
        cache_ttl_hours=6,
        lookback_days=7,
        llm_settings=llm_settings,
    )
    result = scorer.score("AAPL")
    assert result.score == 0.0
    assert result.article_count == 0
    assert "no recent" in result.rationale


def test_score_calls_llm_with_headlines(db_engine, llm_settings) -> None:
    fake_news = MagicMock()
    fake_news.fetch.return_value = [
        _news_item("AAPL", "Earnings beat"),
        _news_item("AAPL", "New product launch"),
    ]

    with patch(
        "bloasis.data.sentiment.complete",
        return_value='{"score": 0.7, "rationale": "strong"}',
    ) as fake_complete:
        scorer = SentimentScorer(
            news_fetcher=fake_news,
            db_engine=db_engine,
            cache_ttl_hours=6,
            lookback_days=7,
            llm_settings=llm_settings,
        )
        result = scorer.score("AAPL")

    assert result.score == 0.7
    assert result.article_count == 2
    assert result.rationale == "strong"
    # prompt includes both headlines
    prompt = fake_complete.call_args.args[0]
    assert "Earnings beat" in prompt
    assert "New product launch" in prompt


def test_score_writes_cache_on_first_call(db_engine, llm_settings) -> None:
    fake_news = MagicMock()
    fake_news.fetch.return_value = [_news_item("AAPL", "h")]

    with patch(
        "bloasis.data.sentiment.complete",
        return_value='{"score": 0.3, "rationale": "x"}',
    ):
        scorer = SentimentScorer(
            news_fetcher=fake_news,
            db_engine=db_engine,
            llm_settings=llm_settings,
            cache_ttl_hours=6,
        )
        scorer.score("AAPL")

    # Second call should hit cache, not LLM
    with patch("bloasis.data.sentiment.complete") as fake_complete:
        scorer2 = SentimentScorer(
            news_fetcher=fake_news,
            db_engine=db_engine,
            llm_settings=llm_settings,
            cache_ttl_hours=6,
        )
        cached = scorer2.score("AAPL")
        fake_complete.assert_not_called()
    assert cached.score == 0.3
    assert cached.rationale == "(cached)"


def test_score_force_refresh_bypasses_cache(db_engine, llm_settings) -> None:
    fake_news = MagicMock()
    fake_news.fetch.return_value = [_news_item("AAPL", "h")]

    with patch(
        "bloasis.data.sentiment.complete",
        return_value='{"score": 0.3, "rationale": "x"}',
    ):
        scorer = SentimentScorer(
            news_fetcher=fake_news, db_engine=db_engine, llm_settings=llm_settings
        )
        scorer.score("AAPL")

    with patch(
        "bloasis.data.sentiment.complete",
        return_value='{"score": 0.5, "rationale": "y"}',
    ) as fake_complete:
        scorer2 = SentimentScorer(
            news_fetcher=fake_news, db_engine=db_engine, llm_settings=llm_settings
        )
        out = scorer2.score("AAPL", force_refresh=True)
        fake_complete.assert_called_once()
    assert out.score == 0.5
