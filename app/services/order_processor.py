"""Background order processor — Outbox consumer + reconciliation.

Processes pending orders, polls unresolved orders, and reconciles
broker positions vs DB positions as a defense-in-depth mechanism.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from shared.utils.redis_client import RedisClient

from ..core.broker import BrokerAdapter
from ..core.models import OrderStatus
from ..repositories.order_repository import OrderRepository
from ..repositories.user_repository import UserRepository
from .brokers.factory import create_broker_adapter
from .portfolio import PortfolioService

logger = logging.getLogger(__name__)

# TTL for reconciliation diff records in Redis (7 days)
_RECONCILIATION_TTL = 86400 * 7


class OrderProcessor:
    """Processes the order outbox and reconciles broker state."""

    def __init__(
        self,
        order_repo: OrderRepository,
        user_repo: UserRepository,
        portfolio_svc: PortfolioService,
        redis: RedisClient,
    ) -> None:
        self.order_repo = order_repo
        self.user_repo = user_repo
        self.portfolio_svc = portfolio_svc
        self.redis = redis
        # Instance-level cache — persists across batches within same processor instance
        self._adapter_cache: dict[tuple[uuid.UUID, str], BrokerAdapter] = {}

    async def _get_broker(
        self,
        user_id: uuid.UUID,
        broker_type: str,
    ) -> BrokerAdapter:
        """Get or create a cached broker adapter for (user_id, broker_type)."""
        key = (user_id, broker_type)
        if key not in self._adapter_cache:
            self._adapter_cache[key] = await create_broker_adapter(
                user_id, self.user_repo, broker_type
            )
        return self._adapter_cache[key]

    async def process_pending_orders(self) -> int:
        """Outbox consumer: submit pending orders to broker.

        Returns number of orders processed.
        """
        orders = await self.order_repo.get_pending_orders()
        processed = 0

        for order in orders:
            if order.retry_count >= order.max_retries:
                await self.order_repo.update_status(
                    order.id, OrderStatus.FAILED, error_message="Max retries exceeded"
                )
                continue

            try:
                broker = await self._get_broker(order.user_id, order.broker_type)
                result = await broker.submit_order(
                    symbol=order.symbol,
                    side=order.side,
                    qty=order.qty,
                    price=order.price,
                    order_type=order.order_type,
                    client_order_id=order.client_order_id,
                )
                await self.order_repo.update_status(
                    order.id,
                    result.status,
                    broker_order_id=result.order_id,
                    filled_qty=result.filled_qty,
                    filled_avg_price=result.filled_avg_price,
                )

                # If immediately filled, record the trade
                if result.status == OrderStatus.FILLED:
                    fill_price = result.filled_avg_price or order.price
                    fill_qty = result.filled_qty or order.qty
                    await self.portfolio_svc.record_trade(
                        user_id=order.user_id,
                        order_id=result.order_id,
                        symbol=order.symbol,
                        side=order.side,
                        qty=fill_qty,
                        price=fill_price,
                        ai_reason=order.ai_reason or "",
                    )

                processed += 1
            except ValueError as e:
                # Unsupported broker_type or missing credentials — no point retrying
                logger.error(
                    "Cannot create broker adapter for order %s: %s",
                    order.client_order_id,
                    e,
                )
                await self.order_repo.update_status(
                    order.id, OrderStatus.FAILED, error_message=str(e)
                )
            except Exception as e:
                logger.error(
                    "Failed to process pending order %s",
                    order.client_order_id,
                    exc_info=True,
                )
                await self.order_repo.increment_retry(order.id, error_message=str(e))

        return processed

    async def poll_unresolved_orders(self) -> int:
        """Poll broker for status of submitted/partially_filled orders.

        Returns number of orders resolved.
        """
        orders = await self.order_repo.get_unresolved_orders()
        resolved = 0

        for order in orders:
            if not order.broker_order_id:
                continue

            try:
                broker = await self._get_broker(order.user_id, order.broker_type)
                result = await broker.get_order_status(order.broker_order_id)

                if result.status == OrderStatus.FILLED:
                    fill_price = result.filled_avg_price or order.price
                    fill_qty = result.filled_qty or order.qty
                    await self.portfolio_svc.record_trade(
                        user_id=order.user_id,
                        order_id=order.broker_order_id,
                        symbol=order.symbol,
                        side=order.side,
                        qty=fill_qty,
                        price=fill_price,
                        ai_reason=order.ai_reason or "",
                    )
                    await self.order_repo.update_status(
                        order.id,
                        OrderStatus.FILLED,
                        filled_qty=result.filled_qty,
                        filled_avg_price=result.filled_avg_price,
                    )
                    resolved += 1
                elif result.status == OrderStatus.CANCELLED:
                    await self.order_repo.update_status(order.id, result.status)
                    resolved += 1
                elif result.status == OrderStatus.PARTIALLY_FILLED:
                    await self.order_repo.update_status(
                        order.id,
                        OrderStatus.PARTIALLY_FILLED,
                        filled_qty=result.filled_qty,
                        filled_avg_price=result.filled_avg_price,
                    )
            except Exception:
                logger.error(
                    "Failed to poll order %s",
                    order.broker_order_id,
                    exc_info=True,
                )

        return resolved

    async def reconcile_with_broker(self) -> int:
        """Reconciliation: detect diffs between broker and DB positions.

        Returns number of diffs detected.
        """
        users = await self.user_repo.get_active_trading_users()
        total_diffs = 0

        for user_id in users:
            try:
                diffs = await self._reconcile_user(user_id)
                total_diffs += diffs
            except Exception:
                logger.error("Reconciliation failed for user %s", user_id, exc_info=True)

        return total_diffs

    async def _reconcile_user(self, user_id: uuid.UUID) -> int:
        """Reconcile a single user's positions with broker."""
        try:
            broker = await create_broker_adapter(user_id, self.user_repo)
        except ValueError:
            return 0

        broker_positions = await broker.get_positions()
        db_positions = await self.portfolio_svc.get_positions(user_id)

        broker_map = {p.symbol: p for p in broker_positions}
        db_map = {p.symbol: p for p in db_positions}

        diffs: list[dict[str, Any]] = []
        detected_at = datetime.now(UTC).isoformat()

        # Check for mismatches
        all_symbols = set(broker_map.keys()) | set(db_map.keys())
        for symbol in all_symbols:
            bp = broker_map.get(symbol)
            dp = db_map.get(symbol)

            if bp and not dp:
                logger.warning(
                    "Reconciliation: position at broker but not in DB",
                    extra={
                        "user_id": str(user_id),
                        "symbol": symbol,
                        "qty": str(bp.quantity),
                        "action_required": True,
                    },
                )
                diffs.append(
                    {
                        "type": "broker_only",
                        "symbol": symbol,
                        "broker_qty": str(bp.quantity),
                        "db_qty": None,
                        "detected_at": detected_at,
                    }
                )
            elif dp and not bp:
                if dp.quantity > 0:
                    logger.warning(
                        "Reconciliation: position in DB but not at broker",
                        extra={
                            "user_id": str(user_id),
                            "symbol": symbol,
                            "qty": str(dp.quantity),
                            "action_required": True,
                        },
                    )
                    diffs.append(
                        {
                            "type": "db_only",
                            "symbol": symbol,
                            "broker_qty": None,
                            "db_qty": str(dp.quantity),
                            "detected_at": detected_at,
                        }
                    )
            elif bp and dp and bp.quantity != dp.quantity:
                logger.warning(
                    "Reconciliation: quantity mismatch",
                    extra={
                        "user_id": str(user_id),
                        "symbol": symbol,
                        "broker_qty": str(bp.quantity),
                        "db_qty": str(dp.quantity),
                        "action_required": True,
                    },
                )
                diffs.append(
                    {
                        "type": "qty_mismatch",
                        "symbol": symbol,
                        "broker_qty": str(bp.quantity),
                        "db_qty": str(dp.quantity),
                        "detected_at": detected_at,
                    }
                )

        # Persist diffs to Redis for historical tracking (TTL: 7 days)
        if diffs:
            await self.redis.setex(
                f"reconciliation:diffs:{user_id}",
                _RECONCILIATION_TTL,
                json.dumps(diffs),
            )

        return len(diffs)
