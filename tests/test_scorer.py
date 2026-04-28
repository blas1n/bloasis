"""Tests for `bloasis.scoring.scorer` — RuleBasedScorer + MLScorerStub."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig
from bloasis.scoring.composites import COMPOSITE_NAMES, CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.scorer import MLScorerStub, RuleBasedScorer

NOW = datetime.now(tz=UTC)


def _fv(**kwargs: float | str) -> FeatureVector:
    base: dict[str, object] = {
        "timestamp": NOW,
        "symbol": "AAPL",
        "feature_version": 1,
    }
    base.update(kwargs)
    return FeatureVector(**base)  # type: ignore[arg-type]


def _cv(**kwargs: float) -> CompositeVector:
    base: dict[str, object] = {"symbol": "AAPL", "sector": None}
    for name in COMPOSITE_NAMES:
        base.setdefault(name, 0.5)
    base.update(kwargs)
    return CompositeVector(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RuleBasedScorer
# ---------------------------------------------------------------------------


def test_score_with_neutral_composites_in_zero_one() -> None:
    """All composites = 0.5 → score = 0.5 (weighted mean of equal values)."""
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(), _cv())
    assert 0.0 <= sc.score <= 1.0
    assert sc.score == pytest.approx(0.5, abs=1e-6)


def test_score_higher_when_composites_higher() -> None:
    """Bumping all composites above 0.5 increases the score."""
    scorer = RuleBasedScorer(ScorerConfig())
    low = scorer.score(_fv(), _cv(**{n: 0.2 for n in COMPOSITE_NAMES})).score
    high = scorer.score(_fv(), _cv(**{n: 0.8 for n in COMPOSITE_NAMES})).score
    assert high > low


def test_nan_composite_excluded_and_weights_renormalize() -> None:
    """A NaN composite's weight is redistributed to surviving factors."""
    scorer = RuleBasedScorer(ScorerConfig())
    cv = _cv(value=float("nan"))
    sc = scorer.score(_fv(), cv)
    weights = [c.weight for c in sc.rationale.contributions if c.name != "value"]
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)
    value_contrib = next(c for c in sc.rationale.contributions if c.name == "value")
    assert value_contrib.contribution == 0.0


def test_contributions_sorted_by_abs_descending() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(), _cv(value=0.9, momentum=0.1, quality=0.5))
    contribs = [abs(c.contribution) for c in sc.rationale.contributions]
    assert contribs == sorted(contribs, reverse=True)


def test_inputs_for_value_includes_per_pbr_profit_margin() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(per=12.0, pbr=1.5, profit_margin=0.2), _cv())
    val = next(c for c in sc.rationale.contributions if c.name == "value")
    assert val.inputs == {"per": 12.0, "pbr": 1.5, "profit_margin": 0.2}


def test_score_clamped_to_unit_interval() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(), _cv(**{n: 1e9 for n in COMPOSITE_NAMES}))
    assert sc.score <= 1.0


# ---------------------------------------------------------------------------
# Triggers / Risks
# ---------------------------------------------------------------------------


def test_rsi_oversold_triggers_fire() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(rsi_14=20.0), _cv())
    assert any("oversold" in t for t in sc.rationale.triggers)


def test_strong_momentum_trigger_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(momentum_20d=0.20), _cv())
    assert any("Strong 20d momentum" in t for t in sc.rationale.triggers)


def test_macd_bullish_trigger_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(macd_hist=0.5), _cv())
    assert any("MACD bullish" in t for t in sc.rationale.triggers)


def test_strong_trend_trigger_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(adx_14=35.0), _cv())
    assert any("Strong trend" in t for t in sc.rationale.triggers)


def test_rsi_overbought_risk_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(rsi_14=80.0), _cv())
    assert any("overbought" in r for r in sc.rationale.risks)


def test_high_volatility_risk_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(volatility_20d=0.60), _cv())
    assert any("High volatility" in r for r in sc.rationale.risks)


def test_elevated_vix_risk_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(vix=30.0), _cv())
    assert any("Elevated VIX" in r for r in sc.rationale.risks)


def test_high_leverage_risk_fires() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(debt_to_equity=3.0), _cv())
    assert any("High leverage" in r for r in sc.rationale.risks)


def test_no_triggers_when_features_nan() -> None:
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(), _cv())  # all NaN by default
    assert sc.rationale.triggers == ()
    assert sc.rationale.risks == ()


# ---------------------------------------------------------------------------
# Regime multipliers
# ---------------------------------------------------------------------------


def test_crisis_regime_amplifies_quality_and_volatility() -> None:
    """In crisis (vix > 40), quality + volatility weights are multiplied.

    Compared to neutral inputs, we should see those two factors get larger
    relative weights.
    """
    cfg = ScorerConfig(
        regime_multipliers={
            "crisis": {"quality": 2.0, "volatility": 2.0, "momentum": 0.5},
        }
    )
    scorer = RuleBasedScorer(cfg)
    sc = scorer.score(_fv(vix=45.0, spy_above_sma200=1.0), _cv())
    weights = {c.name: c.weight for c in sc.rationale.contributions}
    # quality and volatility post-multiplier should exceed momentum
    assert weights["quality"] > weights["momentum"]
    assert weights["volatility"] > weights["momentum"]


def test_bull_regime_amplifies_momentum() -> None:
    cfg = ScorerConfig(
        regime_multipliers={
            "bull": {"momentum": 2.0, "volatility": 0.5},
        }
    )
    scorer = RuleBasedScorer(cfg)
    sc = scorer.score(_fv(vix=12.0, spy_above_sma200=1.0), _cv())
    weights = {c.name: c.weight for c in sc.rationale.contributions}
    assert weights["momentum"] > weights["volatility"]


# ---------------------------------------------------------------------------
# MLScorerStub
# ---------------------------------------------------------------------------


def test_ml_scorer_stub_raises_not_implemented() -> None:
    stub = MLScorerStub()
    with pytest.raises(NotImplementedError, match="train"):
        stub.score(_fv(), _cv())


def test_ml_scorer_stub_accepts_optional_path() -> None:
    stub = MLScorerStub(model_path="path/to/model.lgb")
    assert stub.model_path == "path/to/model.lgb"


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------


def test_all_zero_weights_returns_zero_score() -> None:
    """Edge case: if every composite is NaN, weights collapse to zero
    and score is 0 (rather than raising)."""
    scorer = RuleBasedScorer(ScorerConfig())
    sc = scorer.score(_fv(), _cv(**{n: float("nan") for n in COMPOSITE_NAMES}))
    assert sc.score == 0.0
    assert all(math.isnan(c.composite_score) for c in sc.rationale.contributions)
