"""Trade repository for P&L tracking."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from shared.utils import PostgresClient
from sqlalchemy import select

from ..models import Trade, TradeRecord

logger = logging.getLogger(__name__)


class TradeRepository:
    """Repository for trade data persistence."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        """Initialize repository with PostgreSQL client.

        Args:
            postgres_client: PostgreSQL client for database operations.
        """
        self.postgres = postgres_client

    async def save_trade(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        realized_pnl: Decimal = Decimal("0"),
        executed_at: Optional[datetime] = None,
        ai_reason: Optional[str] = None,
    ) -> Trade:
        """Save a new trade record.

        Args:
            user_id: User identifier (UUID string).
            order_id: Alpaca order ID.
            symbol: Stock ticker symbol.
            side: Trade side ("buy" or "sell").
            qty: Quantity traded.
            price: Execution price.
            commission: Commission paid.
            realized_pnl: Realized P&L for sell trades.
            executed_at: Execution timestamp (defaults to now).
            ai_reason: AI-generated reasoning for this trade (optional, max 500 chars).

        Returns:
            Trade domain object.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        if executed_at is None:
            executed_at = datetime.utcnow()

        # Convert side to action (BUY/SELL)
        action = side.upper()
        quantity = int(qty)
        total_value = price * qty

        record = TradeRecord(
            user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
            order_id=order_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            total_value=total_value,
            commission=commission,
            realized_pnl=realized_pnl,
            executed_at=executed_at,
            ai_reason=ai_reason,
        )

        async with self.postgres.get_session() as session:
            session.add(record)
            await session.flush()
            await session.refresh(record)
            trade = Trade.from_record(record)

        logger.info(f"Saved trade: {order_id} {symbol} {action} {quantity}@{price}")
        return trade

    async def get_trade_by_order_id(self, order_id: str) -> Optional[Trade]:
        """Get a trade by order ID.

        Args:
            order_id: Alpaca order ID.

        Returns:
            Trade if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(TradeRecord).where(TradeRecord.order_id == order_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

        if record is None:
            return None

        return Trade.from_record(record)

    async def get_trades(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Trade]:
        """Get trade history for a user.

        Args:
            user_id: User identifier (UUID string).
            symbol: Optional symbol filter.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            limit: Maximum number of trades to return.

        Returns:
            List of Trade domain objects.
        """
        if not self.postgres:
            return []

        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        stmt = select(TradeRecord).where(TradeRecord.user_id == user_uuid)

        if symbol:
            stmt = stmt.where(TradeRecord.symbol == symbol)

        if start_date:
            stmt = stmt.where(TradeRecord.executed_at >= start_date)

        if end_date:
            stmt = stmt.where(TradeRecord.executed_at <= end_date)

        stmt = stmt.order_by(TradeRecord.executed_at.desc()).limit(limit)

        async with self.postgres.get_session() as session:
            result = await session.execute(stmt)
            records = result.scalars().all()

        return [Trade.from_record(record) for record in records]

    async def get_realized_pnl(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Decimal:
        """Calculate total realized P&L for a user.

        Args:
            user_id: User identifier.
            symbol: Optional symbol filter.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Total realized P&L.
        """
        trades = await self.get_trades(
            user_id=user_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=10000,  # Get all trades for calculation
        )

        total_realized_pnl = sum(
            (t.realized_pnl for t in trades),
            Decimal("0"),
        )

        return total_realized_pnl

    async def get_trades_for_symbol(self, user_id: str, symbol: str) -> list[Trade]:
        """Get all trades for a specific symbol.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol.

        Returns:
            List of trades for the symbol.
        """
        return await self.get_trades(user_id=user_id, symbol=symbol, limit=10000)
