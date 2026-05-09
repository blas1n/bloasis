"""Tests for `bloasis.scoring.edgar_llm`.

Network-free: covers JSON parser + cache hit + Ollama-direct vs LiteLLM
dispatch.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import patch

from bloasis.scoring.edgar_llm import EdgarLLMScorer, _parse_score
from bloasis.scoring.llm_fundamental import LLMConfig


def test_parse_score_extracts_score_field() -> None:
    assert _parse_score('{"score": 0.5}') == 0.5
    assert _parse_score('Some prose {"score": -0.3, "reason": "x"}') == -0.3


def test_parse_score_clamps_invalid_range() -> None:
    assert math.isnan(_parse_score('{"score": 2.0}'))
    assert math.isnan(_parse_score('{"score": -1.5}'))


def test_parse_score_returns_nan_on_malformed() -> None:
    assert math.isnan(_parse_score("not json"))
    assert math.isnan(_parse_score('{"missing": 1}'))
    assert math.isnan(_parse_score(""))


def test_score_returns_nan_on_empty_text(tmp_path: Path) -> None:
    scorer = EdgarLLMScorer(
        cache_dir=tmp_path,
        llm=LLMConfig(model="ollama_chat/test"),
    )
    out = scorer.score(
        symbol="AAPL",
        cik="0000320193",
        current_acc="a1",
        current_filed="2024-11-01",
        current_period="2024-09-28",
        current_text="",
        prior_acc="a0",
        prior_filed="2023-11-03",
        prior_period="2023-09-30",
        prior_text="prior",
    )
    assert math.isnan(out)


def test_score_uses_disk_cache(tmp_path: Path) -> None:
    scorer = EdgarLLMScorer(
        cache_dir=tmp_path,
        llm=LLMConfig(model="ollama_chat/test"),
    )
    cache_file = tmp_path / "0000320193_a1_vs_a0.json"
    cache_file.write_text(json.dumps({"score": 0.42}))
    out = scorer.score(
        symbol="AAPL",
        cik="0000320193",
        current_acc="a1",
        current_filed="2024-11-01",
        current_period="2024-09-28",
        current_text="risk text",
        prior_acc="a0",
        prior_filed="2023-11-03",
        prior_period="2023-09-30",
        prior_text="prior risk text",
    )
    assert out == 0.42


def test_score_dispatches_ollama_direct_for_ollama_chat_model(tmp_path: Path) -> None:
    """ollama_chat/ prefix → ollama direct API path (think=False trap)."""
    scorer = EdgarLLMScorer(
        cache_dir=tmp_path,
        llm=LLMConfig(
            model="ollama_chat/llama3.2:3b",
            api_base="http://localhost:11434",
        ),
    )
    fake_body = json.dumps({"message": {"content": '{"score": 0.7}'}}).encode()
    with patch(
        "urllib.request.urlopen",
        return_value=type("R", (), {"read": lambda self: fake_body})(),
    ):
        out = scorer.score(
            symbol="AAPL",
            cik="0000320193",
            current_acc="b1",
            current_filed="2024-11-01",
            current_period="2024-09-28",
            current_text="cur text " * 10,
            prior_acc="b0",
            prior_filed="2023-11-03",
            prior_period="2023-09-30",
            prior_text="prior text " * 10,
        )
    assert out == 0.7
    # Cache file written
    assert (tmp_path / "0000320193_b1_vs_b0.json").exists()


def test_score_handles_ollama_network_error(tmp_path: Path) -> None:
    import urllib.error

    scorer = EdgarLLMScorer(
        cache_dir=tmp_path,
        llm=LLMConfig(model="ollama_chat/llama3.2:3b"),
    )
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        out = scorer.score(
            symbol="AAPL",
            cik="0000320193",
            current_acc="c1",
            current_filed="2024-11-01",
            current_period="2024-09-28",
            current_text="cur",
            prior_acc="c0",
            prior_filed="2023-11-03",
            prior_period="2023-09-30",
            prior_text="prr",
        )
    assert math.isnan(out)


def test_score_dispatches_litellm_for_anthropic(tmp_path: Path) -> None:
    """Non-ollama model prefix → LiteLLM path (frontier provider)."""
    scorer = EdgarLLMScorer(
        cache_dir=tmp_path,
        llm=LLMConfig(model="claude-3-haiku-20240307"),
    )

    class FakeChoice:
        message = type("M", (), {"content": '{"score": 0.85}'})()

    class FakeResp:
        choices = [FakeChoice()]

    with patch("litellm.completion", return_value=FakeResp()):
        out = scorer.score(
            symbol="AAPL",
            cik="0000320193",
            current_acc="d1",
            current_filed="2024-11-01",
            current_period="2024-09-28",
            current_text="cur",
            prior_acc="d0",
            prior_filed="2023-11-03",
            prior_period="2023-09-30",
            prior_text="prr",
        )
    assert out == 0.85
