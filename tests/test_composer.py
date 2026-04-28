"""Tests for StrategyComposer — capital splits + SPY share computation."""

from __future__ import annotations

import pytest

from bloasis.allocation import StrategyComposer
from bloasis.allocation.composer import make_composer
from bloasis.config import AllocationConfig, AllocationStrategy


def _cfg(*pairs: tuple[str, str, float]) -> AllocationConfig:
    """Build AllocationConfig from (name, type, weight) tuples."""
    return AllocationConfig(
        strategies=[
            AllocationStrategy(name=n, type=t, weight=w)  # type: ignore[arg-type]
            for n, t, w in pairs
        ]
    )


def test_empty_strategies_routes_all_to_strategy_leg() -> None:
    cfg = AllocationConfig(strategies=[])
    plan = StrategyComposer(cfg).plan(total_capital=10_000.0, spy_price=400.0)
    assert plan.total_capital == 10_000.0
    assert plan.strategy_capital == pytest.approx(10_000.0)
    assert plan.spy_share_qty is None
    assert len(plan.legs) == 1
    assert plan.legs[0].strategy_type == "strategy"
    assert plan.legs[0].capital == pytest.approx(10_000.0)


def test_70_30_split_assigns_capital_proportionally() -> None:
    cfg = _cfg(("core", "spy_passive", 0.7), ("alpha", "strategy", 0.3))
    plan = StrategyComposer(cfg).plan(total_capital=100_000.0, spy_price=500.0)
    assert plan.total_capital == 100_000.0
    assert plan.strategy_capital == pytest.approx(30_000.0)
    # 70k / 500 = 140 SPY shares.
    assert plan.spy_share_qty == pytest.approx(140.0)


def test_weight_normalization_handles_unnormalized_input() -> None:
    # Weights 7 + 3 normalize to 0.7 + 0.3.
    cfg = _cfg(("core", "spy_passive", 7.0), ("alpha", "strategy", 3.0))
    plan = StrategyComposer(cfg).plan(total_capital=1000.0, spy_price=10.0)
    assert plan.strategy_capital == pytest.approx(300.0)
    assert plan.spy_share_qty == pytest.approx(70.0)


def test_no_spy_leg_means_no_spy_qty() -> None:
    cfg = _cfg(("alpha", "strategy", 1.0))
    plan = StrategyComposer(cfg).plan(total_capital=10_000.0, spy_price=400.0)
    assert plan.spy_share_qty is None
    assert plan.strategy_capital == pytest.approx(10_000.0)


def test_spy_qty_none_when_price_missing() -> None:
    cfg = _cfg(("core", "spy_passive", 1.0))
    plan = StrategyComposer(cfg).plan(total_capital=10_000.0, spy_price=None)
    assert plan.spy_share_qty is None


def test_spy_qty_none_when_price_non_positive() -> None:
    cfg = _cfg(("core", "spy_passive", 1.0))
    plan = StrategyComposer(cfg).plan(total_capital=10_000.0, spy_price=0.0)
    assert plan.spy_share_qty is None


def test_has_spy_leg_classifier() -> None:
    assert StrategyComposer.has_spy_leg(_cfg(("c", "spy_passive", 1.0))) is True
    assert StrategyComposer.has_spy_leg(_cfg(("a", "strategy", 1.0))) is False
    assert StrategyComposer.has_spy_leg(AllocationConfig(strategies=[])) is False


def test_make_composer_accepts_single_strategy() -> None:
    single = AllocationStrategy(name="solo", type="strategy", weight=1.0)
    composer = make_composer(single)
    plan = composer.plan(total_capital=500.0, spy_price=None)
    assert plan.strategy_capital == pytest.approx(500.0)


def test_make_composer_accepts_full_config() -> None:
    cfg = _cfg(("a", "strategy", 1.0))
    composer = make_composer(cfg)
    assert isinstance(composer, StrategyComposer)


def test_legs_preserve_input_order_and_names() -> None:
    cfg = _cfg(
        ("core", "spy_passive", 0.5),
        ("alpha", "strategy", 0.3),
        ("beta", "strategy", 0.2),
    )
    plan = StrategyComposer(cfg).plan(total_capital=10_000.0, spy_price=100.0)
    names = [leg.name for leg in plan.legs]
    assert names == ["core", "alpha", "beta"]
    types = [leg.strategy_type for leg in plan.legs]
    assert types == ["spy_passive", "strategy", "strategy"]
    # Combined strategy_capital = 0.3 + 0.2 of total.
    assert plan.strategy_capital == pytest.approx(5_000.0)
