"""Tests for `bloasis.scoring.llm_fundamental`.

Network-free: covers JSON parser, cache hit/miss/persistence, in-memory
memo (hot-loop disk-I/O reduction), and partial-NaN prompt formatting.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from bloasis.scoring.llm_fundamental import (
    LLMConfig,
    LLMFundamentalScorer,
    _parse_score,
)


def _ts() -> datetime:
    return datetime(2024, 12, 31, tzinfo=UTC)


def _funds(**overrides: float) -> dict[str, float]:
    base = {
        "Revenue": 391_000_000_000.0,
        "EBITDA": 134_000_000_000.0,
        "NetIncome": 96_000_000_000.0,
        "FreeCashFlow": 110_000_000_000.0,
        "TotalDebt": 99_000_000_000.0,
        "StockholdersEquity": 56_000_000_000.0,
    }
    base.update(overrides)
    return base


def test_parse_score_returns_score_in_range() -> None:
    assert _parse_score('{"score": 0.7, "reason": "x"}') == 0.7


def test_parse_score_handles_invalid() -> None:
    assert math.isnan(_parse_score("not json"))
    assert math.isnan(_parse_score('{"score": 2.0}'))


def test_score_returns_nan_when_all_fundamentals_nan(tmp_path: Path) -> None:
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    nan_funds = {
        k: float("nan")
        for k in (
            "Revenue",
            "EBITDA",
            "NetIncome",
            "FreeCashFlow",
            "TotalDebt",
            "StockholdersEquity",
        )
    }
    out = scorer.score("AAPL", _ts(), nan_funds)
    assert math.isnan(out)


def test_score_proceeds_with_partial_nan(tmp_path: Path) -> None:
    """At least 1 valid value → LLM is called (NaN replaced with N/A in prompt)."""
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    partial = _funds(EBITDA=float("nan"), FreeCashFlow=float("nan"))

    captured: dict[str, str] = {}

    class FakeChoice:
        message = type("M", (), {"content": '{"score": 0.4}'})()

    class FakeResp:
        choices = [FakeChoice()]

    def fake_completion(**kwargs: object) -> FakeResp:
        captured["prompt"] = kwargs["messages"][0]["content"]  # type: ignore[index]
        return FakeResp()

    with patch("litellm.completion", side_effect=fake_completion):
        out = scorer.score("AAPL", _ts(), partial)
    assert out == 0.4
    assert "EBITDA: N/A" in captured["prompt"]
    assert "Revenue: 391000" in captured["prompt"]


def test_score_disk_cache_hit(tmp_path: Path) -> None:
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    funds = _funds()
    # Pre-populate cache
    key = scorer._cache_key("AAPL", _ts(), funds)
    (tmp_path / f"{key}.json").write_text(json.dumps({"score": 0.91}))
    out = scorer.score("AAPL", _ts(), funds)
    assert out == 0.91


def test_score_inmemory_memo_avoids_disk_reread(tmp_path: Path) -> None:
    """Second call for same key should hit memo, not disk."""
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    funds = _funds()
    key = scorer._cache_key("AAPL", _ts(), funds)
    (tmp_path / f"{key}.json").write_text(json.dumps({"score": 0.5}))

    out1 = scorer.score("AAPL", _ts(), funds)
    # Remove cache file — memo should still serve
    (tmp_path / f"{key}.json").unlink()
    out2 = scorer.score("AAPL", _ts(), funds)
    assert out1 == 0.5 == out2


def test_score_persists_after_llm_call(tmp_path: Path) -> None:
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    funds = _funds()

    class FakeChoice:
        message = type("M", (), {"content": '{"score": 0.6}'})()

    class FakeResp:
        choices = [FakeChoice()]

    with patch("litellm.completion", return_value=FakeResp()):
        out = scorer.score("AAPL", _ts(), funds)
    assert out == 0.6
    # Cache file written
    key = scorer._cache_key("AAPL", _ts(), funds)
    assert (tmp_path / f"{key}.json").exists()


def test_score_handles_llm_exception(tmp_path: Path) -> None:
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    funds = _funds()
    with patch("litellm.completion", side_effect=RuntimeError("api down")):
        out = scorer.score("AAPL", _ts(), funds)
    assert math.isnan(out)


def test_cache_key_stable_across_dict_order(tmp_path: Path) -> None:
    scorer = LLMFundamentalScorer(cache_dir=tmp_path, llm=LLMConfig())
    a = {"Revenue": 1.0, "EBITDA": 2.0}
    b = {"EBITDA": 2.0, "Revenue": 1.0}
    assert scorer._cache_key("AAPL", _ts(), a) == scorer._cache_key("AAPL", _ts(), b)
