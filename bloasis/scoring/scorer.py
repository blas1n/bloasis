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


class JTMomentumScorer:
    """Phase 0 redesign — pure rank-based Jegadeesh-Titman 12-1 momentum.

    Top `top_pct` (default 10%) of symbols by `momentum_252_21` get a unit
    score of 0.99 (above the default `entry_threshold=0.65` so they pass);
    everyone else gets 0.0 (below `exit_threshold=0.40`). NaN momentum →
    excluded from ranking, scored as 0.0.

    Why this exists:
    PR12-17 measurement showed bloasis's 7-composite blend + cross-section
    threshold dilutes the long-term momentum signal. The same JT 12-1
    momentum that scores sharpe 1.21 standalone (Quant_Robustness 2026-05-07)
    drops to sharpe 0.30-0.50 once routed through the composite system.

    Phase 0 ships JT 12-1 *raw* — no compositing, no z-score → CDF, just
    rank-based top-decile selection — to recover the standalone alpha.

    Single-row `score()` is degenerate (no cross-section to rank against);
    returns 0.5. Production path is `score_cross_section()` (engine calls
    this per timestep).
    """

    def __init__(
        self,
        cfg: ScorerConfig,
        *,
        top_pct: float = 0.10,
        vol_scale: bool = False,
        residual: bool = False,
        continuous_score: bool = False,
    ) -> None:
        if not 0.0 < top_pct <= 1.0:
            raise ValueError(f"top_pct must be in (0, 1], got {top_pct}")
        self._cfg = cfg
        self._top_pct = top_pct
        self._vol_scale = vol_scale
        self._residual = residual
        self._continuous = continuous_score

    def _signal(self, fv: FeatureVector) -> float:
        # Residual momentum (Blitz-Hanauer-Vidojevic 2020) is the academic
        # drop-in fix for vanilla JT's drawdown failure. Same window, but
        # market-beta-residualized returns — half the vol, no return drop.
        mom = float(fv.residual_momentum_252_21) if self._residual else float(fv.momentum_252_21)
        if math.isnan(mom):
            return float("nan")
        if not self._vol_scale:
            return mom
        vol = float(fv.volatility_20d)
        if math.isnan(vol) or vol <= 0:
            return float("nan")
        return mom / vol

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        # Identify rankable (non-NaN) symbols by their position in the
        # input list (so we can re-emit a ScoredCandidate per input).
        valid_indices: list[tuple[int, float]] = []
        for i, fv in enumerate(fvs):
            sig = self._signal(fv)
            if not math.isnan(sig):
                valid_indices.append((i, sig))

        if self._continuous:
            # Percentile-rank continuous score in [0, 1]. Lets entry/exit
            # threshold gap (hysteresis) keep middle-ranked stocks held
            # rather than cycling. NaN signal → score 0.0.
            scores_by_idx = _percentile_scores(valid_indices, len(fvs))
        else:
            n_select = max(1, int(len(valid_indices) * self._top_pct)) if valid_indices else 0
            valid_sorted = sorted(valid_indices, key=lambda t: t[1], reverse=True)
            top_indices = {idx for idx, _mom in valid_sorted[:n_select]}
            scores_by_idx = {i: (0.99 if i in top_indices else 0.0) for i in range(len(fvs))}

        out: list[ScoredCandidate] = []
        for i, fv in enumerate(fvs):
            score = scores_by_idx.get(i, 0.0)
            out.append(self._build_scored(fv, score=score, momentum=float(fv.momentum_252_21)))
        return out

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        # Without a cross-section we can't rank — return neutral.
        return self._build_scored(fv, score=0.5, momentum=float(fv.momentum_252_21))

    @staticmethod
    def _build_scored(fv: FeatureVector, *, score: float, momentum: float) -> ScoredCandidate:
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=score,
            rationale=Rationale(
                contributions=(
                    FactorContribution(
                        name="momentum_252_21",
                        composite_score=momentum,
                        weight=1.0,
                        contribution=momentum,
                        inputs={"momentum_252_21": momentum},
                    ),
                ),
                triggers=(),
                risks=(),
            ),
        )


def _percentile_scores(valid_indices: list[tuple[int, float]], n_total: int) -> dict[int, float]:
    """Map (index, signal) pairs to [0, 1] percentile-rank scores.

    Higher signal → higher score. Indexes not in `valid_indices` get 0.0.
    Single-valid degenerate case returns 0.5.
    """
    out: dict[int, float] = dict.fromkeys(range(n_total), 0.0)
    if not valid_indices:
        return out
    sorted_by_signal = sorted(valid_indices, key=lambda t: t[1])  # ascending
    n = len(sorted_by_signal)
    if n == 1:
        out[sorted_by_signal[0][0]] = 0.5
        return out
    for rank, (idx, _sig) in enumerate(sorted_by_signal):
        out[idx] = rank / (n - 1)
    return out


