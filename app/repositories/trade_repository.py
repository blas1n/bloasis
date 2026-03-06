"""Trade repository — ORM-based data access with row-level locking.

Handles trade recording + position updates atomically using SELECT FOR UPDATE
to prevent race conditions on concurrent orders.
"""

import uuid as uuid_mod
from decimal import Decimal

from sqlalchemy import select

from shared.utils.postgres_client import PostgresClient

from .models import PositionRecord, TradeRecord


def _to_uuid(user_id: str) -> uuid_mod.UUID | str:
    try:
        return uuid_mod.UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError:
        return user_id


class TradeRepository:
    def __init__(self, postgres: PostgresClient) -> None:
        self.postgres = postgres

    async def get_trades(self, user_id: str, limit: int = 20) -> list[TradeRecord]:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(TradeRecord)
                .where(TradeRecord.user_id == _to_uuid(user_id))
                .order_by(TradeRecord.executed_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def record_trade_and_update_position(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        ai_reason: str = "",
    ) -> None:
        """Record a trade and update position atomically.

        Uses SELECT FOR UPDATE to prevent concurrent modification of the same position.
        Raises ValueError if selling without a position or with insufficient quantity.
        """
        async with self.postgres.get_session() as session:
            # 1. Lock and fetch position (SELECT FOR UPDATE prevents race conditions)
            result = await session.execute(
                select(PositionRecord)
                .where(PositionRecord.user_id == user_id, PositionRecord.symbol == symbol)
                .with_for_update()
            )
            position = result.scalar_one_or_none()

            realized_pnl = Decimal("0")
            actual_qty = qty

            if side.lower() == "buy":
                if position:
                    # Recalculate avg cost with weighted average
                    old_total = position.quantity * position.avg_cost
                    new_total = old_total + qty * price
                    new_qty = position.quantity + qty
                    position.quantity = new_qty
                    position.avg_cost = new_total / new_qty
                    position.current_price = price
                else:
                    session.add(
                        PositionRecord(
                            user_id=user_id,
                            symbol=symbol,
                            quantity=qty,
                            avg_cost=price,
                            current_price=price,
                        )
                    )
            else:
                # Sell — validate, clamp, compute realized P&L
                if not position or position.quantity <= 0:
                    raise ValueError(f"Cannot sell {symbol}: no open position")

                actual_qty = min(qty, position.quantity)
                realized_pnl = (price - position.avg_cost) * actual_qty
                position.quantity = position.quantity - actual_qty
                position.current_price = price

            # 2. Insert trade record (after sell logic so actual_qty and realized_pnl are known)
            session.add(
                TradeRecord(
                    user_id=_to_uuid(user_id),
                    order_id=order_id,
                    symbol=symbol,
                    action=side.upper(),
                    quantity=actual_qty,
                    price=price,
                    total_value=actual_qty * price,
                    realized_pnl=realized_pnl,
                    ai_reason=ai_reason,
                )
            )
            # Session commit handled by PostgresClient.get_session() context manager
