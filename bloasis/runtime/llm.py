"""Provider-agnostic LLM client built on LiteLLM.

The trading platform never hardcodes a provider — sentiment scoring,
explanation narratives, and any future LLM tasks call into this module.
Switching providers is a config change, not a code change.

Configuration is via environment variables (loaded into `LLMSettings`):

  LLM_API_KEY    Provider API key. Required.
  LLM_MODEL      LiteLLM model identifier with provider prefix.
                 Examples:
                   anthropic/claude-haiku-4-5-20251001
                   openai/gpt-4o-mini
                   azure/<deployment-name>
                   ollama/llama3
                 Default: anthropic/claude-haiku-4-5-20251001
  LLM_BASE_URL   Optional custom endpoint. Used for Azure, OpenAI-compatible
                 proxies, self-hosted Ollama, etc. Empty/unset = provider
                 default.

LiteLLM itself is an optional dependency (`pip install bloasis[llm]`). The
import happens lazily inside `complete()` so the package can be imported
in environments where LiteLLM is not installed (e.g., backtest runs that
do not use sentiment scoring).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Resolved LLM configuration.

    Construct via `LLMSettings.from_env()` for the standard env-driven
    flow, or instantiate directly in tests.
    """

    api_key: str
    model: str
    base_url: str | None

    @classmethod
    def from_env(cls, *, env: dict[str, str] | None = None) -> LLMSettings:
        """Load settings from process environment (or an explicit mapping for tests).

        Raises `RuntimeError` if `LLM_API_KEY` is missing — failing fast at
        configuration boundary is preferable to silent credential errors
        deeper in the call stack.
        """
        source = env if env is not None else os.environ
        api_key = source.get("LLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Copy .env.example to .env and fill it in, "
                "or pass an explicit LLMSettings instance."
            )
        model = source.get("LLM_MODEL", "").strip() or DEFAULT_MODEL
        base_url = source.get("LLM_BASE_URL", "").strip() or None
        return cls(api_key=api_key, model=model, base_url=base_url)


def complete(
    prompt: str,
    *,
    system_prompt: str | None = None,
    settings: LLMSettings | None = None,
    response_format: Literal["text", "json"] = "text",
    max_tokens: int = 2000,
    temperature: float = 0.0,
) -> str:
    """Run a single completion against the configured LLM.

    Returns the assistant message content as a string. For `json` response
    format, the string is the raw JSON payload — callers parse it.

    All keyword arguments are explicit; positional args limited to `prompt`
    so call sites read clearly when grep'ing for prompt usage.

    Lazy-imports `litellm` so callers without the [llm] extra get a clear
    error only when they actually try to use this function.
    """
    settings = settings or LLMSettings.from_env()

    try:
        import litellm
    except ImportError as exc:  # pragma: no cover — env-dependent
        raise ImportError(
            "litellm is required for LLM completion. Install with: pip install 'bloasis[llm]'"
        ) from exc

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "api_key": settings.api_key,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if settings.base_url:
        kwargs["api_base"] = settings.base_url
    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise RuntimeError(f"LLM returned non-string content (type={type(content).__name__})")
    return content
