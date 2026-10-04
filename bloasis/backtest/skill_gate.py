"""Skill-relative paper gate (#88).

`docs/research/Random_Baseline_2026-10-03.md` (corrected after #109) ran the
`edgar-rolling2` portfolio frame with a random signal. Even the best tenth of
those no-skill books had a DD ratio to SPY of 0.865–0.896, for monthly and for
yearly turnover, in the development window and in H2. The old fixed bar of
0.85 was therefore beyond reach of the frame itself and could not tell skill
from luck.

The paper gate instead compares a candidate with random books run in the
**same frame and window** (`scripts/skill-gate.py`), choosing the random kind
whose turnover is nearest the candidate's. It passes only if the candidate
beats the random 10th percentile on drawdown **and** the random 90th
percentile on alpha, i.e. it lands in the best tenth of no-skill books on both.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: The baseline distribution is a 20-seed sample; fewer makes p10/p90 noise.
MIN_SEEDS = 20


@dataclass(frozen=True)
class RunMetrics:
    """Median-across-folds results of one walk-forward run."""

    dd: float  # median max-DD ratio to SPY
    alpha: float  # median annualized alpha vs SPY
    trades: int


@dataclass(frozen=True)
class SkillVerdict:
    passed: bool
    baseline_kind: str
    dd_p10: float
    alpha_p90: float
    reasons: tuple[str, ...]


def matched_kind(trades: int, baselines: Mapping[str, Sequence[RunMetrics]]) -> str:
    """The baseline kind whose median trade count is nearest `trades` (log scale)."""
    if not baselines:
        raise ValueError("no baseline runs")

    def distance(kind: str) -> float:
        median = statistics.median(r.trades for r in baselines[kind])
        return abs(math.log(max(trades, 1) / max(median, 1)))

    return min(baselines, key=distance)


def skill_gate(
    candidate: RunMetrics,
    baselines: Mapping[str, Sequence[RunMetrics]],
    *,
    min_seeds: int = MIN_SEEDS,
) -> SkillVerdict:
    """Pass iff the candidate beats the turnover-matched random p10 DD and p90 alpha."""
    kind = matched_kind(candidate.trades, baselines)
    runs = baselines[kind]
    if len(runs) < min_seeds:
        raise ValueError(f"baseline {kind} has {len(runs)} seeds, need at least {min_seeds}")
    dd_p10 = statistics.quantiles([r.dd for r in runs], n=10)[0]
    alpha_p90 = statistics.quantiles([r.alpha for r in runs], n=10)[-1]

    reasons: list[str] = []
    if not candidate.dd < dd_p10:
        reasons.append(f"dd {candidate.dd:.3f} not below random {kind} p10 {dd_p10:.3f}")
    if not candidate.alpha > alpha_p90:
        reasons.append(f"alpha {candidate.alpha:+.4f} not above random {kind} p90 {alpha_p90:+.4f}")
    return SkillVerdict(
        passed=not reasons,
        baseline_kind=kind,
        dd_p10=dd_p10,
        alpha_p90=alpha_p90,
        reasons=tuple(reasons),
    )
