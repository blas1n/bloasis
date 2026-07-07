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


# ---------------------------------------------------------------------------
# PR56 — CEO / founder names expansion
#
# Trump rarely says "Amazon" — he says "Bezos". Same for Zuckerberg / META,
# Tim Cook / AAPL, Elon / TSLA, Jensen Huang / NVDA. The v2 dictionary
# missed every CEO-referencing post; v3 adds the names directly. Composite
# PK on extractor_version means re-extraction accumulates new (CEO-
# referencing) mentions without overwriting v2 rows.
# ---------------------------------------------------------------------------


def test_prefilter_matches_bezos_to_amzn() -> None:
    """'Bezos' (Trump's typical Amazon reference) routes to AMZN."""
    content = "Bezos and the Washington Post are at it again."
    assert is_stock_candidate(content, _SP500) == {"AMZN"}


def test_prefilter_matches_zuckerberg_to_meta() -> None:
    content = "Zuckerberg has destroyed our democracy."
    assert is_stock_candidate(content, _SP500) == {"META"}


def test_prefilter_matches_tim_cook_to_aapl() -> None:
    """Multi-word 'tim cook' must be matched as a phrase, not 'cook'."""
    content = "I had a great call with Tim Cook today about tariffs."
    assert is_stock_candidate(content, _SP500) == {"AAPL"}


def test_prefilter_matches_elon_to_tsla() -> None:
    content = "Elon is making fantastic electric cars in Texas."
    assert is_stock_candidate(content, _SP500) == {"TSLA"}


def test_prefilter_matches_jensen_huang_to_nvda() -> None:
    """The KOSPI-rally trigger phrase from June 2026."""
    content = "Jensen Huang visited Korea and met with Samsung leadership."
    assert is_stock_candidate(content, _SP500) == {"NVDA"}


def test_prefilter_matches_warren_buffett_to_brk() -> None:
    content = "Warren Buffett is a great American."
    assert NAME_TO_TICKER.get("warren buffett") == "BRK-B"
    assert is_stock_candidate(content, _SP500 | {"BRK-B"}) == {"BRK-B"}


def test_prefilter_jensen_alone_does_not_collide() -> None:
    """Bare 'jensen' (without huang) should NOT match — only the full
    name routes to NVDA. Avoids collisions with other Jensens."""
    content = "Jensen wrote a letter to Congress."
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_cook_alone_does_not_collide() -> None:
    """Bare 'cook' must not match AAPL — common verb in prose ('cook the
    books', 'cook dinner'). Only the phrase 'tim cook'."""
    content = "We need to cook up a better trade deal."
    assert is_stock_candidate(content, _SP500) == set()


def test_extractor_version_bumped_to_3_for_ceo_expansion() -> None:
    """v3 = NAME_TO_TICKER expanded with CEO/founder names. Composite PK
    (post_id, ticker, extractor_version) means re-extraction creates NEW
    rows rather than overwriting v2 — historical data is preserved.
    """
    ex = MentionExtractor(ticker_whitelist=_SP500)
    assert ex.extractor_version == 4


# ---------------------------------------------------------------------------
# PR58 — bare-surname / common-word collisions
#
# First truly-prospective cron pass (2026-06-24) wrote 2 GS predictions
# from posts about "Dan Goldman" (US Congressman) — bare "goldman" in
# NAME_TO_TICKER collided with the surname. Same class as the v3 "cook" /
# "jensen" traps but hit us for real. v4 drops the bare surnames and
# keeps only multi-word forms.
# ---------------------------------------------------------------------------


def test_prefilter_dan_goldman_does_not_match_gs() -> None:
    """The concrete post that triggered PR58 — Dan Goldman is a
    Congressman, NOT Goldman Sachs."""
    content = "Weak and pathetic Congressman Dan Goldman just lost, BIG!"
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_goldman_sachs_phrase_still_matches_gs() -> None:
    """The company reference (multi-word) must still route."""
    content = "Goldman Sachs was ranked #1 in M&A advisory this quarter."
    assert is_stock_candidate(content, _SP500) == {"GS"}


def test_prefilter_gerald_ford_does_not_match_f() -> None:
    """Bare 'ford' collides with President Gerald Ford, Harrison Ford,
    and Ford as a common surname."""
    content = "As President Ford once said, our long national nightmare is over."
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_ford_motor_phrase_still_matches_f() -> None:
    content = "Ford Motor announced a new plant in Michigan."
    assert is_stock_candidate(content, _SP500) == {"F"}


def test_prefilter_aircraft_carrier_does_not_match_carr() -> None:
    """'Carrier' is a common English word (aircraft carrier, carrier signal)."""
    content = "The aircraft carrier USS Gerald Ford will deploy next month."
    assert is_stock_candidate(content, _SP500) == set()


def test_prefilter_carrier_corporation_phrase_still_matches_carr() -> None:
    """Trump's 2016 Indianapolis deal — 'Carrier Corporation' is the company."""
    content = "Carrier Corporation kept 800 jobs in Indiana."
    assert is_stock_candidate(content, _SP500) == {"CARR"}


def test_name_dictionary_does_not_include_bare_goldman() -> None:
    """Regression — bare 'goldman' removed in v4 (Dan Goldman collision)."""
    assert "goldman" not in NAME_TO_TICKER
    assert NAME_TO_TICKER.get("goldman sachs") == "GS"


def test_name_dictionary_does_not_include_bare_ford() -> None:
    """Regression — bare 'ford' removed in v4 (Gerald/Harrison Ford collision)."""
    assert "ford" not in NAME_TO_TICKER
    assert NAME_TO_TICKER.get("ford motor") == "F"


def test_name_dictionary_does_not_include_bare_carrier() -> None:
    """Regression — bare 'carrier' removed in v4 (aircraft carrier collision)."""
    assert "carrier" not in NAME_TO_TICKER
    assert NAME_TO_TICKER.get("carrier corporation") == "CARR"
