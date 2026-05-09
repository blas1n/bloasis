"""Cohen-Malloy "Lazy Prices" 2020 — text-diff signal on 10-K Risk Factors.

For each (symbol, fiscal year-end), measure:
- cosine_similarity: TF-IDF cosine similarity vs previous fiscal year's 10-K
  Item 1A "Risk Factors". Range [0, 1]; closer to 1 = no change.
- length_change_pct: (current_len - prior_len) / prior_len. Big positive
  = many risks added (typically bearish in academic studies).

Cohen-Malloy paper: low similarity / large change → future negative return
(short signal). For long-only momentum we use the opposite: HIGH similarity
+ small length change = "stable disclosure" = positive long signal.

Stateless pure compute — no I/O. Caller supplies the two text blocks.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Common boilerplate / function words that dilute the diff signal. Same
# stopword list across all stocks → the metric is comparable cross-section.
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "of",
        "to",
        "a",
        "in",
        "or",
        "for",
        "is",
        "be",
        "on",
        "as",
        "by",
        "with",
        "that",
        "this",
        "are",
        "it",
        "from",
        "an",
        "we",
        "our",
        "may",
        "have",
        "has",
        "could",
        "would",
        "will",
        "if",
        "such",
        "any",
        "all",
        "not",
        "no",
        "than",
        "but",
        "also",
        "their",
        "its",
        "these",
        "those",
        "which",
        "us",
        "company",
        "business",
        "operations",
    ]
)


def tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric tokens of length >= 4, drop stopwords."""
    tokens = re.findall(r"[a-z]{4,}", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def cosine_similarity(a: str, b: str) -> float:
    """TF cosine similarity between two text blocks. Returns 0 if either empty."""
    if not a or not b:
        return float("nan")
    ca = Counter(tokenize(a))
    cb = Counter(tokenize(b))
    if not ca or not cb:
        return float("nan")
    keys = set(ca) | set(cb)
    dot = sum(ca[k] * cb[k] for k in keys)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else float("nan")


def length_change_pct(current: str, prior: str) -> float:
    """(len(current) - len(prior)) / len(prior). NaN if prior empty."""
    if not prior:
        return float("nan")
    return (len(current) - len(prior)) / len(prior)
