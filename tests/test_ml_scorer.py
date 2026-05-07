"""Tests for `bloasis.scoring.scorer.LightGBMScorer`.

Covers single-row + cross-section scoring with a real LightGBM model
trained on synthetic data (the test fixture trains a tiny regressor
in-memory — fast, no I/O).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bloasis.config import ScorerConfig
from bloasis.ml.training import save_model, train_walk_forward
from bloasis.scoring.composites import CompositeVector
from bloasis.scoring.features import FEATURE_COLUMNS, FeatureVector
from bloasis.scoring.scorer import LightGBMScorer, RuleBasedScorer


@pytest.fixture
def tiny_model(tmp_path: Path) -> Path:
    """Train a minimal LightGBM regressor on synthetic features and save.

    The label is a deterministic linear function of `per` so the trained
    model has clear non-zero predictions for varied inputs.
    """
    rng = np.random.default_rng(42)
    n = 300
    X = pd.DataFrame(rng.standard_normal((n, len(FEATURE_COLUMNS))), columns=list(FEATURE_COLUMNS))
    # Strong linear signal in `per` so the model definitely learns something.
    y = pd.Series(2.0 * X["per"] + rng.standard_normal(n) * 0.1, name="forward_return_20d")
    ts = pd.Series(pd.bdate_range("2023-01-01", periods=n, freq="B"))
    result = train_walk_forward(X, y, ts, n_folds=3, embargo_days=5)

    model_path = tmp_path / "tiny.pkl"
    save_model(result, model_path, feature_version=2, label_name="forward_return_20d")
    return model_path


def _fv(symbol: str, *, per: float = 0.5, momentum_252_21: float = 0.1) -> FeatureVector:
    return FeatureVector(
        timestamp=datetime(2024, 6, 15, tzinfo=UTC),
        symbol=symbol,
        feature_version=2,
        sector="Tech",
        per=per,
        momentum_252_21=momentum_252_21,
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
# Construction + metadata
# ---------------------------------------------------------------------------


def test_lightgbm_scorer_loads_model_and_metadata(tiny_model: Path) -> None:
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    assert scorer.feature_names == list(FEATURE_COLUMNS)
    assert scorer.metadata["feature_version"] == 2


def test_lightgbm_scorer_missing_model_path_raises(tmp_path: Path) -> None:
    bad_path = tmp_path / "does_not_exist.pkl"
    cfg = ScorerConfig(type="ml", ml_model_path=bad_path)
    with pytest.raises(FileNotFoundError):
        LightGBMScorer(cfg=cfg, model_path=bad_path)


# ---------------------------------------------------------------------------
# Single-row score (Scorer protocol compat)
# ---------------------------------------------------------------------------


def test_lightgbm_scorer_returns_scored_candidate(tiny_model: Path) -> None:
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    sc = scorer.score(_fv("AAA"), _cv("AAA"))
    assert sc.symbol == "AAA"
    assert 0.0 <= sc.score <= 1.0
    # Even single-row score should populate a Rationale (even minimal).
    assert sc.rationale is not None


def test_lightgbm_scorer_single_row_score_is_finite(tiny_model: Path) -> None:
    """Single-row sigmoid mapping must produce a finite [0, 1] value."""
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    sc = scorer.score(_fv("AAA", per=5.0), _cv("AAA"))
    import math

    assert math.isfinite(sc.score)


# ---------------------------------------------------------------------------
# Cross-section batch (the actual production path)
# ---------------------------------------------------------------------------


def test_score_cross_section_returns_one_per_input(tiny_model: Path) -> None:
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv(s, per=p) for s, p in zip("ABCDE", [-2.0, -1.0, 0.0, 1.0, 2.0], strict=True)]
    cvs = [_cv(s) for s in "ABCDE"]
    out = scorer.score_cross_section(fvs, cvs)
    assert len(out) == 5
    assert {sc.symbol for sc in out} == set("ABCDE")
    for sc in out:
        assert 0.0 <= sc.score <= 1.0


def test_score_cross_section_higher_per_higher_score(tiny_model: Path) -> None:
    """Model was trained y = 2 * per + noise → cross-section ordering should
    follow `per`. Highest `per` → highest unit score."""
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv(s, per=p) for s, p in zip("ABCDE", [-2.0, -1.0, 0.0, 1.0, 2.0], strict=True)]
    cvs = [_cv(s) for s in "ABCDE"]
    out = scorer.score_cross_section(fvs, cvs)
    by_sym = {sc.symbol: sc.score for sc in out}
    # E (per=2.0) should outrank A (per=-2.0) decisively.
    assert by_sym["E"] > by_sym["A"]
    # Monotone: A < B < C ... < E (allow occasional ties at boundary).
    scores = [by_sym[s] for s in "ABCDE"]
    # At least 3 of 4 successive pairs should be non-decreasing.
    monotone_pairs = sum(1 for i in range(4) if scores[i + 1] >= scores[i])
    assert monotone_pairs >= 3


def test_score_cross_section_empty_input_returns_empty(tiny_model: Path) -> None:
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    assert scorer.score_cross_section([], []) == []


def test_score_cross_section_z_score_spreads_values(tiny_model: Path) -> None:
    """Cross-section z-score → cdf gives non-trivial spread over [0, 1].

    Sigmoid of raw predictions would compress everything near 0.5 since
    forward_return_20d predictions cluster near 0. Z-score + cdf maps
    the cross-section onto the full [0, 1] range.
    """
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    rng = np.random.default_rng(0)
    # 50 distinct PER values → predictions should fan out across [0, 1].
    fvs = [_fv(f"S{i}", per=float(rng.standard_normal())) for i in range(50)]
    cvs = [_cv(f"S{i}") for i in range(50)]
    out = scorer.score_cross_section(fvs, cvs)
    scores = np.asarray([sc.score for sc in out])
    assert scores.max() - scores.min() > 0.5, (
        f"score range too narrow: [{scores.min():.3f}, {scores.max():.3f}]"
    )


# ---------------------------------------------------------------------------
# RuleBasedScorer also gets `score_cross_section` (default impl just iterates)
# ---------------------------------------------------------------------------


def test_rule_scorer_score_cross_section_iterates() -> None:
    cfg = ScorerConfig()
    scorer = RuleBasedScorer(cfg)
    fvs = [_fv(s) for s in "ABC"]
    cvs = [_cv(s) for s in "ABC"]
    out = scorer.score_cross_section(fvs, cvs)
    assert len(out) == 3
    # Should match per-symbol score() exactly (default impl iterates).
    for fv, cv, sc in zip(fvs, cvs, out, strict=True):
        single = scorer.score(fv, cv)
        assert sc.score == single.score


# ---------------------------------------------------------------------------
# PR16 — SHAP rationale
# ---------------------------------------------------------------------------


def test_shap_contributions_populated_in_cross_section(tiny_model: Path) -> None:
    """Every ScoredCandidate carries top-K SHAP contributors as FactorContributions.

    The `per` feature (which the model learned strongly) should appear in
    the top contributions for at least one symbol.
    """
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv(s, per=p) for s, p in zip("ABCDE", [-2.0, -1.0, 0.0, 1.0, 2.0], strict=True)]
    cvs = [_cv(s) for s in "ABCDE"]
    out = scorer.score_cross_section(fvs, cvs)

    # Each rationale has at least one FactorContribution.
    for sc in out:
        assert sc.rationale is not None
        assert len(sc.rationale.contributions) > 0
        # Every contribution name is a feature name (not the legacy
        # "ml_prediction" placeholder from PR15).
        for c in sc.rationale.contributions:
            assert c.name in FEATURE_COLUMNS

    # `per` should appear in top contributions for at least one symbol —
    # we trained y = 2 * per + noise, so SHAP should attribute most of
    # the variance to `per`.
    top_features_per_symbol = {
        sc.symbol: {c.name for c in sc.rationale.contributions[:3]} for sc in out
    }
    appearances = sum(1 for top in top_features_per_symbol.values() if "per" in top)
    assert appearances >= 3, (
        f"`per` (the learned signal) should be a top-3 contributor for "
        f"most symbols, got {appearances}/5"
    )


def test_shap_contributions_signed_per_feature(tiny_model: Path) -> None:
    """SHAP values can be negative (feature pushes prediction down)."""
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    # Mix of high-per (positive contribution) and low-per (negative)
    fvs = [_fv(s, per=p) for s, p in zip("AB", [-3.0, 3.0], strict=True)]
    cvs = [_cv(s) for s in "AB"]
    out = scorer.score_cross_section(fvs, cvs)

    by_sym = {sc.symbol: sc for sc in out}
    a_per = next(c.contribution for c in by_sym["A"].rationale.contributions if c.name == "per")
    b_per = next(c.contribution for c in by_sym["B"].rationale.contributions if c.name == "per")
    # A had per=-3 (low), B had per=+3 (high). SHAP for `per` should be
    # negative for A, positive for B.
    assert a_per < 0
    assert b_per > 0


def test_shap_contributions_top_k_limit(tiny_model: Path) -> None:
    """Default top-K = 5 (Phase 2 design §PR16)."""
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv("X", per=1.0)]
    cvs = [_cv("X")]
    out = scorer.score_cross_section(fvs, cvs)
    assert len(out[0].rationale.contributions) <= 5


def test_shap_contributions_sorted_by_abs_contribution(tiny_model: Path) -> None:
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv(s, per=p) for s, p in zip("ABC", [-1.0, 0.0, 1.0], strict=True)]
    cvs = [_cv(s) for s in "ABC"]
    out = scorer.score_cross_section(fvs, cvs)
    for sc in out:
        contribs = sc.rationale.contributions
        magnitudes = [abs(c.contribution) for c in contribs]
        assert magnitudes == sorted(magnitudes, reverse=True), (
            f"contributions should be sorted by |contribution| desc, got {magnitudes}"
        )


def test_shap_inputs_carry_raw_feature_value(tiny_model: Path) -> None:
    """`inputs` dict on each FactorContribution exposes the row's raw
    feature value — useful for `bloasis runs show` debug display."""
    cfg = ScorerConfig(type="ml", ml_model_path=tiny_model)
    scorer = LightGBMScorer(cfg=cfg, model_path=tiny_model)
    fvs = [_fv("Z", per=2.5, momentum_252_21=0.3)]
    cvs = [_cv("Z")]
    out = scorer.score_cross_section(fvs, cvs)
    for c in out[0].rationale.contributions:
        # Each contribution carries the raw value of its named feature.
        assert c.name in c.inputs
        if c.name == "per":
            assert c.inputs["per"] == pytest.approx(2.5)
