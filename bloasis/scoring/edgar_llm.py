"""LLM YoY diff scoring on 10-K Risk Factors (Phase 3 Candidate D).

For a stock at time T, find the most recent 10-K filed before T. Compare
its Item 1A "Risk Factors" against the prior year's. Ask an LLM to rate
the risk-profile change in [-1, 1]:
- +1.0 = risks materially LOWER (improving outlook)
-  0.0 = no change
- -1.0 = risks materially HIGHER

Cohen-Malloy-Nguyen "Lazy Prices" 2020 — academic sharpe ~1.0 from
short-side disclosure-change signal. We're long-only here so expect
roughly half the strength.

Cache: cache_dir/edgar_llm/{cik}_{current_acc}_vs_{prior_acc}.json.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from bloasis.scoring.llm_fundamental import LLMConfig

_PROMPT_TEMPLATE = """You are a financial analyst.
Compare two consecutive 10-K Risk Factors disclosures.

Rate the YoY change in risk profile (sign matters: positive = better).
- Score +1.0 = risks materially LOWER (improving outlook).
- Score  0.0 = no material change.
- Score -1.0 = risks materially HIGHER (deteriorating, NEW risks, intensified language).

Output ONLY a JSON object: {{"score": <float in [-1, 1]>, "reason": "<brief, 1 sentence>"}}
No prose outside JSON.

Symbol: {symbol}

PRIOR (filed {prior_filed}, FY ending {prior_period}):
\"\"\"{prior_text}\"\"\"

CURRENT (filed {current_filed}, FY ending {current_period}):
\"\"\"{current_text}\"\"\"

Output:"""


@dataclass(frozen=True)
class EdgarLLMScorer:
    """LLM-based 10-K Risk Factors YoY diff scorer with disk cache."""

    cache_dir: Path
    llm: LLMConfig
    max_chars: int = 6000  # truncate per-doc to keep prompt under ~16k tokens

    def __post_init__(self) -> None:
        Path(self.cache_dir).expanduser().mkdir(parents=True, exist_ok=True)

    def score(
        self,
        *,
        symbol: str,
        cik: str,
        current_acc: str,
        current_filed: str,
        current_period: str,
        current_text: str,
        prior_acc: str,
        prior_filed: str,
        prior_period: str,
        prior_text: str,
    ) -> float:
        if not current_text or not prior_text:
            return float("nan")
        cache_path = self._cache_path(cik, current_acc, prior_acc)
        if cache_path.exists():
            try:
                return float(json.loads(cache_path.read_text())["score"])
            except (KeyError, ValueError, json.JSONDecodeError):
                pass
        score = self._call_llm(
            symbol=symbol,
            current_filed=current_filed,
            current_period=current_period,
            current_text=current_text[: self.max_chars],
            prior_filed=prior_filed,
            prior_period=prior_period,
            prior_text=prior_text[: self.max_chars],
        )
        if not math.isnan(score):
            cache_path.write_text(json.dumps({"score": score}))
        return score

    def _cache_path(self, cik: str, current_acc: str, prior_acc: str) -> Path:
        cur = current_acc.replace("-", "")
        prr = prior_acc.replace("-", "")
        return Path(self.cache_dir).expanduser() / f"{cik}_{cur}_vs_{prr}.json"

    def _call_llm(self, **kwargs: str) -> float:
        prompt = _PROMPT_TEMPLATE.format(**kwargs)
        # Ollama direct path (think=False is critical for qwen3 / glm-* —
        # LiteLLM silently drops the kwarg). LiteLLM model strings starting
        # with `ollama_chat/` are stripped to bare model name.
        if self.llm.model.startswith("ollama_chat/") or self.llm.model.startswith("ollama/"):
            return _ollama_direct_score(prompt, self.llm)
        # Frontier (Anthropic/OpenAI) path via LiteLLM.
        return _litellm_score(prompt, self.llm)


def _ollama_direct_score(prompt: str, cfg: LLMConfig) -> float:
    import json as _json
    import urllib.error
    import urllib.request

    model_name = cfg.model.split("/", 1)[-1]
    req = urllib.request.Request(
        f"{cfg.api_base.rstrip('/')}/api/chat",
        data=_json.dumps(
            {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "think": False,
                "stream": False,
                "options": {
                    "temperature": cfg.temperature,
                    "num_predict": cfg.max_tokens,
                },
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        body = urllib.request.urlopen(req, timeout=120).read()
    except (urllib.error.URLError, TimeoutError):
        return float("nan")
    try:
        data = _json.loads(body)
        content = data.get("message", {}).get("content", "") or ""
    except _json.JSONDecodeError:
        return float("nan")
    return _parse_score(content)


def _litellm_score(prompt: str, cfg: LLMConfig) -> float:
    import litellm

    try:
        resp = litellm.completion(
            model=cfg.model,
            api_base=cfg.api_base,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )
        content = resp.choices[0].message.content or ""
    except Exception:
        return float("nan")
    return _parse_score(content)


def _parse_score(content: str) -> float:
    match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if not match:
        return float("nan")
    try:
        obj = json.loads(match.group(0))
        v = float(obj["score"])
        if not -1.0 <= v <= 1.0:
            return float("nan")
        return v
    except (KeyError, ValueError, json.JSONDecodeError):
        return float("nan")
