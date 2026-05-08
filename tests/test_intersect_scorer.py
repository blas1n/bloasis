"""Tests for `bloasis.scoring.scorer.IntersectScorer`.

Phase 3 Candidate A4 — combine two orthogonal alpha signals (e.g. PEAD
AND JT momentum). Symbols passing entry_threshold in BOTH sub-scorers
get score 0.99; otherwise 0.0.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import IntersectScorer, JTMomentumScorer, PEADScorer


def _fv(
    symbol: str,
    *,
    momentum_252_21: float = 0.10,
    last_eps_surprise_pct: float = 5.0,
    days_since_earnings: float = 10.0,
) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=3,
        sector="Tech",
        momentum_252_21=momentum_252_21,
        last_eps_surprise_pct=last_eps_surprise_pct,
        days_since_earnings=days_since_earnings,
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


def _both_scorers(cfg: ScorerConfig) -> IntersectScorer:
    return IntersectScorer(
        cfg,
        sub_scorers=[
            JTMomentumScorer(cfg, top_pct=0.30),
            PEADScorer(cfg, top_pct=0.30),
        ],
    )


def test_passes_only_when_both_pass() -> None:
    """Stock passes entry_threshold only if BOTH sub-scorers vote pass."""
    cfg = ScorerConfig()
    scorer = _both_scorers(cfg)
    fvs = [
        # JT-strong + PEAD-strong → both pass
        _fv("BOTH", momentum_252_21=0.50, last_eps_surprise_pct=10.0, days_since_earnings=5.0),
        # JT-strong only (no recent earnings)
        _fv(
            "JT_ONLY",
            momentum_252_21=0.45,
            last_eps_surprise_pct=float("nan"),
            days_since_earnings=float("nan"),
        ),
        # PEAD-strong only (low momentum)
        _fv(
            "PEAD_ONLY",
            momentum_252_21=-0.20,
            last_eps_surprise_pct=8.0,
            days_since_earnings=10.0,
        ),
        # neither
        _fv("NONE", momentum_252_21=-0.30, last_eps_surprise_pct=-2.0, days_since_earnings=15.0),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    # BOTH should pass; JT_ONLY/PEAD_ONLY/NONE should not
    assert by_sym["BOTH"] > cfg.entry_threshold
    assert by_sym["JT_ONLY"] == 0.0
    assert by_sym["PEAD_ONLY"] == 0.0
    assert by_sym["NONE"] == 0.0


def test_empty_input_returns_empty() -> None:
    cfg = ScorerConfig()
    scorer = _both_scorers(cfg)
    assert scorer.score_cross_section([], []) == []


def test_single_row_score_returns_neutral() -> None:
    cfg = ScorerConfig()
    scorer = _both_scorers(cfg)
    sc = scorer.score(_fv("X"), _cv("X"))
    assert math.isfinite(sc.score)
    assert 0.0 <= sc.score <= 1.0


def test_validation_at_least_two_sub_scorers() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="at least 2"):
        IntersectScorer(cfg, sub_scorers=[JTMomentumScorer(cfg)])
    with pytest.raises(ValueError, match="at least 2"):
        IntersectScorer(cfg, sub_scorers=[])
