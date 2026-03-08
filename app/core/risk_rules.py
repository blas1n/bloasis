"""Pure risk evaluation rules.

No infrastructure dependencies. All functions take domain models and return results.
Replaces the 3-agent voting system (~620 lines) with deterministic rules (~60 lines).

Source: services/risk-committee/src/agents/*.py, service.py
"""

from decimal import Decimal

from .models import (
    OrderRequest,
    OrderSide,
    Portfolio,
    RiskDecision,
    RiskLimits,
    RiskResult,
)


def evaluate_risk(
    order: OrderRequest,
    portfolio: Portfolio,
    vix: float | Decimal,
    limits: RiskLimits | None = None,
) -> RiskResult:
    """Evaluate order risk using deterministic rules.

    Checks (in order):
    1. Extreme VIX → reject new buys
    2. High VIX → reduce size by 50%
    3. Single order size limit
    4. Sector concentration limit

    Args:
        order: Order to evaluate.
        portfolio: Current portfolio state.
        vix: Current VIX value.
        limits: Risk limits (uses defaults if None).

    Returns:
        RiskResult with action and reasoning.
    """
    if limits is None:
        limits = RiskLimits()

    warnings: list[str] = []

    # No funds — reject order
    if portfolio.total_value == 0:
        return RiskResult(
            action=RiskDecision.REJECT,
            risk_score=1.0,
            reasoning="Insufficient funds — sync portfolio with broker first",
        )

    order_value = order.qty * order.price
    portfolio_value = portfolio.total_value
    order_pct = order_value / portfolio_value
    vix_d = Decimal(str(vix))

    # Sell-specific validation: ensure position exists with sufficient quantity
    if order.side == OrderSide.SELL:
        position = next((p for p in portfolio.positions if p.symbol == order.symbol), None)
        if not position or position.quantity <= 0:
            return RiskResult(
                action=RiskDecision.REJECT,
                risk_score=1.0,
                reasoning=f"Cannot sell {order.symbol}: no open position",
            )
        if order.qty > position.quantity:
            return RiskResult(
                action=RiskDecision.REJECT,
                risk_score=0.8,
                reasoning=(
                    f"Cannot sell {order.qty} shares of {order.symbol}: "
                    f"only {position.quantity} held"
                ),
            )

    # 1. Extreme VIX — reject new buys
    if vix_d > limits.vix_extreme_threshold and order.side == OrderSide.BUY:
        return RiskResult(
            action=RiskDecision.REJECT,
            risk_score=0.9,
            reasoning=f"VIX at {vix:.1f} — extreme volatility, no new longs",
            warnings=[f"VIX {vix:.1f} exceeds extreme threshold {limits.vix_extreme_threshold}"],
        )

    # 2. High VIX — reduce size
    vix_multiplier = Decimal("1.0")
    if vix_d > limits.vix_high_threshold:
        vix_multiplier = Decimal("0.5")
        warnings.append(f"VIX elevated at {vix:.1f} — size reduced 50%")

    # 3. Single order size limit
    effective_max = limits.max_single_order * vix_multiplier
    if order_pct > effective_max:
        max_qty = (portfolio_value * effective_max) / order.price
        return RiskResult(
            action=RiskDecision.ADJUST,
            risk_score=0.7,
            reasoning=(
                f"Order size {float(order_pct):.1%} exceeds limit {float(effective_max):.1%}"
            ),
            adjusted_size=max_qty.quantize(Decimal("0.01")),
            adjustments=[{"type": "reduce_size", "target_pct": float(effective_max)}],
            warnings=warnings,
        )

    # 4. Sector concentration
    sector_value = _sector_exposure(portfolio, order.sector)
    new_sector_pct = (sector_value + order_value) / portfolio_value
    if new_sector_pct > limits.max_sector_concentration:
        max_additional_value = limits.max_sector_concentration * portfolio_value - sector_value
        max_qty = max(Decimal("0"), max_additional_value / order.price)
        return RiskResult(
            action=RiskDecision.ADJUST,
            risk_score=0.7,
            reasoning=(
                f"Sector {order.sector} concentration {float(new_sector_pct):.1%} "
                f"exceeds limit {float(limits.max_sector_concentration):.1%}"
            ),
            adjusted_size=max_qty.quantize(Decimal("0.01")),
            adjustments=[
                {
                    "type": "reduce_sector",
                    "sector": order.sector,
                    "max_pct": float(limits.max_sector_concentration),
                }
            ],
            warnings=warnings,
        )

    # All checks passed
    risk_score = float(order_pct / limits.max_single_order)
    if warnings:
        return RiskResult(
            action=RiskDecision.ADJUST,
            risk_score=min(risk_score, 1.0),
            reasoning="Approved with VIX adjustment",
            adjusted_size=(order.qty * vix_multiplier).quantize(Decimal("0.01")),
            warnings=warnings,
        )

    return RiskResult(
        action=RiskDecision.APPROVE,
        risk_score=min(risk_score, 1.0),
        reasoning="All risk checks passed",
    )


def _sector_exposure(portfolio: Portfolio, sector: str) -> Decimal:
    """Calculate total exposure to a sector in the portfolio."""
    return sum(
        (p.current_value for p in portfolio.positions if p.sector == sector),
        Decimal("0"),
    )
