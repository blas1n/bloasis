"""P&L calculation for portfolio positions."""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .clients.market_data_client import MarketDataClient

logger = logging.getLogger(__name__)


@dataclass
class PositionPnL:
    """P&L for a single position."""

    symbol: str
    qty: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    daily_pnl: Decimal
    daily_pnl_pct: Decimal


@dataclass
class PortfolioPnL:
    """Aggregate P&L for portfolio."""

    total_market_value: Decimal
    total_cost_basis: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_pct: Decimal
    total_realized_pnl: Decimal
    total_daily_pnl: Decimal
    total_daily_pnl_pct: Decimal
    positions: list[PositionPnL]


class PnLCalculator:
    """Calculates P&L for portfolio positions."""

    def __init__(self, market_data_client: Optional["MarketDataClient"] = None) -> None:
        """Initialize P&L calculator.

        Args:
            market_data_client: Optional client for fetching current prices.
                                If not provided, uses position's stored current_price.
        """
        self.market_data = market_data_client

    async def calculate_position_pnl(
        self,
        symbol: str,
        qty: Decimal,
        avg_cost: Decimal,
        current_price: Optional[Decimal] = None,
        previous_close: Optional[Decimal] = None,
    ) -> PositionPnL:
        """Calculate P&L for a single position.

        Args:
            symbol: Stock ticker symbol
            qty: Position quantity
            avg_cost: Average cost per share
            current_price: Current price (fetched if not provided)
            previous_close: Previous day's close (for daily P&L)

        Returns:
            PositionPnL with calculated values
        """
        # Get current price if not provided
        if current_price is None:
            current_price = await self._get_current_price(symbol)

        # Get previous close if not provided (for daily P&L)
        if previous_close is None and self.market_data:
            previous_close = await self._get_previous_close(symbol)

        # Calculate values
        market_value = qty * current_price
        cost_basis = qty * avg_cost
        unrealized_pnl = market_value - cost_basis

        # Avoid division by zero
        if cost_basis > 0:
            unrealized_pnl_pct = (unrealized_pnl / cost_basis) * Decimal("100")
        else:
            unrealized_pnl_pct = Decimal("0")

        # Daily P&L
        if previous_close and previous_close > 0:
            daily_change = current_price - previous_close
            daily_pnl = qty * daily_change
            daily_pnl_pct = (daily_change / previous_close) * Decimal("100")
        else:
            daily_pnl = Decimal("0")
            daily_pnl_pct = Decimal("0")

        return PositionPnL(
            symbol=symbol,
            qty=qty,
            avg_cost=avg_cost,
            current_price=current_price,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
        )

    async def calculate_portfolio_pnl(
        self,
        positions: list[dict],
        realized_pnl: Decimal = Decimal("0"),
    ) -> PortfolioPnL:
        """Calculate aggregate P&L for portfolio.

        Args:
            positions: List of position dicts with symbol, qty, avg_cost, current_price
            realized_pnl: Total realized P&L from closed trades

        Returns:
            PortfolioPnL with aggregated values
        """
        position_pnls: list[PositionPnL] = []
        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")
        total_daily_pnl = Decimal("0")

        for pos in positions:
            # Handle both dict and object-like positions
            if isinstance(pos, dict):
                symbol: str = pos.get("symbol", "")
                qty = Decimal(str(pos.get("qty", 0)))
                avg_cost = Decimal(str(pos.get("avg_cost", 0)))
                current_price = pos.get("current_price")
            else:
                symbol = pos.symbol
                qty = Decimal(str(pos.quantity))
                avg_cost = pos.avg_cost
                current_price = None

            if current_price is not None:
                current_price = Decimal(str(current_price))

            pnl = await self.calculate_position_pnl(
                symbol=symbol,
                qty=qty,
                avg_cost=avg_cost,
                current_price=current_price,
            )
            position_pnls.append(pnl)
            total_market_value += pnl.market_value
            total_cost_basis += pnl.cost_basis
            total_daily_pnl += pnl.daily_pnl

        total_unrealized_pnl = total_market_value - total_cost_basis

        if total_cost_basis > 0:
            total_unrealized_pnl_pct = (total_unrealized_pnl / total_cost_basis) * Decimal("100")
        else:
            total_unrealized_pnl_pct = Decimal("0")

        if total_market_value > 0:
            total_daily_pnl_pct = (total_daily_pnl / total_market_value) * Decimal("100")
        else:
            total_daily_pnl_pct = Decimal("0")

        return PortfolioPnL(
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_pct=total_unrealized_pnl_pct,
            total_realized_pnl=realized_pnl,
            total_daily_pnl=total_daily_pnl,
            total_daily_pnl_pct=total_daily_pnl_pct,
            positions=position_pnls,
        )

    def calculate_trade_pnl(
        self,
        side: str,
        qty: Decimal,
        price: Decimal,
        avg_cost: Decimal,
        commission: Decimal = Decimal("0"),
    ) -> Decimal:
        """Calculate realized P&L for a trade.

        Args:
            side: Trade side ("buy" or "sell")
            qty: Trade quantity
            price: Execution price
            avg_cost: Average cost basis of position
            commission: Commission paid

        Returns:
            Realized P&L (only for sell trades, 0 for buy)
        """
        if side.lower() == "sell":
            # Realized P&L = (sell_price - avg_cost) * qty - commission
            gross_pnl = (price - avg_cost) * qty
            return gross_pnl - commission
        else:
            # Buy trades don't realize P&L, but we deduct commission
            return -commission

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price for symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price or Decimal("0") if unavailable
        """
        if self.market_data is None:
            logger.warning(f"No market data client, returning 0 for {symbol}")
            return Decimal("0")

        try:
            return await self.market_data.get_current_price(symbol)
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")
            return Decimal("0")

    async def _get_previous_close(self, symbol: str) -> Optional[Decimal]:
        """Get previous day's close for symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Previous close or None if unavailable
        """
        if self.market_data is None:
            return None

        try:
            return await self.market_data.get_previous_close(symbol)
        except Exception:
            return None
