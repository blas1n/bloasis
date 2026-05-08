"""Tests for `bloasis.scoring.scorer.JTMomentumScorer`.

Phase 0 redesign — pure rank-based selection on `momentum_252_21`.
Top-decile passes entry threshold (score=0.99), rest fails (score=0.0).
Bypasses the 7-composite blend that PR12-17 measurement showed dilutes
the signal.

JT 12-1 standalone pilot baseline: sharpe 1.21, alpha +7.6% on the same
universe (~/Docs/bloasis/Quant_Robustness_2026-05-07.md).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import JTMomentumScorer


def _fv(symbol: str, *, momentum_252_21: float = 0.10) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=2,
        sector="Tech",
        momentum_252_21=momentum_252_21,
    )


def _cv(symbol: str) -> CompositeVector:
    """Composite values are unused by JTMomentumScorer but required by Scorer protocol."""
    return CompositeVector(
        symbol=symbol,
        sector="Tech",
        value=0.5,
        quality=0.5,
        momentum=0.5,
        technical=0.5,
        volatility=0.5,
        liquidity=0.5,
        sentiment=0.5,
    )


# ---------------------------------------------------------------------------
# score_cross_section — top-decile rank-based selection
# ---------------------------------------------------------------------------


def test_top_decile_passes_entry_threshold() -> None:
    """Top 10% by momentum_252_21 → score above entry_threshold (0.65)."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    # 20 symbols with monotonically increasing momentum
    fvs = [_fv(f"S{i:02d}", momentum_252_21=0.01 * i) for i in range(20)]
    cvs = [_cv(f"S{i:02d}") for i in range(20)]
    out = scorer.score_cross_section(fvs, cvs)

    # Default top_pct=0.10 → 2 symbols pass (S18, S19)
    above_threshold = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert len(above_threshold) == 2
    assert {sc.symbol for sc in above_threshold} == {"S18", "S19"}


def test_below_top_decile_fails_exit_threshold() -> None:
    """Symbols outside top decile → score below exit_threshold (0.40)."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    fvs = [_fv(f"S{i:02d}", momentum_252_21=0.01 * i) for i in range(20)]
    cvs = [_cv(f"S{i:02d}") for i in range(20)]
    out = scorer.score_cross_section(fvs, cvs)

    below_exit = [sc for sc in out if sc.score < cfg.exit_threshold]
    assert len(below_exit) == 18  # 20 - 2 top-decile
    for sc in below_exit:
        assert sc.score < 0.40


def test_configurable_top_pct() -> None:
    """`top_pct=0.20` → top 20% pass, others fail."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg, top_pct=0.20)
    fvs = [_fv(f"S{i:02d}", momentum_252_21=0.01 * i) for i in range(20)]
    cvs = [_cv(f"S{i:02d}") for i in range(20)]
    out = scorer.score_cross_section(fvs, cvs)

    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert len(above) == 4  # 20% of 20


def test_minimum_one_symbol_passes() -> None:
    """Even with tiny universe, at least 1 symbol passes (rank-based)."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg, top_pct=0.10)
    fvs = [_fv(f"S{i}", momentum_252_21=0.01 * i) for i in range(3)]
    cvs = [_cv(f"S{i}") for i in range(3)]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert len(above) >= 1


def test_nan_momentum_excluded_from_ranking() -> None:
    """Symbols with NaN momentum_252_21 → score=0 (cannot rank)."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    fvs = [
        _fv("HIGH", momentum_252_21=0.5),
        _fv("MID", momentum_252_21=0.1),
        _fv("LOW", momentum_252_21=-0.2),
        _fv("NAN1", momentum_252_21=float("nan")),
        _fv("NAN2", momentum_252_21=float("nan")),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    assert by_sym["NAN1"] == 0.0
    assert by_sym["NAN2"] == 0.0
    # HIGH should be top decile of the 3 ranked → pass
    assert by_sym["HIGH"] > cfg.entry_threshold


def test_empty_input_returns_empty() -> None:
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    assert scorer.score_cross_section([], []) == []


def test_all_nan_momentum_returns_all_zero() -> None:
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    fvs = [_fv(f"S{i}", momentum_252_21=float("nan")) for i in range(5)]
    cvs = [_cv(f"S{i}") for i in range(5)]
    out = scorer.score_cross_section(fvs, cvs)
    for sc in out:
        assert sc.score == 0.0


# ---------------------------------------------------------------------------
# Scorer Protocol — single-row score()
# ---------------------------------------------------------------------------


def test_single_row_score_returns_neutral_without_cross_section() -> None:
    """Single-row score has no cross-section → neutral 0.5 (caller falls back
    to rule scorer if they need ranking)."""
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    sc = scorer.score(_fv("X", momentum_252_21=0.42), _cv("X"))
    assert sc.symbol == "X"
    assert math.isfinite(sc.score)
    assert 0.0 <= sc.score <= 1.0


# ---------------------------------------------------------------------------
# Rationale shape — what `bloasis runs show` displays
# ---------------------------------------------------------------------------


def test_rationale_carries_momentum_value(tmp_path: object = None) -> None:  # type: ignore[no-untyped-def]
    cfg = ScorerConfig()
    scorer = JTMomentumScorer(cfg)
    fvs = [_fv(f"S{i}", momentum_252_21=0.05 * i) for i in range(10)]
    cvs = [_cv(f"S{i}") for i in range(10)]
    out = scorer.score_cross_section(fvs, cvs)

    for sc in out:
        contribs = sc.rationale.contributions
        assert len(contribs) >= 1
        # Top contribution names momentum_252_21 with the raw value
        first = contribs[0]
        assert first.name == "momentum_252_21"
        assert "momentum_252_21" in first.inputs


def test_top_decile_pct_validation_at_construction() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        JTMomentumScorer(cfg, top_pct=0.0)
    with pytest.raises(ValueError, match="top_pct"):
        JTMomentumScorer(cfg, top_pct=1.1)
