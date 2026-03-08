"""Order repository — ORM-based data access for the order outbox (Saga pattern).

Manages order lifecycle: pending → submitted → filled/failed/compensation_needed.
"""

import uuid as uuid_mod
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update

from shared.utils.postgres_client import PostgresClient

from ..core.models import OrderStatus
from .models import OrderRecord


class OrderRepository:
    def __init__(self, postgres: PostgresClient) -> None:
        self.postgres = postgres

    async def create_pending_order(
        self,
        user_id: uuid_mod.UUID,
        client_order_id: str,
        broker_type: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_type: str = "market",
        ai_reason: str = "",
        risk_limits_snapshot: dict[str, Any] | None = None,
    ) -> OrderRecord:
        """Create a pending order in the outbox (Step 2 of Saga)."""
        async with self.postgres.get_session() as session:
            record = OrderRecord(
                user_id=user_id,
                client_order_id=client_order_id,
                broker_type=broker_type,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=order_type,
                status=OrderStatus.PENDING,
                ai_reason=ai_reason,
                risk_limits_snapshot=risk_limits_snapshot,
            )
            session.add(record)
            await session.flush()
            return record

    async def update_status(
        self,
        order_id: uuid_mod.UUID,
        status: str,
        broker_order_id: str | None = None,
        filled_qty: Decimal | None = None,
        filled_avg_price: Decimal | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update order status and optional fill details."""
        async with self.postgres.get_session() as session:
            values: dict[str, Any] = {"status": status}
            if broker_order_id is not None:
                values["broker_order_id"] = broker_order_id
            if filled_qty is not None:
                values["filled_qty"] = filled_qty
            if filled_avg_price is not None:
                values["filled_avg_price"] = filled_avg_price
            if error_message is not None:
                values["error_message"] = error_message

            now = datetime.now(UTC)
            if status == OrderStatus.SUBMITTED:
                values["submitted_at"] = now
            elif status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                values["filled_at"] = now

            await session.execute(
                update(OrderRecord).where(OrderRecord.id == order_id).values(**values)
            )

    async def increment_retry(
        self, order_id: uuid_mod.UUID, error_message: str | None = None
    ) -> None:
        """Increment retry count for a failed order submission."""
        async with self.postgres.get_session() as session:
            values: dict[str, Any] = {"retry_count": OrderRecord.retry_count + 1}
            if error_message is not None:
                values["error_message"] = error_message
            await session.execute(
                update(OrderRecord).where(OrderRecord.id == order_id).values(**values)
            )

    async def get_by_client_order_id(self, client_order_id: str) -> OrderRecord | None:
        """Find order by idempotency key (duplicate prevention)."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(OrderRecord).where(OrderRecord.client_order_id == client_order_id)
            )
            return result.scalar_one_or_none()

    async def get_pending_orders(self, limit: int = 50) -> list[OrderRecord]:
        """Get pending orders for the outbox consumer to process."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(OrderRecord)
                .where(OrderRecord.status == OrderStatus.PENDING)
                .where(OrderRecord.retry_count < OrderRecord.max_retries)
                .order_by(OrderRecord.created_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_unresolved_orders(self, limit: int = 100) -> list[OrderRecord]:
        """Get submitted/partially_filled orders for status polling."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(OrderRecord)
                .where(
                    OrderRecord.status.in_([OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED])
                )
                .order_by(OrderRecord.created_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_orders_by_user(
        self, user_id: uuid_mod.UUID, limit: int = 20
    ) -> list[OrderRecord]:
        """Get order history for a user."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(OrderRecord)
                .where(OrderRecord.user_id == user_id)
                .order_by(OrderRecord.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
