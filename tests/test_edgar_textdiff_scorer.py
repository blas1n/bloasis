"""Tests for `bloasis.scoring.scorer.EDGARTextDiffScorer`.

Phase 3 Candidate D-textdiff. Cross-section ranking on
`risk_factors_cosine` (HIGHER cosine = stable disclosure = positive
long-only signal per Cohen-Malloy 2020 inverted for long-side).
Top top_pct passes entry threshold.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import EDGARTextDiffScorer


def _fv(symbol: str, *, cosine: float = 0.99, len_change: float = 0.0) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=3,
        sector="Tech",
        risk_factors_cosine=cosine,
        risk_factors_len_change=len_change,
    )


def _cv(s: str) -> CompositeVector:
    return CompositeVector(
        symbol=s,
        sector="Tech",
        value=0.5,
        quality=0.5,
        momentum=0.5,
        technical=0.5,
        volatility=0.5,
        liquidity=0.5,
        sentiment=0.5,
    )


def test_top_decile_by_cosine_passes_entry() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg)
    fvs = [_fv(f"S{i:02d}", cosine=0.95 + 0.001 * i) for i in range(20)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    # Top 10% of 20 = 2 highest cosine = S18, S19
    assert len(above) == 2
    assert {sc.symbol for sc in above} == {"S18", "S19"}


def test_nan_cosine_excluded() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg)
    fvs = [
        _fv("OK", cosine=0.99),
        _fv("NAN", cosine=float("nan")),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    assert by["NAN"] == 0.0
    assert by["OK"] > cfg.entry_threshold


def test_empty_input() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg)
    assert scorer.score_cross_section([], []) == []


def test_single_row_neutral() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg)
    sc = scorer.score(_fv("X"), _cv("X"))
    assert math.isfinite(sc.score)


def test_top_pct_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        EDGARTextDiffScorer(cfg, top_pct=0.0)
    with pytest.raises(ValueError, match="top_pct"):
        EDGARTextDiffScorer(cfg, top_pct=1.5)


def test_signal_mode_length_uses_neg_abs_length_change() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg, signal_mode="length")
    fvs = [
        _fv("STABLE", cosine=0.99, len_change=0.01),  # tiny change → top
        _fv("BIG_UP", cosine=0.99, len_change=0.30),  # big change → bottom
        _fv("BIG_DOWN", cosine=0.99, len_change=-0.30),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    assert by["STABLE"] > cfg.entry_threshold  # smallest |length_change|
    assert by["BIG_UP"] == 0.0
    assert by["BIG_DOWN"] == 0.0


def test_signal_mode_blend_combines_cosine_and_length() -> None:
    cfg = ScorerConfig()
    scorer = EDGARTextDiffScorer(cfg, signal_mode="blend", length_blend_weight=0.5)
    fvs = [
        _fv("BEST", cosine=0.99, len_change=0.01),
        _fv("LOW_COS", cosine=0.50, len_change=0.01),
        _fv("BIG_LEN", cosine=0.99, len_change=0.50),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    # BEST has highest cosine - 0.5*|len| → top decile
    assert by["BEST"] > cfg.entry_threshold


def test_signal_mode_invalid_raises() -> None:
    cfg = ScorerConfig()
    import pytest as _pytest

    with _pytest.raises(ValueError, match="signal_mode"):
        EDGARTextDiffScorer(cfg, signal_mode="bogus")
