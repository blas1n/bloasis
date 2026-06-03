"""Tests for the deterministic prefilter + hybrid extractor (PR55).

The prefilter is the load-bearing piece that keeps the LLM from being
asked about 15k unrelated political posts. Tests focus on the
false-positive traps observed in the wild:
  - "ICE" / "DAY" / "FAST" — English words that happen to be SP500
    tickers MUST NOT match
  - "intel official" must NOT match Intel Corp (no `intel` in dict)
  - "President DJT" signature must NOT match Trump Media (no `djt` in dict)
"""

from __future__ import annotations

from bloasis.analysis.mention_pipeline import (
    NAME_TO_TICKER,
    MentionExtractor,
    is_stock_candidate,
)

# Simulated SP500 whitelist for tests — includes both safe (4+ char) and
# ambiguous (English-word) tickers so the gate is exercised both ways.
_SP500 = {
    "AAPL",
    "AMZN",
    "NVDA",
    "META",
    "GOOGL",
    "MSFT",
    "PLTR",
    "DELL",
    "BA",
    "INTC",
    "DJT",
    "ICE",
    "FAST",
    "DAY",
    "PM",
    "MAR",
    "X",
    "T",
}


def test_prefilter_passes_curated_name() -> None:
    """Trump's actual Dell endorsement should match via the name dictionary."""
    content = "Buy Dell computers! Great quality!"
    assert is_stock_candidate(content, _SP500) == {"DELL"}


def test_prefilter_passes_uppercase_4plus_char_ticker() -> None:
    """A bare 4+ char ticker mention should still come through."""
    content = "AMZN had a big quarter."
    assert is_stock_candidate(content, _SP500) == {"AMZN"}


def test_prefilter_rejects_short_word_tickers() -> None:
    """ICE, DAY, FAST, PM, MAR — English-word collisions get blocked."""
    content = (
        "The ICE raids on illegal immigrants will continue every DAY. "
        "We move FAST. PM Modi was here. Coming to Mar-a-Lago."
    )
    # None of these should leak through — they all collide with prose.
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_rejects_intel_official() -> None:
    """'intel official' (intelligence) must not match Intel Corp."""
    content = "Ex-intel official said the laptop letter was a deception."
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_rejects_president_djt_signature() -> None:
    """Trump signs many posts 'President DJT' — that's NOT a Trump Media mention."""
    content = "Iran really wants a deal. President DJT"
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_passes_explicit_trump_media() -> None:
    """The multi-word 'trump media' SHOULD match."""
    content = "Today Trump Media announced strong results."
    assert is_stock_candidate(content, _SP500) == {"DJT"}


def test_prefilter_multiple_hits() -> None:
    """A single post can mention multiple companies."""
    content = "Apple and Nvidia are American champions. Boeing builds great planes."
    assert is_stock_candidate(content, _SP500) == {"AAPL", "NVDA", "BA"}


def test_prefilter_case_insensitive_names() -> None:
    """Name dictionary matches case-insensitively (Trump's caps are erratic)."""
    content = "I LOVE APPLE products."
    assert is_stock_candidate(content, _SP500) == {"AAPL"}


def test_prefilter_handles_empty_content() -> None:
    assert is_stock_candidate("", _SP500) == set()


def test_name_dictionary_does_not_include_djt_alone() -> None:
    """Regression — 'djt' alone was removed because Trump signs posts with it."""
    assert "djt" not in NAME_TO_TICKER
    # but the multi-word form is kept
    assert NAME_TO_TICKER.get("trump media") == "DJT"


def test_name_dictionary_does_not_include_intel_alone() -> None:
    """Regression — 'intel' alone was removed (matched 'intel official')."""
    assert "intel" not in NAME_TO_TICKER
    # multi-word form kept
    assert NAME_TO_TICKER.get("intel corp") == "INTC"


# ---------------------------------------------------------------------------
# Hybrid extractor — sentiment-only LLM, deterministic ticker
# ---------------------------------------------------------------------------


def test_extractor_returns_empty_when_no_candidates() -> None:
    """No name / ticker in content → no LLM call, no mentions."""
    ex = MentionExtractor(ticker_whitelist=_SP500)
    assert ex.extract("Crooked Hillary should be in jail!") == []


def test_extractor_parses_sentiment_json() -> None:
    """The sentiment parser tolerates JSON wrapped in prose."""
    sentiment, conf = MentionExtractor._parse_sentiment(
        'Here is the answer: {"sentiment": "positive", "confidence": 0.92}'
    )
    assert sentiment == "positive"
    assert conf == 0.92


def test_extractor_parses_sentiment_falls_back_to_neutral() -> None:
    """Malformed LLM output → neutral, low confidence."""
    s, c = MentionExtractor._parse_sentiment("uhh I'm not sure")
    assert s == "neutral"
    assert c == 0.3


def test_extractor_clamps_invalid_sentiment_label() -> None:
    s, _ = MentionExtractor._parse_sentiment('{"sentiment":"bullish","confidence":0.7}')
    assert s == "neutral"
