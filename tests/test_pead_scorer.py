"""Tests for `bloasis.scoring.scorer.PEADScorer`.

Phase 3 — Post-Earnings Announcement Drift.

Signal: stocks with a recent positive earnings surprise drift upward for
~60 days. Top decile of `last_eps_surprise_pct` (where
`days_since_earnings <= drift_days` AND `last_eps_surprise_pct > 0`)
gets unit score 0.99 (passes entry threshold), rest 0.0.

References: Bernard-Thomas 1989, Sloan 1996. Phase 3 spec —
`~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md` §Candidate A.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import PEADScorer


def _fv(
    symbol: str,
    *,
    last_eps_surprise_pct: float = 5.0,
    days_since_earnings: float = 10.0,
) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=3,
        sector="Tech",
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


# ---------------------------------------------------------------------------
# score_cross_section — top-decile of positive surprise within drift window
# ---------------------------------------------------------------------------


def test_top_surprise_in_drift_window_passes() -> None:
    """Top decile of positive surprise, within drift window → score > entry_threshold."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    # 20 stocks all within 30 days of earnings, positive surprise increasing
    fvs = [
        _fv(f"S{i:02d}", last_eps_surprise_pct=0.5 * i, days_since_earnings=30.0)
        for i in range(1, 21)  # surprise: 0.5..10.0
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)

    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    # Top 10% of 20 eligible = 2 stocks (S19, S20 with surprise 9.5, 10.0)
    assert len(above) == 2
    assert {sc.symbol for sc in above} == {"S19", "S20"}


def test_outside_drift_window_excluded() -> None:
    """days_since_earnings > drift_days → score 0 (drift period over)."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg, drift_days=60)
    fvs = [
        _fv("RECENT", last_eps_surprise_pct=10.0, days_since_earnings=10.0),
        _fv("STALE", last_eps_surprise_pct=10.0, days_since_earnings=120.0),  # outside
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    assert by_sym["STALE"] == 0.0
    # RECENT is the only eligible → top decile of 1 → passes
    assert by_sym["RECENT"] > cfg.entry_threshold


def test_negative_surprise_excluded() -> None:
    """surprise <= 0 → score 0 (no PEAD anomaly on misses)."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    fvs = [
        _fv("BEAT", last_eps_surprise_pct=5.0, days_since_earnings=10.0),
        _fv("MISS", last_eps_surprise_pct=-3.0, days_since_earnings=10.0),
        _fv("NEUTRAL", last_eps_surprise_pct=0.0, days_since_earnings=10.0),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    assert by_sym["MISS"] == 0.0
    assert by_sym["NEUTRAL"] == 0.0
    assert by_sym["BEAT"] > cfg.entry_threshold


def test_nan_data_excluded() -> None:
    """NaN surprise OR NaN days → score 0 (cannot rank)."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    fvs = [
        _fv("OK", last_eps_surprise_pct=5.0, days_since_earnings=10.0),
        _fv("NAN_SURPRISE", last_eps_surprise_pct=float("nan"), days_since_earnings=10.0),
        _fv("NAN_DAYS", last_eps_surprise_pct=5.0, days_since_earnings=float("nan")),
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    assert by_sym["NAN_SURPRISE"] == 0.0
    assert by_sym["NAN_DAYS"] == 0.0
    assert by_sym["OK"] > cfg.entry_threshold


def test_minimum_one_passes() -> None:
    """Tiny eligible set → at least 1 pass."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg, top_pct=0.10)
    fvs = [_fv(f"S{i}", last_eps_surprise_pct=1.0 + i, days_since_earnings=5.0) for i in range(3)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    above = [sc for sc in out if sc.score > cfg.entry_threshold]
    assert len(above) >= 1


def test_empty_input_returns_empty() -> None:
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    assert scorer.score_cross_section([], []) == []


def test_all_ineligible_returns_all_zero() -> None:
    """No eligible stocks → all score 0, no errors."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    fvs = [_fv(f"S{i}", last_eps_surprise_pct=-5.0, days_since_earnings=10.0) for i in range(5)]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    for sc in out:
        assert sc.score == 0.0


# ---------------------------------------------------------------------------
# Scorer Protocol — single-row score()
# ---------------------------------------------------------------------------


def test_single_row_score_returns_neutral() -> None:
    """Single-row score has no cross-section → neutral 0.5."""
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    sc = scorer.score(_fv("X"), _cv("X"))
    assert sc.symbol == "X"
    assert math.isfinite(sc.score)
    assert 0.0 <= sc.score <= 1.0


# ---------------------------------------------------------------------------
# Rationale shape
# ---------------------------------------------------------------------------


def test_rationale_carries_eps_surprise() -> None:
    cfg = ScorerConfig()
    scorer = PEADScorer(cfg)
    fvs = [
        _fv(f"S{i}", last_eps_surprise_pct=0.5 * i, days_since_earnings=15.0) for i in range(1, 11)
    ]
    cvs = [_cv(f.symbol) for f in fvs]
    out = scorer.score_cross_section(fvs, cvs)
    for sc in out:
        contribs = sc.rationale.contributions
        assert len(contribs) >= 1
        first = contribs[0]
        assert first.name == "last_eps_surprise_pct"
        assert "last_eps_surprise_pct" in first.inputs


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_top_pct_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="top_pct"):
        PEADScorer(cfg, top_pct=0.0)
    with pytest.raises(ValueError, match="top_pct"):
        PEADScorer(cfg, top_pct=1.1)


def test_drift_days_validation() -> None:
    cfg = ScorerConfig()
    with pytest.raises(ValueError, match="drift_days"):
        PEADScorer(cfg, drift_days=0)
    with pytest.raises(ValueError, match="drift_days"):
        PEADScorer(cfg, drift_days=-5)
