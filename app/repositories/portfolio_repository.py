"""Portfolio repository — ORM-based data access for trading schema."""

import uuid as uuid_mod
from decimal import Decimal

from sqlalchemy import delete, select

from shared.utils.postgres_client import PostgresClient

from .models import PortfolioRecord, PositionRecord


class PortfolioRepository:
    def __init__(self, postgres: PostgresClient) -> None:
        self.postgres = postgres

    async def get_positions(self, user_id: uuid_mod.UUID) -> list[PositionRecord]:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(PositionRecord).where(
                    PositionRecord.user_id == user_id,
                    PositionRecord.quantity > 0,
                )
            )
            return list(result.scalars().all())

    async def get_cash_balance(self, user_id: uuid_mod.UUID) -> Decimal:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(PortfolioRecord).where(PortfolioRecord.user_id == user_id)
            )
            record = result.scalar_one_or_none()
            return record.cash_balance if record else Decimal("0")

    async def get_position_by_symbol(
        self, user_id: uuid_mod.UUID, symbol: str
    ) -> PositionRecord | None:
        """Get a single position by user and symbol."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(PositionRecord).where(
                    PositionRecord.user_id == user_id,
                    PositionRecord.symbol == symbol,
                    PositionRecord.quantity > 0,
                )
            )
            return result.scalar_one_or_none()

    async def upsert_position(
        self,
        user_id: uuid_mod.UUID,
        symbol: str,
        quantity: Decimal,
        avg_cost: Decimal,
        current_price: Decimal,
    ) -> None:
        """Create or update a position."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(PositionRecord).where(
                    PositionRecord.user_id == user_id,
                    PositionRecord.symbol == symbol,
                )
            )
            record = result.scalar_one_or_none()

            if record:
                record.quantity = quantity
                record.avg_cost = avg_cost
                record.current_price = current_price
            else:
                session.add(
                    PositionRecord(
                        user_id=user_id,
                        symbol=symbol,
                        quantity=quantity,
                        avg_cost=avg_cost,
                        current_price=current_price,
                        currency="USD",
                    )
                )

    async def delete_position(self, user_id: uuid_mod.UUID, symbol: str) -> None:
        """Delete a position by user and symbol."""
        async with self.postgres.get_session() as session:
            await session.execute(
                delete(PositionRecord).where(
                    PositionRecord.user_id == user_id,
                    PositionRecord.symbol == symbol,
                    PositionRecord.quantity > 0,
                )
            )

    async def update_cash_balance(self, user_id: uuid_mod.UUID, amount: Decimal) -> None:
        """Set cash balance for a user (creates portfolio record if needed)."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(PortfolioRecord).where(PortfolioRecord.user_id == user_id)
            )
            record = result.scalar_one_or_none()

            if record:
                record.cash_balance = amount
            else:
                session.add(PortfolioRecord(user_id=user_id, cash_balance=amount))
