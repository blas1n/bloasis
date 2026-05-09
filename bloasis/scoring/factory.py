"""Scorer dispatch — single source of truth for `cfg.scorer.type` → scorer.

Both the backtester (`Backtester._build_scorer`) and the live trade path
(`bloasis trade paper` / `bloasis trade live`) need the same scorer
dispatch. PR48 extracts the logic here so paper trading actually runs
the strategy that backtests measure (previously RuleBasedScorer was
used unconditionally — silent fallback that hid every non-rule strategy
from live testing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bloasis.scoring.scorer import (
    EDGARTextDiffScorer,
    Form8KEventScorer,
    FundamentalLLMScorer,
    InsiderClusterScorer,
    IntersectScorer,
    JTMomentumScorer,
    LightGBMScorer,
    PEADScorer,
    RuleBasedScorer,
    Scorer,
)

if TYPE_CHECKING:
    from bloasis.config.schema import StrategyConfig


def build_scorer(cfg: StrategyConfig) -> Scorer:
    """Instantiate the scorer named by `cfg.scorer.type`.

    Mirrors `Backtester._build_scorer` exactly; that method now delegates
    here. Adding a new scorer type means adding a branch here and a
    `Literal` value in `ScorerConfig`.
    """
    sc = cfg.scorer
    if sc.type == "rule":
        return RuleBasedScorer(sc)
    if sc.type == "ml":
        return LightGBMScorer(cfg=sc)
    if sc.type == "jt_momentum":
        return JTMomentumScorer(
            sc,
            top_pct=sc.jt_top_pct,
            vol_scale=sc.jt_vol_scale,
            residual=sc.jt_residual,
        )
    if sc.type == "pead":
        return PEADScorer(
            sc,
            top_pct=sc.pead_top_pct,
            drift_days=sc.pead_drift_days,
        )
    if sc.type == "fundamental_llm":
        return FundamentalLLMScorer(
            sc,
            top_pct=sc.fundamental_llm_top_pct,
        )
    if sc.type == "edgar_textdiff":
        return EDGARTextDiffScorer(
            sc,
            top_pct=sc.edgar_textdiff_top_pct,
            continuous_score=sc.continuous_score,
            signal_mode=sc.edgar_signal_mode,
            length_blend_weight=sc.edgar_length_blend_weight,
        )
    if sc.type == "insider_cluster":
        return InsiderClusterScorer(
            sc,
            top_pct=sc.insider_top_pct,
            continuous_score=sc.continuous_score,
        )
    if sc.type == "form_8k_event":
        return Form8KEventScorer(
            sc,
            top_pct=sc.form_8k_top_pct,
            continuous_score=sc.continuous_score,
        )
    if sc.type == "pead_jt_intersect":
        return IntersectScorer(
            sc,
            sub_scorers=[
                JTMomentumScorer(
                    sc,
                    top_pct=sc.jt_top_pct,
                    vol_scale=sc.jt_vol_scale,
                    residual=sc.jt_residual,
                    continuous_score=sc.continuous_score,
                ),
                PEADScorer(
                    sc,
                    top_pct=sc.pead_top_pct,
                    drift_days=sc.pead_drift_days,
                ),
            ],
        )
    if sc.type == "edgar_textdiff_jt_intersect":
        return IntersectScorer(
            sc,
            sub_scorers=[
                JTMomentumScorer(
                    sc,
                    top_pct=sc.jt_top_pct,
                    vol_scale=sc.jt_vol_scale,
                    residual=sc.jt_residual,
                    continuous_score=sc.continuous_score,
                ),
                EDGARTextDiffScorer(
                    sc,
                    top_pct=sc.edgar_textdiff_top_pct,
                    continuous_score=sc.continuous_score,
                    signal_mode=sc.edgar_signal_mode,
                    length_blend_weight=sc.edgar_length_blend_weight,
                ),
            ],
        )
    if sc.type == "fundamental_llm_jt_intersect":
        return IntersectScorer(
            sc,
            sub_scorers=[
                JTMomentumScorer(
                    sc,
                    top_pct=sc.jt_top_pct,
                    vol_scale=sc.jt_vol_scale,
                    residual=sc.jt_residual,
                    continuous_score=sc.continuous_score,
                ),
                FundamentalLLMScorer(
                    sc,
                    top_pct=sc.fundamental_llm_top_pct,
                ),
            ],
        )
    raise ValueError(f"unknown scorer.type: {sc.type!r}")
