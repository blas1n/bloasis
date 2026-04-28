"""Scorer Protocol + RuleBasedScorer + MLScorer stub.

The `Scorer` Protocol is the single contract between the scoring layer
and consumers (signal generator, backtest engine, CLI). Both rule-based
and ML scorers conform; swapping is a config change, not a code change.

`RuleBasedScorer` produces a 0-1 score from composite factors with
regime-conditioned weights. Triggers/risks are derived from raw features
using thresholds defined in `ScorerConfig.thresholds`.

`MLScorerStub` is a Protocol-conforming placeholder that fails loudly
until a model is trained (PR5+).
"""

from __future__ import annotations

import math
from typing import Protocol, cast, runtime_checkable

from bloasis.config import ScorerConfig
from bloasis.config.schema import RegimeName
from bloasis.scoring.composites import COMPOSITE_NAMES, CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.rationale import FactorContribution, Rationale, ScoredCandidate
from bloasis.scoring.regime import classify_regime


@runtime_checkable
class Scorer(Protocol):
    """Protocol every scorer (rule-based, ML) implements.

    Takes both the raw `FeatureVector` (for triggers/risks/regime) and the
    cross-section composite scores (for weighted aggregation). Returns a
    fully-explained `ScoredCandidate`.
    """

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate: ...


class RuleBasedScorer:
    """Weighted-sum scorer with regime-conditioned weights.

    The score is `sum(composite_i * adjusted_weight_i)` where
    `adjusted_weight = base_weight * regime_multiplier(name)`, then
    re-normalized to sum to 1.0. NaN composites contribute 0 with weight
    redistributed across the surviving factors at normalization.
    """

    def __init__(self, cfg: ScorerConfig) -> None:
        self._cfg = cfg
        self._base_weights: dict[str, float] = cfg.weights.model_dump()

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        regime = classify_regime(fv.vix, fv.spy_above_sma200)
        weights = self._adjusted_weights(regime, cv)

        contributions: list[FactorContribution] = []
        for name in COMPOSITE_NAMES:
            comp = float(getattr(cv, name))
            w = weights.get(name, 0.0)
            contrib = 0.0 if math.isnan(comp) else comp * w
            contributions.append(
                FactorContribution(
                    name=name,
                    composite_score=comp,
                    weight=w,
                    contribution=contrib,
                    inputs=_inputs_for(name, fv),
                )
            )

        score = sum(c.contribution for c in contributions)
        contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
        triggers = self._detect_triggers(fv)
        risks = self._detect_risks(fv)

        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=max(0.0, min(1.0, score)),
            rationale=Rationale(
                contributions=tuple(contributions),
                triggers=triggers,
                risks=risks,
            ),
        )

    # ------------------------------------------------------------------
    # weights
    # ------------------------------------------------------------------

    def _adjusted_weights(self, regime: str, cv: CompositeVector) -> dict[str, float]:
        """Apply regime multipliers, drop NaN-composite factors, renormalize."""
        mults: dict[str, float] = self._cfg.regime_multipliers.get(cast(RegimeName, regime), {})
        adjusted: dict[str, float] = {}
        for name in COMPOSITE_NAMES:
            comp = float(getattr(cv, name))
            if math.isnan(comp):
                continue
            base = self._base_weights[name]
            mult = float(mults.get(name, 1.0))
            adjusted[name] = base * mult

        total = sum(adjusted.values())
        if total <= 0:
            return dict.fromkeys(COMPOSITE_NAMES, 0.0)
        return {name: w / total for name, w in adjusted.items()}

    # ------------------------------------------------------------------
    # triggers / risks
    # ------------------------------------------------------------------

    def _detect_triggers(self, fv: FeatureVector) -> tuple[str, ...]:
        t = self._cfg.thresholds
        out: list[str] = []
        if not _isnan(fv.rsi_14) and fv.rsi_14 < t.rsi_oversold:
            out.append(f"RSI oversold ({fv.rsi_14:.1f} < {t.rsi_oversold:.0f})")
        if not _isnan(fv.momentum_20d) and fv.momentum_20d > t.strong_momentum_20d:
            out.append(f"Strong 20d momentum (+{fv.momentum_20d * 100:.1f}%)")
        if not _isnan(fv.macd_hist) and fv.macd_hist > 0:
            out.append("MACD bullish")
        if not _isnan(fv.adx_14) and fv.adx_14 > t.strong_trend_adx:
            out.append(f"Strong trend (ADX {fv.adx_14:.0f})")
        return tuple(out)

    def _detect_risks(self, fv: FeatureVector) -> tuple[str, ...]:
        t = self._cfg.thresholds
        out: list[str] = []
        if not _isnan(fv.rsi_14) and fv.rsi_14 > t.rsi_overbought:
            out.append(f"RSI overbought ({fv.rsi_14:.1f} > {t.rsi_overbought:.0f})")
        if not _isnan(fv.volatility_20d) and fv.volatility_20d > t.high_volatility_ann:
            out.append(f"High volatility ({fv.volatility_20d * 100:.0f}% ann.)")
        if not _isnan(fv.vix) and fv.vix > t.elevated_vix:
            out.append(f"Elevated VIX ({fv.vix:.1f})")
        if not _isnan(fv.debt_to_equity) and fv.debt_to_equity > t.high_leverage_de:
            out.append(f"High leverage (D/E {fv.debt_to_equity:.1f})")
        return tuple(out)


class MLScorerStub:
    """Placeholder for the LightGBM scorer landing in PR5+.

    Conforms to the `Scorer` Protocol so config-driven swapping works
    today, but raises if anyone actually calls `score`. This way the
    Phase 1 wiring is complete and Phase 3 just drops in an implementation.
    """

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        raise NotImplementedError(
            "MLScorerStub is not implemented; train a LightGBM model in PR5+ "
            "and replace this with the real scorer."
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_INPUTS_FOR_COMPOSITE: dict[str, tuple[str, ...]] = {
    "value": ("per", "pbr", "profit_margin"),
    "quality": ("roe", "debt_to_equity", "current_ratio"),
    "momentum": ("momentum_20d", "momentum_60d", "rsi_14"),
    "technical": ("macd_hist", "adx_14", "bb_width"),
    "volatility": ("volatility_20d", "atr_14"),
    "liquidity": ("market_cap", "volume_ratio_20d"),
    "sentiment": ("sentiment_score", "news_count"),
}


def _inputs_for(composite_name: str, fv: FeatureVector) -> dict[str, float]:
    """Pull the raw feature values that feed a composite, for debug display."""
    return {f: float(getattr(fv, f)) for f in _INPUTS_FOR_COMPOSITE.get(composite_name, ())}


def _isnan(v: float) -> bool:
    return v != v
