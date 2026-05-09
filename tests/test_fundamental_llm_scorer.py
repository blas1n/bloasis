"""Tests for `bloasis.scoring.scorer.FundamentalLLMScorer`.

Phase 3 Candidate B-modern. Top decile of `fundamental_llm_score`
(LLM-rated fundamental health, [-1, 1]) gets unit score 0.99; rest 0.0.
NaN scores are excluded from ranking.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import FundamentalLLMScorer


def _fv(symbol: str, *, fundamental_llm_score: float = 0.5) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=3,
        sector="Tech",
        fundamental_llm_score=fundamental_llm_score,
    )


def _cv(symbol: str) -> CompositeVector:
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


def test_top_decile_passes_entry_threshold() -> None:
    cfg = ScorerConfig()
    scorer = FundamentalLLMScorer(cfg)
    fvs = [_fv(f"S{i:02d}", fundamental_llm_score=-1.0 + 0.1 * i) for i in range(20)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    # Top 10% of 20 = 2 stocks (S18, S19 with the highest scores)
    assert len(above) == 2
    assert {sc.symbol for sc in above} == {"S18", "S19"}


def test_nan_scores_excluded() -> None:
    cfg = ScorerConfig()
    scorer = FundamentalLLMScorer(cfg)
    fvs = [
        _fv("OK", fundamental_llm_score=0.8),
        _fv("NAN1", fundamental_llm_score=float("nan")),
        _fv("NAN2", fundamental_llm_score=float("nan")),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by = {sc.symbol: sc.score for sc in out}
    assert by["NAN1"] == 0.0
    assert by["NAN2"] == 0.0
    assert by["OK"] > cfg.entry_threshold


def test_empty_input_returns_empty() -> None:
    cfg = ScorerConfig()
    scorer = FundamentalLLMScorer(cfg)
    assert scorer.score_cross_section([], []) == []


def test_single_row_score_returns_neutral() -> None:
    cfg = ScorerConfig()
    scorer = FundamentalLLMScorer(cfg)
    sc = scorer.score(_fv("X"), _cv("X"))
    assert math.isfinite(sc.score)
    assert 0.0 <= sc.score <= 1.0


def test_top_pct_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        FundamentalLLMScorer(cfg, top_pct=0.0)
    with pytest.raises(ValueError, match="top_pct"):
        FundamentalLLMScorer(cfg, top_pct=1.1)


def test_rationale_carries_llm_score() -> None:
    cfg = ScorerConfig()
    scorer = FundamentalLLMScorer(cfg)
    fvs = [_fv(f"S{i}", fundamental_llm_score=0.1 * i) for i in range(10)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    for sc in out:
        contribs = sc.rationale.contributions
        assert len(contribs) >= 1
        assert contribs[0].name == "fundamental_llm_score"
