"""Tests for `bloasis.scoring.factory.build_scorer` (PR48).

Extracts the scorer dispatch logic out of `Backtester._build_scorer`
so the live trade path (`bloasis trade paper` / `bloasis trade live`)
uses the same factory. Without this, paper trading silently uses
RuleBasedScorer regardless of `cfg.scorer.type` and never tests the
actual strategy that backtests measure.
"""

from __future__ import annotations

import pytest

from bloasis.config.schema import ScorerConfig, StrategyConfig
from bloasis.scoring.factory import build_scorer
from bloasis.scoring.scorer import (
    EDGARTextDiffScorer,
    Form8KEventScorer,
    FundamentalLLMScorer,
    InsiderClusterScorer,
    IntersectScorer,
    JTMomentumScorer,
    PEADScorer,
    RuleBasedScorer,
)


def _cfg(scorer_type: str, **scorer_kwargs: object) -> StrategyConfig:
    base = StrategyConfig()
    overrides = {"type": scorer_type, **scorer_kwargs}
    return base.model_copy(update={"scorer": ScorerConfig(**overrides)})


def test_factory_default_returns_rule_based() -> None:
    cfg = _cfg("rule")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, RuleBasedScorer)


def test_factory_dispatches_edgar_textdiff() -> None:
    cfg = _cfg(
        "edgar_textdiff",
        edgar_textdiff_top_pct=0.10,
        edgar_rolling_window=2,
    )
    scorer = build_scorer(cfg)
    assert isinstance(scorer, EDGARTextDiffScorer)


def test_factory_dispatches_jt_momentum() -> None:
    cfg = _cfg("jt_momentum", jt_top_pct=0.10, jt_residual=True)
    scorer = build_scorer(cfg)
    assert isinstance(scorer, JTMomentumScorer)


def test_factory_dispatches_pead() -> None:
    cfg = _cfg("pead", pead_top_pct=0.20, pead_drift_days=60)
    scorer = build_scorer(cfg)
    assert isinstance(scorer, PEADScorer)


def test_factory_dispatches_fundamental_llm() -> None:
    cfg = _cfg("fundamental_llm", fundamental_llm_top_pct=0.10)
    scorer = build_scorer(cfg)
    assert isinstance(scorer, FundamentalLLMScorer)


def test_factory_dispatches_insider_cluster() -> None:
    cfg = _cfg("insider_cluster")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, InsiderClusterScorer)


def test_factory_dispatches_form_8k_event() -> None:
    cfg = _cfg("form_8k_event")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, Form8KEventScorer)


def test_factory_dispatches_intersect_pead_jt() -> None:
    cfg = _cfg("pead_jt_intersect")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, IntersectScorer)


def test_factory_dispatches_intersect_edgar_jt() -> None:
    cfg = _cfg("edgar_textdiff_jt_intersect")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, IntersectScorer)


def test_factory_dispatches_ml(tmp_path) -> None:
    # ML scorer requires a model file; just check the dispatch path.
    cfg = _cfg("ml", ml_model_path=str(tmp_path / "no.lgb"))
    with pytest.raises((FileNotFoundError, RuntimeError, ValueError, OSError)):
        # LightGBMScorer constructor loads the model and raises if missing.
        build_scorer(cfg)


def test_factory_unknown_type_raises() -> None:
    # Schema's Literal will reject this at construction, so pass via
    # bypassing pydantic validation.
    cfg = _cfg("rule")
    object.__setattr__(cfg.scorer, "type", "wibble")
    with pytest.raises((ValueError, KeyError, RuntimeError)):
        build_scorer(cfg)