class EDGARTextDiffScorer:
    """Phase 3 Candidate D-textdiff — Cohen-Malloy "Lazy Prices" 2020 inverted.

    Academic finding: large 10-K disclosure changes (low cosine similarity,
    big length changes) predict NEGATIVE future returns. We're long-only
    so we invert: HIGH cosine similarity = stable disclosure = our long
    candidate.

    Top `top_pct` by `risk_factors_cosine` get score 0.99. NaN cosine
    excluded. Score is pure cross-section rank, no compute beyond.

    LLM-free — `risk_factors_cosine` is a TF cosine on tokenized Item 1A,
    populated upstream by the engine prefetch (see
    `bloasis.scoring.edgar_textdiff`).
    """

    def __init__(
        self,
        cfg: ScorerConfig,
        *,
        top_pct: float = 0.10,
        continuous_score: bool = False,
    ) -> None:
        if not 0.0 < top_pct <= 1.0:
            raise ValueError(f"top_pct must be in (0, 1], got {top_pct}")
        self._cfg = cfg
        self._top_pct = top_pct
        self._continuous = continuous_score

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        eligibles: list[tuple[int, float]] = []
        for i, fv in enumerate(fvs):
            v = float(fv.risk_factors_cosine)
            if not math.isnan(v):
                eligibles.append((i, v))

        if self._continuous:
            scores_by_idx = _percentile_scores(eligibles, len(fvs))
        else:
            n_select = max(1, int(len(eligibles) * self._top_pct)) if eligibles else 0
            eligibles_sorted = sorted(eligibles, key=lambda t: t[1], reverse=True)
            top_indices = {idx for idx, _v in eligibles_sorted[:n_select]}
            scores_by_idx = {i: (0.99 if i in top_indices else 0.0) for i in range(len(fvs))}

        out: list[ScoredCandidate] = []
        for i, fv in enumerate(fvs):
            out.append(self._build_scored(fv, score=scores_by_idx.get(i, 0.0)))
        return out

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        return self._build_scored(fv, score=0.5)

    @staticmethod
    def _build_scored(fv: FeatureVector, *, score: float) -> ScoredCandidate:
        cos = float(fv.risk_factors_cosine)
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=score,
            rationale=Rationale(
                contributions=(
                    FactorContribution(
                        name="risk_factors_cosine",
                        composite_score=cos,
                        weight=1.0,
                        contribution=cos,
                        inputs={
                            "risk_factors_cosine": cos,
                            "risk_factors_len_change": float(fv.risk_factors_len_change),
                        },
                    ),
                ),
                triggers=(),
                risks=(),
            ),
        )


class FundamentalLLMScorer:
    """Phase 3 Candidate B-modern — LLM-rated fundamental health.

    Cross-section ranking on `fundamental_llm_score` (already populated
    in FeatureVector by upstream LLM pass). Top `top_pct` get score 0.99,
    rest 0.0. NaN scores excluded.

    The LLM call itself happens before `score_cross_section` — this scorer
    is pure compute (matches bloasis architectural rule §2). The pipeline:
    `bloasis.scoring.llm_fundamental.LLMFundamentalScorer` populates
    `ExtractionContext.fundamental_llm_score`, extractor copies it into
    FeatureVector, this scorer reads it.
    """

    def __init__(self, cfg: ScorerConfig, *, top_pct: float = 0.10) -> None:
        if not 0.0 < top_pct <= 1.0:
            raise ValueError(f"top_pct must be in (0, 1], got {top_pct}")
        self._cfg = cfg
        self._top_pct = top_pct

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        eligibles: list[tuple[int, float]] = []
        for i, fv in enumerate(fvs):
            v = float(fv.fundamental_llm_score)
            if not math.isnan(v):
                eligibles.append((i, v))
        n_select = max(1, int(len(eligibles) * self._top_pct)) if eligibles else 0
        eligibles_sorted = sorted(eligibles, key=lambda t: t[1], reverse=True)
        top_indices = {idx for idx, _v in eligibles_sorted[:n_select]}

        out: list[ScoredCandidate] = []
        for i, fv in enumerate(fvs):
            score = 0.99 if i in top_indices else 0.0
            out.append(self._build_scored(fv, score=score))
        return out

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        return self._build_scored(fv, score=0.5)

    @staticmethod
    def _build_scored(fv: FeatureVector, *, score: float) -> ScoredCandidate:
        v = float(fv.fundamental_llm_score)
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=score,
            rationale=Rationale(
                contributions=(
                    FactorContribution(
                        name="fundamental_llm_score",
                        composite_score=v,
                        weight=1.0,
                        contribution=v,
                        inputs={"fundamental_llm_score": v},
                    ),
                ),
                triggers=(),
                risks=(),
            ),
        )


