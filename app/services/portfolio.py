"""Portfolio Service — Positions, P&L, trade history.

Replaces: services/portfolio/ (1129 lines gRPC + Redpanda → ~100 lines direct)
No event consumption — executor calls record_trade() directly.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from shared.utils.redis_client import RedisClient

if TYPE_CHECKING:
    from ..core.broker import BrokerAdapter
    from .market_data import MarketDataService

from ..config import settings
from ..core.models import OrderSide, Portfolio, Position, Trade
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.trade_repository import TradeRepository

logger = logging.getLogger(__name__)


class PortfolioService:
    """Portfolio management with PostgreSQL persistence and Redis cache."""

    def __init__(
        self,
        redis: RedisClient,
        portfolio_repo: PortfolioRepository,
        trade_repo: TradeRepository,
        market_data_svc: MarketDataService | None = None,
    ) -> None:
        self.redis = redis
        self.portfolio_repo = portfolio_repo
        self.trade_repo = trade_repo
        self.market_data_svc = market_data_svc

    async def get_portfolio(self, user_id: uuid.UUID) -> Portfolio:
        """Get portfolio summary for a user."""
        cache_key = f"user:{user_id}:portfolio"
        cached = await self.redis.get(cache_key)
        if cached and isinstance(cached, dict):
            return Portfolio(**cached)

        positions = await self.get_positions(user_id)
        cash = await self.portfolio_repo.get_cash_balance(user_id)

        invested = sum((p.current_value for p in positions), Decimal("0"))
        total_value = cash + invested
        cost_basis = sum((p.avg_cost * p.quantity for p in positions), Decimal("0"))
        pnl = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        pnl_pct = float((pnl / cost_basis) * 100) if cost_basis > 0 else 0.0
        daily_pnl = sum((p.daily_pnl for p in positions), Decimal("0"))
        daily_pnl_pct = float(daily_pnl / total_value * 100) if total_value > 0 else 0.0

        portfolio = Portfolio(
            user_id=str(user_id),
            total_value=total_value,
            cash_balance=cash,
            invested_value=invested,
            total_return=pnl_pct,
            total_return_amount=pnl,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            positions=positions,
            timestamp=datetime.now(UTC).isoformat(),
        )

        await self.redis.setex(cache_key, settings.cache_user_portfolio_ttl, portfolio.model_dump())
        return portfolio

    async def get_positions(self, user_id: uuid.UUID) -> list[Position]:
        """Get all positions for a user."""
        rows = await self.portfolio_repo.get_positions(user_id)

        positions = []
        for row in rows:
            qty = row.quantity
            avg_cost = row.avg_cost
            current_price = row.current_price
            current_value = current_price * qty
            pnl = (current_price - avg_cost) * qty
            pnl_pct = float((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0.0

            # Daily P&L: (current_price - previous_close) * quantity
            daily_pnl = Decimal("0")
            daily_pnl_pct = 0.0
            if self.market_data_svc:
                try:
                    prev_close = await self.market_data_svc.get_previous_close(row.symbol)
                    if prev_close > 0:
                        daily_pnl = (current_price - prev_close) * qty
                        daily_pnl_pct = float((current_price - prev_close) / prev_close * 100)
                except (TimeoutError, ValueError) as e:
                    logger.warning(
                        "Failed to calculate daily P&L",
                        extra={"symbol": row.symbol, "error": str(e)},
                    )

            positions.append(
                Position(
                    symbol=row.symbol,
                    quantity=qty,
                    avg_cost=avg_cost,
                    current_price=current_price,
                    current_value=current_value,
                    unrealized_pnl=pnl,
                    unrealized_pnl_percent=pnl_pct,
                    daily_pnl=daily_pnl,
                    daily_pnl_pct=daily_pnl_pct,
                    currency=row.currency,
                )
            )

        return positions

    async def get_trades(self, user_id: uuid.UUID, limit: int = 20) -> list[Trade]:
        """Get trade history for a user."""
        rows = await self.trade_repo.get_trades(user_id, limit)

        return [
            Trade(
                order_id=row.order_id,
                symbol=row.symbol,
                side=OrderSide(row.action.lower()),
                qty=Decimal(row.quantity),
                price=row.price,
                commission=row.commission or Decimal("0"),
                realized_pnl=row.realized_pnl or Decimal("0"),
                executed_at=row.executed_at.isoformat() if row.executed_at else "",
                ai_reason=row.ai_reason,
            )
            for row in rows
        ]

    async def record_trade(
        self,
        user_id: uuid.UUID,
        order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        ai_reason: str = "",
    ) -> None:
        """Record a completed trade and update positions atomically.

        Uses SELECT FOR UPDATE to prevent concurrent modification race conditions.
        Called directly by ExecutorService (replaces Redpanda order-filled event).
        """
        await self.trade_repo.record_trade_and_update_position(
            user_id=user_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            ai_reason=ai_reason,
        )
        await self.redis.delete(f"user:{user_id}:portfolio")

    async def sync_with_broker(self, user_id: uuid.UUID, broker: BrokerAdapter) -> dict[str, Any]:
        """Sync positions from broker via adapter.

        BLOASIS DB is the source of truth. Broker sync updates DB to match
        current broker state (account balance + positions).

        Steps:
        1. Fetch account → update cash balance
        2. Fetch positions → create/update DB positions
        3. Delete stale positions (in DB but not at broker)
        4. Invalidate cache
        """
        try:
            account = await broker.get_account()
            await self.portfolio_repo.update_cash_balance(user_id, account.cash)
        except Exception as e:
            logger.error("Broker API error during sync", extra={"error": str(e)})
            return {"success": False, "errorMessage": "Broker API connection failed"}

        try:
            broker_positions = await broker.get_positions()
        except Exception as e:
            logger.error("Failed to fetch broker positions", extra={"error": str(e)})
            return {"success": False, "errorMessage": "Failed to fetch broker positions"}

        # Reconcile positions
        broker_symbols: set[str] = set()
        for pos in broker_positions:
            broker_symbols.add(pos.symbol)
            await self.portfolio_repo.upsert_position(
                user_id=user_id,
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_cost=pos.avg_entry_price,
                current_price=pos.current_price,
            )

        # Delete stale positions (in DB but not at broker)
        db_positions = await self.portfolio_repo.get_positions(user_id)
        for db_pos in db_positions:
            if db_pos.symbol not in broker_symbols:
                await self.portfolio_repo.delete_position(user_id, db_pos.symbol)

        # Invalidate cache
        await self.redis.delete(f"user:{user_id}:portfolio")

        return {"success": True, "positionsSynced": len(broker_symbols)}
