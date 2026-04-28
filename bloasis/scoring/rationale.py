"""Rationale data carriers — explainability is a first-class output.

Every `ScoredCandidate` carries a `Rationale` describing exactly which
factors drove the score and which boolean triggers / risks fired. Display
code (CLI, future explain command) and audit logs read this directly.

Storing rationale per-trade in `trades.rationale_json` (PR1 schema) means
we can answer "why did we buy AAPL on 2024-03-15?" months later without
re-running the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FactorContribution:
    """One composite factor's contribution to a final score.

    `composite_score` is the per-factor 0-1 score from `CompositeBuilder`.
    `weight` is the post-regime-adjustment, post-normalization weight.
    `contribution = composite_score * weight` (or 0 when composite is NaN).
    `inputs` carries raw feature values for debug/audit; not used for math.
    """

    name: str
    composite_score: float
    weight: float
    contribution: float
    inputs: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rationale:
    """Structured explanation behind a score.

    `contributions` is sorted by `|contribution|` descending so callers can
    show "top N factors driving this pick" without sorting.
    `triggers` are positive boolean signals ("RSI oversold").
    `risks` are negative boolean signals ("VIX elevated").
    """

    contributions: tuple[FactorContribution, ...]
    triggers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A symbol's score + rationale at one timestamp. 0-1 scale."""

    symbol: str
    timestamp: datetime
    score: float
    rationale: Rationale
