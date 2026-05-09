"""Tests for PR20 SEC Form 4 / 8-K event scorers."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import Form8KEventScorer, InsiderClusterScorer


def _fv(
    symbol: str, *, insider: float = float("nan"), form8k: float = float("nan")
) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=3,
        sector="Tech",
        insider_filings_60d=insider,
        form_8k_filings_30d=form8k,
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


# ---------------------------------------------------------------------------
# InsiderClusterScorer
# ---------------------------------------------------------------------------


def test_insider_top_decile_passes() -> None:
    cfg = ScorerConfig()
    scorer = InsiderClusterScorer(cfg)
    fvs = [_fv(f"S{i:02d}", insider=float(i)) for i in range(20)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert {sc.symbol for sc in above} == {"S18", "S19"}


def test_insider_nan_excluded() -> None:
    cfg = ScorerConfig()
    scorer = InsiderClusterScorer(cfg)
    fvs = [
        _fv("HIGH", insider=10.0),
        _fv("NAN", insider=float("nan")),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    assert by["NAN"] == 0.0
    assert by["HIGH"] > cfg.entry_threshold


def test_insider_continuous_mode_emits_percentiles() -> None:
    cfg = ScorerConfig()
    scorer = InsiderClusterScorer(cfg, continuous_score=True)
    fvs = [_fv(f"S{i:02d}", insider=float(i)) for i in range(10)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    # Highest insider count → score 1.0; lowest → 0.0
    assert by["S09"] == 1.0
    assert by["S00"] == 0.0


def test_insider_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        InsiderClusterScorer(cfg, top_pct=0.0)


# ---------------------------------------------------------------------------
# Form8KEventScorer
# ---------------------------------------------------------------------------


def test_form_8k_top_decile_passes() -> None:
    cfg = ScorerConfig()
    scorer = Form8KEventScorer(cfg)
    fvs = [_fv(f"S{i:02d}", form8k=float(i)) for i in range(20)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert {sc.symbol for sc in above} == {"S18", "S19"}


def test_form_8k_single_row_score() -> None:
    cfg = ScorerConfig()
    scorer = Form8KEventScorer(cfg)
    sc = scorer.score(_fv("X", form8k=5.0), _cv("X"))
    assert math.isfinite(sc.score)


def test_form_8k_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        Form8KEventScorer(cfg, top_pct=2.0)
