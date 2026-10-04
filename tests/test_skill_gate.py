"""Skill-relative paper gate (#88).

The corrected random baseline (`docs/research/Random_Baseline_2026-10-03.md`,
after #109) put even the best tenth of no-skill books above the old 0.85 DD
bar. A candidate is judged against random books with matching turnover, in
the same frame, instead.
"""

from __future__ import annotations

import pytest

from bloasis.backtest.skill_gate import RunMetrics, matched_kind, skill_gate


def _runs(dds: list[float], alphas: list[float], trades: int) -> list[RunMetrics]:
    return [RunMetrics(dd=d, alpha=a, trades=trades) for d, a in zip(dds, alphas, strict=True)]


# 20 seeds: DD 0.80 .. 1.18 step 0.02, alpha -0.10 .. +0.09 step 0.01.
_DD = [round(0.80 + 0.02 * i, 2) for i in range(20)]
_ALPHA = [round(-0.10 + 0.01 * i, 2) for i in range(20)]
BASELINES = {
    "R1": _runs([d - 0.25 for d in _DD], _ALPHA, trades=1354),
    "R2": _runs(_DD, _ALPHA, trades=434),
}


def test_matched_kind_is_the_baseline_with_the_nearest_turnover() -> None:
    assert matched_kind(398, BASELINES) == "R2"
    assert matched_kind(1200, BASELINES) == "R1"


def test_passes_only_when_dd_beats_p10_and_alpha_beats_p90() -> None:
    v = skill_gate(RunMetrics(dd=0.79, alpha=0.10, trades=400), BASELINES)
    assert v.passed
    assert v.baseline_kind == "R2"


def test_better_dd_alone_does_not_pass() -> None:
    v = skill_gate(RunMetrics(dd=0.70, alpha=0.00, trades=400), BASELINES)
    assert not v.passed
    assert any("alpha" in r for r in v.reasons)


def test_better_alpha_alone_does_not_pass() -> None:
    v = skill_gate(RunMetrics(dd=0.95, alpha=0.20, trades=400), BASELINES)
    assert not v.passed
    assert any("dd" in r for r in v.reasons)


def test_ties_with_the_baseline_quantiles_do_not_pass() -> None:
    probe = skill_gate(RunMetrics(dd=0.0, alpha=1.0, trades=400), BASELINES)
    v = skill_gate(RunMetrics(dd=probe.dd_p10, alpha=probe.alpha_p90, trades=400), BASELINES)
    assert not v.passed


def test_churning_cannot_buy_a_pass() -> None:
    # A high-turnover candidate is judged against the high-turnover baseline.
    v = skill_gate(RunMetrics(dd=0.60, alpha=0.10, trades=1300), BASELINES)
    assert v.baseline_kind == "R1"
    assert not v.passed


def test_too_few_seeds_is_refused() -> None:
    short = {"R2": BASELINES["R2"][:5]}
    with pytest.raises(ValueError, match="seeds"):
        skill_gate(RunMetrics(dd=0.5, alpha=0.5, trades=400), short)


def test_edgar_rolling2_on_the_recorded_development_baseline_fails() -> None:
    # The 20 development R2 seeds re-measured 2026-10-04 after #109, 4 dp.
    # EDGAR measured DD 0.873 / alpha +3.74%: neither beats p10 / p90.
    dds = [
        1.1144,
        0.9304,
        0.9164,
        0.9817,
        1.0342,
        0.9239,
        0.8651,
        1.1353,
        0.8874,
        1.0463,
        0.9592,
        0.9554,
        0.9634,
        0.775,
        0.8653,
        0.9216,
        0.9496,
        1.0207,
        1.0209,
        0.9247,
    ]
    alphas = [
        0.1215,
        0.0323,
        -0.0398,
        -0.1432,
        -0.0216,
        -0.0143,
        -0.0792,
        -0.0158,
        0.0286,
        -0.0298,
        0.0431,
        -0.065,
        -0.0113,
        0.054,
        -0.0313,
        0.0382,
        -0.0198,
        -0.049,
        0.0002,
        -0.0413,
    ]
    runs = [RunMetrics(dd=d, alpha=a, trades=518) for d, a in zip(dds, alphas, strict=True)]
    v = skill_gate(RunMetrics(dd=0.873, alpha=0.0374, trades=398), {"R2": runs})
    assert not v.passed
    assert len(v.reasons) == 2
