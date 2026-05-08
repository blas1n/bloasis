"""LLM-based fundamental health scoring (Phase 3 Candidate B-modern).

Given a stock's last quarterly statement (Revenue / EBITDA / NetIncome /
FreeCashFlow / TotalDebt / StockholdersEquity), invoke an LLM (typically
a small local model via Ollama) to produce a fundamental-health score in
[-1, 1]. Cache by (symbol, quarter_end) → score so backtests are
deterministic after the first scoring pass.

Spec: ~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md §B-modern
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_PROMPT_TEMPLATE = """You are a financial analyst.
Given quarterly fundamentals, rate the company's fundamental health for the next quarter.

Rules:
- Output ONLY a JSON object: {{"score": <float in [-1.0, 1.0]>, "reason": "<brief>"}}
- Score 1.0 = excellent (growth + margins + balance), -1.0 = severe weakness, 0 = neutral.
- No prose outside JSON.

Symbol: {symbol}
Quarter end: {quarter_end}
TTM-style data (millions USD):
- Revenue: {Revenue}
- EBITDA: {EBITDA}
- Net Income: {NetIncome}
- Free Cash Flow: {FreeCashFlow}
- Total Debt: {TotalDebt}
- Stockholders Equity: {StockholdersEquity}

Output:"""


@dataclass(frozen=True)
class LLMConfig:
    model: str = "ollama_chat/llama3.2:3b"
    api_base: str = "http://localhost:11434"
    temperature: float = 0.0
    max_tokens: int = 120


class LLMFundamentalScorer:
    """Score a single (symbol, quarter_end, fundamentals) tuple via LLM.

    Cache key = sha1(symbol + quarter_end + canonical fundamentals JSON).
    Score is float in [-1, 1]; failures (LLM error, malformed JSON, NaN
    inputs) return NaN.
    """

    def __init__(
        self,
        cache_dir: Path | str,
        llm: LLMConfig | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._llm = llm or LLMConfig()
        # In-memory cache for backtest hot loops — disk lookups dominate
        # when the engine queries the same (symbol, fy_end) every trading
        # day across ~250 days × 500 symbols.
        self._memo: dict[str, float] = {}

    def score(
        self,
        symbol: str,
        quarter_end: datetime,
        fundamentals: dict[str, float],
    ) -> float:
        # Short-circuit only when ALL values are NaN — partial data still
        # gets sent to the LLM with "N/A" placeholders.
        if all(v != v for v in fundamentals.values()):
            return float("nan")
        key = self._cache_key(symbol, quarter_end, fundamentals)
        if key in self._memo:
            return self._memo[key]
        cached = self._cache_get(key)
        if cached is not None:
            self._memo[key] = cached
            return cached

        score = self._call_llm(symbol, quarter_end, fundamentals)
        if not math.isnan(score):
            self._cache_put(key, score)
            self._memo[key] = score
        return score

    def _cache_key(
        self,
        symbol: str,
        quarter_end: datetime,
        fundamentals: dict[str, float],
    ) -> str:
        canon = json.dumps(
            {
                "symbol": symbol,
                "qe": quarter_end.isoformat(),
                "f": dict(sorted(fundamentals.items())),
            },
            sort_keys=True,
        )
        return hashlib.sha1(canon.encode()).hexdigest()  # noqa: S324 — non-crypto cache key

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _cache_get(self, key: str) -> float | None:
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            return float(json.loads(p.read_text())["score"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return None

    def _cache_put(self, key: str, score: float) -> None:
        self._cache_path(key).write_text(json.dumps({"score": score}))

    def _call_llm(
        self,
        symbol: str,
        quarter_end: datetime,
        fundamentals: dict[str, float],
    ) -> float:
        import litellm

        # Format numeric values, "N/A" for NaN. Ensure all canonical fields
        # in the template are present so .format() doesn't KeyError.
        from bloasis.data.fetchers.yfinance_financials import CANONICAL_FIELDS

        formatted: dict[str, str] = {}
        for k in CANONICAL_FIELDS:
            v = fundamentals.get(k, float("nan"))
            formatted[k] = "N/A" if v != v else f"{v / 1e6:.0f}"
        prompt = _PROMPT_TEMPLATE.format(
            symbol=symbol,
            quarter_end=quarter_end.date().isoformat(),
            **formatted,
        )
        try:
            resp = litellm.completion(
                model=self._llm.model,
                api_base=self._llm.api_base,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._llm.max_tokens,
                temperature=self._llm.temperature,
            )
            content = resp.choices[0].message.content or ""
        except Exception:
            return float("nan")
        return _parse_score(content)


def _parse_score(content: str) -> float:
    """Extract `score` field from LLM JSON output. Robust to surrounding text."""
    # Find the first {...} block; LLM might emit small extra prose.
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
