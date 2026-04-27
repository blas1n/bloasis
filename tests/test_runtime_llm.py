"""Tests for `bloasis.runtime.llm`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bloasis.runtime.llm import DEFAULT_MODEL, LLMSettings, complete

# ---------------------------------------------------------------------------
# LLMSettings.from_env
# ---------------------------------------------------------------------------


def test_from_env_minimal() -> None:
    cfg = LLMSettings.from_env(env={"LLM_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.model == DEFAULT_MODEL
    assert cfg.base_url is None


def test_from_env_full() -> None:
    cfg = LLMSettings.from_env(
        env={
            "LLM_API_KEY": "sk-test",
            "LLM_MODEL": "openai/gpt-4o-mini",
            "LLM_BASE_URL": "https://proxy.example.com/v1",
        }
    )
    assert cfg.api_key == "sk-test"
    assert cfg.model == "openai/gpt-4o-mini"
    assert cfg.base_url == "https://proxy.example.com/v1"


def test_from_env_blank_api_key_rejected() -> None:
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        LLMSettings.from_env(env={"LLM_API_KEY": "   "})


def test_from_env_missing_api_key_rejected() -> None:
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        LLMSettings.from_env(env={})


def test_from_env_blank_model_falls_back_to_default() -> None:
    cfg = LLMSettings.from_env(env={"LLM_API_KEY": "sk-test", "LLM_MODEL": ""})
    assert cfg.model == DEFAULT_MODEL


def test_from_env_blank_base_url_becomes_none() -> None:
    cfg = LLMSettings.from_env(env={"LLM_API_KEY": "sk-test", "LLM_BASE_URL": ""})
    assert cfg.base_url is None


def test_settings_is_frozen() -> None:
    cfg = LLMSettings(api_key="x", model="y", base_url=None)
    with pytest.raises((AttributeError, TypeError)):
        cfg.api_key = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# complete() — provider routing via LiteLLM
# ---------------------------------------------------------------------------


def _make_mock_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def test_complete_passes_provider_args_through() -> None:
    """Verify model, api_key, api_base, and response_format reach LiteLLM."""
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _make_mock_response("ok")

    settings = LLMSettings(
        api_key="sk-x",
        model="openai/gpt-4o-mini",
        base_url="https://proxy.example.com/v1",
    )

    with patch.dict("sys.modules", {"litellm": fake_litellm}):
        out = complete(
            "what is the weather",
            system_prompt="answer briefly",
            settings=settings,
            response_format="json",
            max_tokens=500,
            temperature=0.2,
        )

    assert out == "ok"
    kwargs = fake_litellm.completion.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-4o-mini"
    assert kwargs["api_key"] == "sk-x"
    assert kwargs["api_base"] == "https://proxy.example.com/v1"
    assert kwargs["max_tokens"] == 500
    assert kwargs["temperature"] == 0.2
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"] == [
        {"role": "system", "content": "answer briefly"},
        {"role": "user", "content": "what is the weather"},
    ]


def test_complete_omits_base_url_when_unset() -> None:
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _make_mock_response("ok")
    settings = LLMSettings(api_key="sk-x", model="anthropic/claude-haiku", base_url=None)

    with patch.dict("sys.modules", {"litellm": fake_litellm}):
        complete("hi", settings=settings)

    kwargs = fake_litellm.completion.call_args.kwargs
    assert "api_base" not in kwargs


def test_complete_text_format_omits_response_format() -> None:
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _make_mock_response("ok")
    settings = LLMSettings(api_key="sk-x", model="m", base_url=None)

    with patch.dict("sys.modules", {"litellm": fake_litellm}):
        complete("hi", settings=settings, response_format="text")

    assert "response_format" not in fake_litellm.completion.call_args.kwargs


def test_complete_no_system_prompt_omitted_from_messages() -> None:
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _make_mock_response("ok")
    settings = LLMSettings(api_key="sk-x", model="m", base_url=None)

    with patch.dict("sys.modules", {"litellm": fake_litellm}):
        complete("hi", settings=settings)

    messages = fake_litellm.completion.call_args.kwargs["messages"]
    assert messages == [{"role": "user", "content": "hi"}]


def test_complete_non_string_content_raises() -> None:
    fake_litellm = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = None
    fake_litellm.completion.return_value = response
    settings = LLMSettings(api_key="sk-x", model="m", base_url=None)

    with patch.dict("sys.modules", {"litellm": fake_litellm}):  # noqa: SIM117
        with pytest.raises(RuntimeError, match="non-string content"):
            complete("hi", settings=settings)
