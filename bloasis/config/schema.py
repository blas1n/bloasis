"""Pydantic models for the strategy YAML config.

A loaded `StrategyConfig` is the canonical, validated, and normalized
representation of a backtest or live strategy. All consumers (backtest
engine, scorer, signal generator, risk evaluator) take this as input.

Validation includes auto-normalization of weights and allocation strategies
so users editing YAML do not have to manually rebalance numerics during
hyperparameter tuning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------


UniverseSource = Literal["sp500", "sp500_historical", "custom_csv"]


class UniverseConfig(BaseModel):
    """Defines the pool of symbols considered before pre-filtering.

    Universe is intentionally separate from `pre_filter`: universe is the
    "playing field", pre_filter is the first-pass cutoff. Keeping them
    distinct lets us A/B different filter thresholds on the same universe.
    """

    model_config = ConfigDict(extra="forbid")

    source: UniverseSource = "sp500"
    custom_csv_path: Path | None = None

    @model_validator(mode="after")
    def _validate_csv_path(self) -> UniverseConfig:
        if self.source == "custom_csv" and self.custom_csv_path is None:
            raise ValueError("universe.custom_csv_path required when source=custom_csv")
        return self


# ---------------------------------------------------------------------------
# Pre-filter
# ---------------------------------------------------------------------------


class PreFilterConfig(BaseModel):
    """Deterministic first-pass filter applied to universe.

    Operates on cached fundamentals. Operates uniformly across all universe
    sources so backtests with different sources are comparable.
    """

    model_config = ConfigDict(extra="forbid")

    min_market_cap: float = Field(default=1_000_000_000, ge=0)
    max_pe_ratio: float = Field(default=25.0, gt=0)
    min_dollar_volume: float = Field(default=5_000_000, ge=0)
    exclude_sectors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


ScorerType = Literal[
    "rule",
    "ml",
    "jt_momentum",
    "pead",
    "pead_jt_intersect",
    "fundamental_llm",
    "fundamental_llm_jt_intersect",
    "edgar_textdiff",
    "edgar_textdiff_jt_intersect",
]
RegimeName = Literal["crisis", "bear", "sideways", "recovery", "bull"]


class WeightsConfig(BaseModel):
    """Composite factor weights. Auto-normalized to sum to 1.0."""

    model_config = ConfigDict(extra="forbid")

    value: float = Field(default=0.18, ge=0)
    quality: float = Field(default=0.15, ge=0)
    momentum: float = Field(default=0.18, ge=0)
    technical: float = Field(default=0.12, ge=0)
    volatility: float = Field(default=0.12, ge=0)
    liquidity: float = Field(default=0.10, ge=0)
    sentiment: float = Field(default=0.15, ge=0)

    @model_validator(mode="after")
    def _normalize(self) -> WeightsConfig:
        values = self.model_dump()
        total = sum(values.values())
        if total <= 0:
            raise ValueError("scorer.weights must contain at least one positive entry")
        for name, v in values.items():
            object.__setattr__(self, name, v / total)
        return self


class ThresholdsConfig(BaseModel):
    """Trigger and risk thresholds used in Rationale narrative."""

    model_config = ConfigDict(extra="forbid")

    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    strong_momentum_20d: float = 0.10
    high_volatility_ann: float = 0.40
    elevated_vix: float = 25.0
    high_leverage_de: float = 2.0
    strong_trend_adx: float = 25.0


class ScorerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ScorerType = "rule"
    ml_model_path: Path | None = None

    weights: WeightsConfig = Field(default_factory=WeightsConfig)
    regime_multipliers: dict[RegimeName, dict[str, float]] = Field(default_factory=dict)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)

    entry_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    exit_threshold: float = Field(default=0.40, ge=0.0, le=1.0)

    jt_top_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    jt_vol_scale: bool = False
    # PR19 — Residual / idiosyncratic momentum (Blitz-Hanauer-Vidojevic 2020).
    # When true, scorer ranks by `residual_momentum_252_21` (market-beta-
    # residualized) instead of raw `momentum_252_21`. Drop-in fix for JT's
    # drawdown failure — same return, half the vol.
    jt_residual: bool = False

    pead_top_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    pead_drift_days: int = Field(default=60, gt=0)

    fundamental_llm_top_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    fundamental_llm_model: str = "ollama_chat/llama3.2:3b"
    fundamental_llm_api_base: str = "http://localhost:11434"

    edgar_textdiff_top_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    edgar_filing_lag_days: int = Field(default=90, ge=0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> ScorerConfig:
        if self.exit_threshold >= self.entry_threshold:
            raise ValueError(
                "scorer.exit_threshold must be < entry_threshold "
                f"(got exit={self.exit_threshold}, entry={self.entry_threshold})"
            )
        if self.type == "ml" and self.ml_model_path is None:
            raise ValueError("scorer.ml_model_path required when type=ml")
        return self


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


ProfitTierType = Literal["target", "trailing"]


class ProfitTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fraction: float = Field(ge=0.0, le=1.0)
    type: ProfitTierType
    atr_mult: float = Field(gt=0.0)


class SignalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atr_stop_multiplier: float = Field(default=2.0, gt=0.0)
    atr_tp_multiplier: float = Field(default=3.0, gt=0.0)
    position_size_max_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    profit_tiers: list[ProfitTier] = Field(default_factory=list)

    # Rebalance every N trading days (default 1 = daily, original behaviour).
    # Larger values reduce turnover and may dampen DD. Stop-loss / profit-tier
    # exits still evaluate every trading day regardless of this setting.
    rebalance_days: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_tiers(self) -> SignalConfig:
        if not self.profit_tiers:
            return self
        total = sum(t.fraction for t in self.profit_tiers)
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"signal.profit_tiers fractions must sum to 1.0 (got {total:.4f})")
        return self


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vix_extreme: float = Field(default=40.0, gt=0.0)
    vix_high: float = Field(default=30.0, gt=0.0)
    max_single_order_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    max_sector_concentration: float = Field(default=0.30, gt=0.0, le=1.0)

    # Live-trading halt: refuse `bloasis trade live` when realized PnL over
    # `halt_drawdown_lookback_days` falls below `-halt_drawdown_pct *
    # initial_capital`. Set `halt_drawdown_pct=0` to disable. See L009.
    halt_drawdown_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    halt_drawdown_lookback_days: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _validate_vix_order(self) -> RiskConfig:
        if self.vix_high >= self.vix_extreme:
            raise ValueError(
                "risk.vix_high must be < vix_extreme "
                f"(got high={self.vix_high}, extreme={self.vix_extreme})"
            )
        return self


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


FillMode = Literal["market", "limit_with_fallback"]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_mode: FillMode = "limit_with_fallback"
    market_slippage_bps: float = Field(default=5.0, ge=0.0)
    limit_offset_bps: float = Field(default=10.0, ge=0.0)
    limit_timeout_bars: int = Field(default=1, ge=0)
    fees_bps: float = Field(default=0.0, ge=0.0)
    initial_capital: float = Field(default=10_000.0, gt=0.0)


# ---------------------------------------------------------------------------
# Allocation (core + satellite composition)
# ---------------------------------------------------------------------------


AllocationStrategyType = Literal["spy_passive", "strategy"]


class AllocationStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: AllocationStrategyType
    weight: float = Field(ge=0.0)


class AllocationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategies: list[AllocationStrategy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_weights(self) -> AllocationConfig:
        if not self.strategies:
            return self
        total = sum(s.weight for s in self.strategies)
        if total <= 0:
            raise ValueError("allocation.strategies weights must sum > 0")
        for s in self.strategies:
            s.weight = s.weight / total
        names = [s.name for s in self.strategies]
        if len(names) != len(set(names)):
            raise ValueError("allocation.strategies names must be unique")
        return self


# ---------------------------------------------------------------------------
# Data layer (cache TTLs, paths, rate limits)
# ---------------------------------------------------------------------------


class DataConfig(BaseModel):
    """Tunables for the data layer.

    Cache directory holds parquet OHLCV cache and the fja05680 historical
    S&P 500 dataset. `~` is expanded at config load time.
    """

    model_config = ConfigDict(extra="forbid")

    cache_dir: Path = Field(default=Path("~/.cache/bloasis"))
    ohlcv_cache_max_age_hours: int = Field(default=24, ge=0)
    fundamentals_cache_max_age_hours: int = Field(default=24, ge=0)
    sentiment_cache_max_age_hours: int = Field(default=6, ge=0)
    finnhub_rate_per_minute: int = Field(default=60, ge=1, le=300)
    sentiment_lookback_days: int = Field(default=7, ge=1, le=30)

    @model_validator(mode="after")
    def _expand_user(self) -> DataConfig:
        # Expand ~ once at validation time so downstream code can rely on
        # an absolute path.
        object.__setattr__(self, "cache_dir", Path(self.cache_dir).expanduser())
        return self


# ---------------------------------------------------------------------------
# Acceptance criteria (phase gate)
# ---------------------------------------------------------------------------


class AcceptanceCriteria(BaseModel):
    """Phase gate. Backtest must clear all criteria to promote config."""

    model_config = ConfigDict(extra="forbid")

    walk_forward_min_folds: int = Field(default=5, ge=1)
    median_alpha_annualized: float = -0.005
    median_sharpe_vs_spy: float = 1.0
    median_max_dd_ratio_to_spy: float = Field(default=0.85, gt=0.0)


# ---------------------------------------------------------------------------
# Regime overlay (PR12)
# ---------------------------------------------------------------------------


class RegimeOverlayConfig(BaseModel):
    """Barroso-Santa-Clara constant-vol scaling + Daniel-Moskowitz bear gate.

    When enabled, multiplies per-trade position size_pct by a scale factor
    derived from SPY's recent realized vol and 24-month return state. See
    `bloasis/scoring/regime_overlay.py` for math + ~/Docs/bloasis/
    Research_DM_Dynamic_Momentum.md for derivation.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    sigma_target: float = Field(default=0.12, gt=0.0, le=1.0)
    vol_lookback_days: int = Field(default=126, ge=20)
    bear_lookback_days: int = Field(default=504, ge=60)
    bear_scale: float = Field(default=0.5, ge=0.0, le=1.0)
    scale_clip: tuple[float, float] = (0.0, 1.5)

    @model_validator(mode="after")
    def _validate_clip(self) -> RegimeOverlayConfig:
        lo, hi = self.scale_clip
        if not (0.0 <= lo < hi):
            raise ValueError(
                f"scale_clip must be (low, high) with 0 <= low < high; got {self.scale_clip}"
            )
        return self


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


class StrategyConfig(BaseModel):
    """Top-level config. Loaded from YAML, validated, and hashed for run identity."""

    model_config = ConfigDict(extra="forbid")

    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    pre_filter: PreFilterConfig = Field(default_factory=PreFilterConfig)
    scorer: ScorerConfig = Field(default_factory=ScorerConfig)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    allocation: AllocationConfig = Field(default_factory=AllocationConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    regime_overlay: RegimeOverlayConfig = Field(default_factory=RegimeOverlayConfig)
    acceptance_criteria: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
