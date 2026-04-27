"""Tests for `bloasis.config.schema`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bloasis.config import StrategyConfig
from bloasis.config.schema import (
    AcceptanceCriteria,
    AllocationConfig,
    AllocationStrategy,
    ExecutionConfig,
    PreFilterConfig,
    ProfitTier,
    RiskConfig,
    ScorerConfig,
    SignalConfig,
    UniverseConfig,
    WeightsConfig,
)

# ---------------------------------------------------------------------------
# baseline.yaml round-trip
# ---------------------------------------------------------------------------


def test_baseline_config_validates(baseline_raw: dict) -> None:
    cfg = StrategyConfig.model_validate(baseline_raw)
    assert cfg.universe.source == "sp500"
    assert cfg.scorer.type == "rule"
    assert cfg.execution.fill_mode == "limit_with_fallback"


def test_baseline_weights_sum_to_one(baseline_config: StrategyConfig) -> None:
    weights = baseline_config.scorer.weights.model_dump()
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_baseline_allocation_weights_sum_to_one(baseline_config: StrategyConfig) -> None:
    total = sum(s.weight for s in baseline_config.allocation.strategies)
    assert total == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# UniverseConfig
# ---------------------------------------------------------------------------


def test_universe_custom_csv_requires_path() -> None:
    with pytest.raises(ValidationError, match="custom_csv_path required"):
        UniverseConfig(source="custom_csv")


def test_universe_sp500_no_path_required() -> None:
    cfg = UniverseConfig(source="sp500")
    assert cfg.custom_csv_path is None


def test_universe_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        UniverseConfig.model_validate({"source": "sp500", "bogus": True})


# ---------------------------------------------------------------------------
# WeightsConfig — auto-normalization
# ---------------------------------------------------------------------------


def test_weights_auto_normalize() -> None:
    w = WeightsConfig(
        value=2.0,
        quality=2.0,
        momentum=2.0,
        technical=2.0,
        volatility=2.0,
        liquidity=2.0,
        sentiment=2.0,
    )
    total = sum(w.model_dump().values())
    assert total == pytest.approx(1.0, abs=1e-9)
    # equal inputs → equal normalized weights
    assert w.value == pytest.approx(1.0 / 7, abs=1e-9)


def test_weights_zero_total_rejected() -> None:
    with pytest.raises(ValidationError, match="positive entry"):
        WeightsConfig(
            value=0,
            quality=0,
            momentum=0,
            technical=0,
            volatility=0,
            liquidity=0,
            sentiment=0,
        )


def test_weights_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        WeightsConfig(value=-0.1)


# ---------------------------------------------------------------------------
# ScorerConfig
# ---------------------------------------------------------------------------


def test_scorer_exit_must_be_below_entry() -> None:
    with pytest.raises(ValidationError, match="exit_threshold"):
        ScorerConfig(entry_threshold=0.5, exit_threshold=0.5)
    with pytest.raises(ValidationError, match="exit_threshold"):
        ScorerConfig(entry_threshold=0.4, exit_threshold=0.6)


def test_scorer_ml_requires_model_path() -> None:
    with pytest.raises(ValidationError, match="ml_model_path required"):
        ScorerConfig(type="ml")


def test_scorer_rule_no_model_path_required() -> None:
    cfg = ScorerConfig(type="rule")
    assert cfg.ml_model_path is None


# ---------------------------------------------------------------------------
# SignalConfig — profit tier sum
# ---------------------------------------------------------------------------


def test_profit_tiers_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        SignalConfig(
            profit_tiers=[
                ProfitTier(fraction=0.5, type="target", atr_mult=1.5),
                ProfitTier(fraction=0.3, type="trailing", atr_mult=2.0),
            ]
        )


def test_profit_tiers_empty_allowed() -> None:
    SignalConfig(profit_tiers=[])


def test_profit_tiers_rounding_tolerance() -> None:
    SignalConfig(
        profit_tiers=[
            ProfitTier(fraction=0.33, type="target", atr_mult=1.5),
            ProfitTier(fraction=0.33, type="target", atr_mult=3.0),
            ProfitTier(fraction=0.34, type="trailing", atr_mult=2.0),
        ]
    )


# ---------------------------------------------------------------------------
# RiskConfig
# ---------------------------------------------------------------------------


def test_risk_vix_high_must_be_below_extreme() -> None:
    with pytest.raises(ValidationError, match="vix_high"):
        RiskConfig(vix_high=40, vix_extreme=30)


def test_risk_max_pct_bounded() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(max_single_order_pct=1.5)


# ---------------------------------------------------------------------------
# AllocationConfig — auto-normalize, unique names
# ---------------------------------------------------------------------------


def test_allocation_normalizes_weights() -> None:
    cfg = AllocationConfig(
        strategies=[
            AllocationStrategy(name="a", type="spy_passive", weight=1),
            AllocationStrategy(name="b", type="strategy", weight=3),
        ]
    )
    weights = {s.name: s.weight for s in cfg.strategies}
    assert weights["a"] == pytest.approx(0.25)
    assert weights["b"] == pytest.approx(0.75)


def test_allocation_rejects_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="unique"):
        AllocationConfig(
            strategies=[
                AllocationStrategy(name="x", type="spy_passive", weight=0.5),
                AllocationStrategy(name="x", type="strategy", weight=0.5),
            ]
        )


def test_allocation_empty_allowed() -> None:
    AllocationConfig(strategies=[])


# ---------------------------------------------------------------------------
# Cross-section: defaults round-trip
# ---------------------------------------------------------------------------


def test_strategy_config_defaults_round_trip() -> None:
    cfg = StrategyConfig()
    # All sections present and defaultable
    assert isinstance(cfg.universe, UniverseConfig)
    assert isinstance(cfg.pre_filter, PreFilterConfig)
    assert isinstance(cfg.scorer, ScorerConfig)
    assert isinstance(cfg.signal, SignalConfig)
    assert isinstance(cfg.risk, RiskConfig)
    assert isinstance(cfg.execution, ExecutionConfig)
    assert isinstance(cfg.allocation, AllocationConfig)
    assert isinstance(cfg.acceptance_criteria, AcceptanceCriteria)
