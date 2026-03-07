"""Tests for core/risk_rules.py — no mocks needed."""

from decimal import Decimal

from app.core.models import (
    OrderRequest,
    Portfolio,
    Position,
    RiskDecision,
    RiskLimits,
)
from app.core.risk_rules import evaluate_risk


def _make_portfolio(
    total_value: Decimal = Decimal("100000"),
    positions: list[Position] | None = None,
) -> Portfolio:
    return Portfolio(
        user_id="test-user",
        total_value=total_value,
        cash_balance=Decimal("50000"),
        positions=positions or [],
    )


def _make_order(
    symbol: str = "AAPL",
    side: str = "buy",
    qty: Decimal = Decimal("10"),
    price: Decimal = Decimal("150"),
    sector: str = "Technology",
) -> OrderRequest:
    return OrderRequest(
        user_id="test-user",
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        sector=sector,
    )


class TestEmptyPortfolio:
    def test_no_funds_rejected(self):
        result = evaluate_risk(
            order=_make_order(),
            portfolio=_make_portfolio(total_value=Decimal("0")),
            vix=20.0,
        )
        assert result.action == RiskDecision.REJECT
        assert result.risk_score == 1.0
        assert "Insufficient funds" in result.reasoning


class TestVIXRules:
    def test_extreme_vix_rejects_buy(self):
        result = evaluate_risk(
            order=_make_order(side="buy"),
            portfolio=_make_portfolio(),
            vix=45.0,
        )
        assert result.action == RiskDecision.REJECT
        assert "extreme volatility" in result.reasoning.lower()

    def test_extreme_vix_allows_sell(self):
        result = evaluate_risk(
            order=_make_order(side="sell"),
            portfolio=_make_portfolio(),
            vix=45.0,
        )
        assert result.action != RiskDecision.REJECT

    def test_high_vix_reduces_size(self):
        result = evaluate_risk(
            order=_make_order(qty=Decimal("10"), price=Decimal("100")),
            portfolio=_make_portfolio(),
            vix=35.0,
        )
        # Order is 1% of portfolio, within limits, but VIX is high
        assert result.warnings
        assert any("vix" in w.lower() for w in result.warnings)

    def test_normal_vix_no_warnings(self):
        result = evaluate_risk(
            order=_make_order(qty=Decimal("10"), price=Decimal("100")),
            portfolio=_make_portfolio(),
            vix=15.0,
        )
        assert result.action == RiskDecision.APPROVE
        assert not result.warnings


class TestPositionSizeRules:
    def test_order_exceeds_single_limit(self):
        # Default max_single_order = 5%, order = $6000 / $100000 = 6%
        result = evaluate_risk(
            order=_make_order(qty=Decimal("40"), price=Decimal("150")),
            portfolio=_make_portfolio(),
            vix=15.0,
        )
        assert result.action == RiskDecision.ADJUST
        assert result.adjusted_size is not None
        assert result.adjusted_size > 0

    def test_order_within_limit(self):
        # $1500 / $100000 = 1.5%, well within 5%
        result = evaluate_risk(
            order=_make_order(qty=Decimal("10"), price=Decimal("150")),
            portfolio=_make_portfolio(),
            vix=15.0,
        )
        assert result.action == RiskDecision.APPROVE


class TestSectorConcentration:
    def test_exceeds_sector_limit(self):
        # Existing tech position: $28000 (28%)
        # New order: $4000 (4%, within single order limit) → sector total 32% > 30%
        positions = [
            Position(
                symbol="MSFT",
                quantity=100,
                avg_cost=Decimal("280"),
                current_price=Decimal("280"),
                current_value=Decimal("28000"),
                sector="Technology",
            ),
        ]
        result = evaluate_risk(
            order=_make_order(
                symbol="AAPL",
                qty=Decimal("20"),
                price=Decimal("200"),
                sector="Technology",
            ),
            portfolio=_make_portfolio(positions=positions),
            vix=15.0,
        )
        assert result.action == RiskDecision.ADJUST
        assert "concentration" in result.reasoning.lower()

    def test_different_sector_ok(self):
        positions = [
            Position(
                symbol="MSFT",
                quantity=100,
                avg_cost=Decimal("250"),
                current_price=Decimal("250"),
                current_value=Decimal("25000"),
                sector="Technology",
            ),
        ]
        result = evaluate_risk(
            order=_make_order(
                symbol="JNJ",
                qty=Decimal("10"),
                price=Decimal("150"),
                sector="Healthcare",
            ),
            portfolio=_make_portfolio(positions=positions),
            vix=15.0,
        )
        assert result.action == RiskDecision.APPROVE


class TestCustomLimits:
    def test_custom_vix_threshold(self):
        limits = RiskLimits(vix_extreme_threshold=Decimal("50.0"))
        result = evaluate_risk(
            order=_make_order(side="buy"),
            portfolio=_make_portfolio(),
            vix=45.0,
            limits=limits,
        )
        # VIX 45 is below custom extreme threshold of 50
        assert result.action != RiskDecision.REJECT
