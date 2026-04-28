"""Tests for `bloasis.risk` — RiskEvaluator + RiskDecision."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bloasis.config import RiskConfig
from bloasis.risk import MarketState, PortfolioState, RiskEvaluator
from bloasis.signal import TradingSignal

NOW = datetime.now(tz=UTC)


def _signal(
    action: str = "BUY",
    *,
    target_size_pct: float = 0.05,
    sector: str | None = "Technology",
    symbol: str = "AAPL",
) -> TradingSignal:
    return TradingSignal(
        timestamp=NOW,
        symbol=symbol,
        action=action,  # type: ignore[arg-type]
        confidence=0.8,
        target_size_pct=target_size_pct,
        entry_price=100.0,
        sector=sector,
    )


def _market(vix: float = 18.0) -> MarketState:
    return MarketState(timestamp=NOW, vix=vix)


def _risk_cfg(**overrides: float) -> RiskConfig:
    base = dict(
        vix_extreme=40.0,
        vix_high=30.0,
        max_single_order_pct=0.10,
        max_sector_concentration=0.30,
    )
    base.update(overrides)
    return RiskConfig(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SELL / HOLD pass-through
# ---------------------------------------------------------------------------


def test_sell_always_approved() -> None:
    ev = RiskEvaluator(_risk_cfg())
    d = ev.evaluate(_signal(action="SELL"), PortfolioState(), _market(vix=45.0))
    assert d.action == "APPROVE"
    assert d.adjusted_size_pct == 0.0


def test_hold_always_approved() -> None:
    ev = RiskEvaluator(_risk_cfg())
    d = ev.evaluate(_signal(action="HOLD"), PortfolioState(), _market(vix=45.0))
    assert d.action == "APPROVE"


# ---------------------------------------------------------------------------
# VIX rules
# ---------------------------------------------------------------------------


def test_extreme_vix_rejects_buy() -> None:
    ev = RiskEvaluator(_risk_cfg(vix_extreme=40.0))
    d = ev.evaluate(_signal(action="BUY"), PortfolioState(), _market(vix=45.0))
    assert d.action == "REJECT"
    assert any("VIX" in r for r in d.reasons)


def test_high_vix_halves_size() -> None:
    ev = RiskEvaluator(_risk_cfg(vix_high=30.0))
    d = ev.evaluate(
        _signal(target_size_pct=0.10),
        PortfolioState(),
        _market(vix=35.0),
    )
    assert d.action in ("APPROVE", "ADJUST")
    assert d.adjusted_size_pct == pytest.approx(0.05)
    assert any("halved" in r for r in d.reasons)


def test_normal_vix_no_size_change_when_within_caps() -> None:
    ev = RiskEvaluator(_risk_cfg())
    d = ev.evaluate(
        _signal(target_size_pct=0.05),
        PortfolioState(),
        _market(vix=18.0),
    )
    assert d.action == "APPROVE"
    assert d.adjusted_size_pct == 0.05


# ---------------------------------------------------------------------------
# Single-order cap
# ---------------------------------------------------------------------------


def test_single_order_cap_applied() -> None:
    ev = RiskEvaluator(_risk_cfg(max_single_order_pct=0.05))
    d = ev.evaluate(
        _signal(target_size_pct=0.20),
        PortfolioState(),
        _market(),
    )
    assert d.action == "ADJUST"
    assert d.adjusted_size_pct == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Sector concentration cap
# ---------------------------------------------------------------------------


def test_sector_concentration_clips_size() -> None:
    ev = RiskEvaluator(_risk_cfg(max_sector_concentration=0.30))
    portfolio = PortfolioState(sector_concentrations={"Technology": 0.25})
    d = ev.evaluate(
        _signal(target_size_pct=0.10, sector="Technology"),
        portfolio,
        _market(),
    )
    assert d.action == "ADJUST"
    # Already 25%, cap 30%, so allowed = 5%.
    assert d.adjusted_size_pct == pytest.approx(0.05)


def test_sector_at_cap_rejects_new_buy() -> None:
    ev = RiskEvaluator(_risk_cfg(max_sector_concentration=0.30))
    portfolio = PortfolioState(sector_concentrations={"Technology": 0.30})
    d = ev.evaluate(
        _signal(target_size_pct=0.05, sector="Technology"),
        portfolio,
        _market(),
    )
    assert d.action == "REJECT"


def test_other_sector_unaffected_by_concentration() -> None:
    ev = RiskEvaluator(_risk_cfg(max_sector_concentration=0.30))
    portfolio = PortfolioState(sector_concentrations={"Energy": 0.30})
    d = ev.evaluate(
        _signal(target_size_pct=0.05, sector="Technology"),
        portfolio,
        _market(),
    )
    assert d.action == "APPROVE"
    assert d.adjusted_size_pct == 0.05


def test_unknown_sector_treated_as_zero_existing() -> None:
    ev = RiskEvaluator(_risk_cfg(max_sector_concentration=0.30))
    d = ev.evaluate(
        _signal(target_size_pct=0.05, sector=None),
        PortfolioState(),
        _market(),
    )
    assert d.action == "APPROVE"


# ---------------------------------------------------------------------------
# Stacked rules
# ---------------------------------------------------------------------------


def test_high_vix_and_sector_cap_both_apply() -> None:
    """VIX halve → 0.10 → 0.05; sector concentration further clips to 0.03."""
    ev = RiskEvaluator(_risk_cfg(vix_high=30.0, max_sector_concentration=0.30))
    portfolio = PortfolioState(sector_concentrations={"Technology": 0.27})
    d = ev.evaluate(
        _signal(target_size_pct=0.10, sector="Technology"),
        portfolio,
        _market(vix=32.0),
    )
    assert d.action == "ADJUST"
    # 0.10 → 0.05 (VIX), then sector cap 0.30 - 0.27 = 0.03
    assert d.adjusted_size_pct == pytest.approx(0.03)
    assert any("halved" in r for r in d.reasons)
    assert any("sector" in r for r in d.reasons)
