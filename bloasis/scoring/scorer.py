"""Scorer Protocol + RuleBasedScorer + LightGBMScorer.

The `Scorer` Protocol is the single contract between the scoring layer
and consumers (signal generator, backtest engine, CLI). Both rule-based
and ML scorers conform; swapping is a config change, not a code change.

`RuleBasedScorer` produces a 0-1 score from composite factors with
regime-conditioned weights. Triggers/risks are derived from raw features
using thresholds defined in `ScorerConfig.thresholds`.

`LightGBMScorer` (PR15) loads a pickled LightGBM regressor + JSON sidecar
written by `bloasis ml train` and converts cross-section predictions to
unit scores via z-score + Normal CDF (so top decile of predictions maps
to ~ top decile of unit scores). Single-row scoring uses a sigmoid
fallback.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from bloasis.config import ScorerConfig
from bloasis.config.schema import RegimeName
from bloasis.scoring.composites import COMPOSITE_NAMES, CompositeVector
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.rationale import FactorContribution, Rationale, ScoredCandidate
from bloasis.scoring.regime import classify_regime

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd


@runtime_checkable
class Scorer(Protocol):
    """Protocol every scorer (rule-based, ML) implements.

    `score()` is the per-symbol entrypoint. `score_cross_section()` is
    the batch entrypoint preferred by the engine — ML scorers override
    it for batch predict + cross-section z-score; rule scorers use the
    default fallback that just iterates `score()`.
    """

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate: ...

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]: ...


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

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        """Default impl — iterate `score()`. Rule-based scoring has no
        cross-section dependency so this is correct + cheap."""
        return [self.score(fv, cv) for fv, cv in zip(fvs, cvs, strict=True)]

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


class LightGBMScorer:
    """LightGBM-backed scorer (PR15, replaces the Phase 1 `MLScorerStub`).

    Loads a pickled LightGBM Booster + JSON sidecar written by
    `bloasis ml train`. Uses the FeatureVector's 23-column slice as
    input; converts cross-section raw predictions to unit scores via
    z-score + Normal CDF (so top decile of predictions maps to ~ top
    decile of [0, 1]).

    Single-row `score()` falls back to a logistic squash of the raw
    prediction normalized by training-time IC scale — this is a rough
    approximation; the production path is `score_cross_section()`,
    which the engine calls per timestep.
    """

    # PR16: top-K SHAP contributors surfaced per `Rationale`.
    SHAP_TOP_K = 5

    def __init__(self, *, cfg: ScorerConfig, model_path: Path | None = None) -> None:
        from bloasis.ml.training import load_model

        path = Path(model_path or cfg.ml_model_path or "")
        if not path.exists():
            raise FileNotFoundError(f"ml model not found at {path}")

        self._cfg = cfg
        self._model = load_model(path)
        # Sidecar JSON written by ml.training.save_model.
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            import json

            self.metadata: dict[str, Any] = json.loads(sidecar.read_text())
        else:
            self.metadata = {}
        self.feature_names: list[str] = list(
            self.metadata.get("feature_names") or self._model.feature_name()
        )
        # PR16: SHAP TreeExplainer for per-feature contributions. Cheap to
        # construct, expensive to call per-row → we batch in cross-section.
        import shap

        self._shap_explainer = shap.TreeExplainer(self._model)

    # ------------------------------------------------------------------
    # Cross-section batch (production path)
    # ------------------------------------------------------------------

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        import numpy as np
        import pandas as pd

        # Build a DataFrame matching the model's feature_names order.
        rows: list[dict[str, float]] = []
        for fv in fvs:
            rows.append({name: float(getattr(fv, name)) for name in self.feature_names})
        X = pd.DataFrame(rows, columns=self.feature_names)
        for col in self.feature_names:
            X[col] = pd.to_numeric(X[col], errors="coerce")

        preds = np.asarray(self._model.predict(X))
        unit_scores = _zscore_to_unit(preds)
        # PR16: batch SHAP for the whole cross-section (much cheaper than
        # one explainer call per row).
        shap_values = np.asarray(self._shap_explainer.shap_values(X))

        out: list[ScoredCandidate] = []
        for i, (fv, cv, raw, unit) in enumerate(zip(fvs, cvs, preds, unit_scores, strict=True)):
            out.append(
                self._build_scored(
                    fv,
                    cv,
                    raw=float(raw),
                    unit=float(unit),
                    shap_row=shap_values[i],
                    feature_row=X.iloc[i],
                )
            )
        return out

    # ------------------------------------------------------------------
    # Single-row score (Scorer protocol compatibility)
    # ------------------------------------------------------------------

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        import numpy as np
        import pandas as pd

        row = pd.DataFrame(
            [{name: float(getattr(fv, name)) for name in self.feature_names}],
            columns=self.feature_names,
        )
        for col in self.feature_names:
            row[col] = pd.to_numeric(row[col], errors="coerce")
        raw = float(self._model.predict(row)[0])
        # No cross-section here — sigmoid-like squash. Production path
        # uses score_cross_section() which has proper cross-section z-score.
        unit = 1.0 / (1.0 + math.exp(-raw / 0.05))  # 5% return ≈ 0.73
        shap_row = np.asarray(self._shap_explainer.shap_values(row))[0]
        return self._build_scored(
            fv, cv, raw=raw, unit=unit, shap_row=shap_row, feature_row=row.iloc[0]
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _build_scored(
        self,
        fv: FeatureVector,
        cv: CompositeVector,
        *,
        raw: float,
        unit: float,
        shap_row: np.ndarray,
        feature_row: pd.Series,
    ) -> ScoredCandidate:
        unit = max(0.0, min(1.0, unit))
        # PR16: top-K SHAP contributors, sorted by |SHAP value| desc.
        # Each FactorContribution.name is a feature name, .contribution is
        # the SHAP value (can be negative — the feature pushed the
        # prediction down), .composite_score is the feature's raw value
        # (so display can show "per=2.5 → SHAP +0.34").
        idx_by_abs = sorted(
            range(len(shap_row)),
            key=lambda i: abs(float(shap_row[i])),
            reverse=True,
        )[: self.SHAP_TOP_K]
        contributions: tuple[FactorContribution, ...] = tuple(
            FactorContribution(
                name=str(self.feature_names[i]),
                composite_score=float(feature_row.iloc[i]),
                weight=1.0,
                contribution=float(shap_row[i]),
                inputs={str(self.feature_names[i]): float(feature_row.iloc[i])},
            )
            for i in idx_by_abs
        )
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=unit,
            rationale=Rationale(
                contributions=contributions,
                triggers=(),
                risks=(),
            ),
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


def _zscore_to_unit(preds: np.ndarray) -> np.ndarray:
    """Map raw cross-section predictions to [0, 1] via z-score → Normal CDF.

    This preserves cross-section RANKING while spreading values across the
    whole [0, 1] range — important for entry/exit thresholding (otherwise
    LightGBM's tightly-clustered regression outputs would all sit near
    sigmoid(0) ≈ 0.5).
    """
    import numpy as np

    arr = np.asarray(preds, dtype=np.float64).ravel()
    if arr.size == 0:
        return arr
    mu = float(np.nanmean(arr))
    sd = float(np.nanstd(arr, ddof=1)) if arr.size >= 2 else 0.0
    if sd <= 0 or not math.isfinite(sd):
        # Degenerate cross-section (single symbol or all-equal preds) →
        # neutral 0.5 for everyone.
        return np.full_like(arr, 0.5, dtype=np.float64)
    z = (arr - mu) / sd
    # Normal CDF without scipy: 0.5 * (1 + erf(z / sqrt(2)))
    cdf = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    return np.asarray(cdf, dtype=np.float64)