class IntersectScorer:
    """Phase 3 Candidate A4 — combine N orthogonal alpha signals via AND.

    A symbol gets score 0.99 only when EVERY sub-scorer scores it above
    `entry_threshold`. Otherwise 0.0. Designed to capture the case where
    e.g. high momentum AND a positive earnings surprise both confirm a
    buy candidate (academic intuition: orthogonal signals reinforce).

    Sub-scorers must implement `score_cross_section(fvs, cvs)`.
    """

    def __init__(self, cfg: ScorerConfig, *, sub_scorers: list) -> None:  # type: ignore[type-arg]
        if len(sub_scorers) < 2:
            raise ValueError(
                f"IntersectScorer needs at least 2 sub-scorers, got {len(sub_scorers)}"
            )
        self._cfg = cfg
        self._subs = sub_scorers

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        threshold = self._cfg.entry_threshold
        # Run each sub-scorer; track per-symbol pass count.
        pass_counts: dict[str, int] = dict.fromkeys((fv.symbol for fv in fvs), 0)
        for sub in self._subs:
            sub_out = sub.score_cross_section(fvs, cvs)
            for sc in sub_out:
                if sc.score > threshold:
                    pass_counts[sc.symbol] = pass_counts.get(sc.symbol, 0) + 1
        n_required = len(self._subs)
        out: list[ScoredCandidate] = []
        for fv in fvs:
            score = 0.99 if pass_counts.get(fv.symbol, 0) >= n_required else 0.0
            out.append(self._build_scored(fv, score=score))
        return out

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        return self._build_scored(fv, score=0.5)

    @staticmethod
    def _build_scored(fv: FeatureVector, *, score: float) -> ScoredCandidate:
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=score,
            rationale=Rationale(
                contributions=(
                    FactorContribution(
                        name="intersect",
                        composite_score=score,
                        weight=1.0,
                        contribution=score,
                        inputs={},
                    ),
                ),
                triggers=(),
                risks=(),
            ),
        )


class PEADScorer:
    """Phase 3 Candidate A — Post-Earnings Announcement Drift.

    Stocks with a recent positive earnings surprise drift upward for the
    next ~60 days (Bernard-Thomas 1989, Sloan 1996). Eligible stocks are
    those with `last_eps_surprise_pct > 0` AND
    `0 <= days_since_earnings <= drift_days`. Among eligibles, the top
    `top_pct` by `last_eps_surprise_pct` get score 0.99 (passes
    `entry_threshold=0.65`); rest 0.0.

    Spec: ~/Docs/bloasis/Phase3_Modern_Candidates_2026-05-08.md §A
    """

    def __init__(
        self,
        cfg: ScorerConfig,
        *,
        top_pct: float = 0.10,
        drift_days: int = 60,
    ) -> None:
        if not 0.0 < top_pct <= 1.0:
            raise ValueError(f"top_pct must be in (0, 1], got {top_pct}")
        if drift_days <= 0:
            raise ValueError(f"drift_days must be > 0, got {drift_days}")
        self._cfg = cfg
        self._top_pct = top_pct
        self._drift_days = drift_days

    def _eligible(self, fv: FeatureVector) -> float | None:
        """Return surprise% if eligible (positive beat, within drift), else None."""
        surprise = float(fv.last_eps_surprise_pct)
        days = float(fv.days_since_earnings)
        if math.isnan(surprise) or math.isnan(days):
            return None
        if surprise <= 0.0:
            return None
        if days < 0.0 or days > self._drift_days:
            return None
        return surprise

    def score_cross_section(
        self, fvs: list[FeatureVector], cvs: list[CompositeVector]
    ) -> list[ScoredCandidate]:
        if not fvs:
            return []
        eligibles: list[tuple[int, float]] = []
        for i, fv in enumerate(fvs):
            sig = self._eligible(fv)
            if sig is not None:
                eligibles.append((i, sig))

        n_select = max(1, int(len(eligibles) * self._top_pct)) if eligibles else 0
        eligibles_sorted = sorted(eligibles, key=lambda t: t[1], reverse=True)
        top_indices = {idx for idx, _sig in eligibles_sorted[:n_select]}

        out: list[ScoredCandidate] = []
        for i, fv in enumerate(fvs):
            score = 0.99 if i in top_indices else 0.0
            out.append(self._build_scored(fv, score=score))
        return out

    def score(self, fv: FeatureVector, cv: CompositeVector) -> ScoredCandidate:
        # Without a cross-section we can't rank — return neutral.
        return self._build_scored(fv, score=0.5)

    @staticmethod
    def _build_scored(fv: FeatureVector, *, score: float) -> ScoredCandidate:
        surprise = float(fv.last_eps_surprise_pct)
        days = float(fv.days_since_earnings)
        return ScoredCandidate(
            symbol=fv.symbol,
            timestamp=fv.timestamp,
            score=score,
            rationale=Rationale(
                contributions=(
                    FactorContribution(
                        name="last_eps_surprise_pct",
                        composite_score=surprise,
                        weight=1.0,
                        contribution=surprise,
                        inputs={
                            "last_eps_surprise_pct": surprise,
                            "days_since_earnings": days,
                        },
                    ),
                ),
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
