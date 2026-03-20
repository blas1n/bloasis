"""Executor Service — Order execution with Saga pattern.

Saga flow:
  Step 1: Risk check (fresh portfolio data)
  Step 2: Create pending order in outbox (DB)
  Step 3: Submit to broker via adapter (with idempotency key)
  Step 4: Record trade + update order status

Compensation:
  Step 3 failure → mark order as "failed"
  Step 4 failure → cancel broker order → mark "compensation_needed"
"""

import logging
import uuid
from decimal import Decimal
from typing import Any

from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.broker import BrokerAdapter
from ..core.models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    RiskDecision,
    RiskLimits,
)
from ..core.risk_rules import evaluate_risk
from ..repositories.order_repository import OrderRepository
from ..repositories.user_repository import UserRepository
from .market_data import MarketDataService
from .portfolio import PortfolioService

logger = logging.getLogger(__name__)


class ExecutorService:
    """Order execution with integrated risk checks and Saga pattern."""

    def __init__(
        self,
        redis: RedisClient,
        portfolio_svc: PortfolioService,
        market_data_svc: MarketDataService,
        broker: BrokerAdapter,
        order_repo: OrderRepository,
        user_repo: UserRepository | None = None,
    ) -> None:
        self.redis = redis
        self.portfolio_svc = portfolio_svc
        self.market_data_svc = market_data_svc
        self.broker = broker
        self.order_repo = order_repo
        self.user_repo = user_repo

    async def execute_order(
        self,
        user_id: uuid.UUID,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal | None = None,
        order_type: str = "market",
        sector: str = "Unknown",
        ai_reason: str = "",
    ) -> OrderResult:
        """Execute an order with risk checks and Saga pattern protection."""
        # Get current price if not provided
        if price is None or price == 0:
            bars = await self.market_data_svc.get_ohlcv(symbol, period="1d", interval="1d")
            if bars:
                price = Decimal(str(bars[-1]["close"]))
            else:
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    side=OrderSide(side),
                    qty=qty,
                    status=OrderStatus.FAILED,
                    error_message="Cannot determine price",
                )

        # Step 1: Risk check (fresh portfolio — no cache)
        portfolio = await self.portfolio_svc.get_portfolio(user_id)
        vix = await self.market_data_svc.get_vix()

        order = OrderRequest(
            user_id=str(user_id),
            symbol=symbol,
            side=OrderSide(side),
            qty=qty,
            price=price,
            sector=sector,
        )

        limits = RiskLimits(
            max_position_size=settings.max_position_size,
            max_single_order=settings.max_single_order,
            max_sector_concentration=settings.max_sector_concentration,
            vix_high_threshold=settings.vix_high_threshold,
            vix_extreme_threshold=settings.vix_extreme_threshold,
        )

        risk_result = evaluate_risk(order, portfolio, vix, limits)

        if risk_result.action == RiskDecision.REJECT:
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=OrderSide(side),
                qty=qty,
                status=OrderStatus.FAILED,
                error_message=risk_result.reasoning,
            )

        # Adjust size if needed
        effective_qty = qty
        if risk_result.adjusted_size is not None:
            effective_qty = risk_result.adjusted_size

        # Guard: reject before touching DB if qty is zero after risk adjustment
        if effective_qty <= 0:
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=OrderSide(side),
                qty=qty,
                status=OrderStatus.FAILED,
                error_message="Order rejected: effective qty is zero after risk adjustment",
            )

        # Step 2: Outbox — create pending order in DB (survives crashes)
        client_order_id = str(uuid.uuid4())
        order_record = await self.order_repo.create_pending_order(
            user_id=user_id,
            client_order_id=client_order_id,
            broker_type=self.broker.broker_type,
            symbol=symbol,
            side=side,
            qty=effective_qty,
            price=price,
            order_type=order_type,
            ai_reason=ai_reason,
            risk_limits_snapshot=limits.model_dump(mode="json"),
        )

        # Step 3: Submit to broker (with idempotency key)
        try:
            result = await self.broker.submit_order(
                symbol=symbol,
                side=side,
                qty=effective_qty,
                price=price,
                order_type=order_type,
                client_order_id=client_order_id,
            )
            await self.order_repo.update_status(
                order_record.id,
                result.status,
                broker_order_id=result.order_id,
                filled_qty=result.filled_qty,
                filled_avg_price=result.filled_avg_price,
            )
        except Exception:
            # Saga compensation: mark order as failed
            await self.order_repo.update_status(
                order_record.id, OrderStatus.FAILED, error_message="Broker submission failed"
            )
            logger.error("Broker submission failed for order %s", client_order_id, exc_info=True)
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=OrderSide(side),
                qty=effective_qty,
                status=OrderStatus.FAILED,
                error_message="Broker submission failed",
            )

        # Handle rejected orders (broker returned rejection without exception)
        if result.status == OrderStatus.FAILED:
            await self.order_repo.update_status(
                order_record.id,
                OrderStatus.FAILED,
                error_message=result.error_message or "Broker rejected order",
            )
            return result

        # Step 4: Record trade if filled
        if result.status == OrderStatus.FILLED:
            fill_price = result.filled_avg_price or price
            try:
                await self.portfolio_svc.record_trade(
                    user_id=user_id,
                    order_id=result.order_id,
                    symbol=symbol,
                    side=side,
                    qty=result.filled_qty or effective_qty,
                    price=fill_price,
                    ai_reason=ai_reason,
                )
                await self.order_repo.update_status(order_record.id, OrderStatus.FILLED)
            except Exception:
                # Saga compensation: cancel broker order + mark compensation_needed
                logger.error(
                    "Trade recording failed, attempting broker cancellation",
                    exc_info=True,
                )
                cancelled = await self.broker.cancel_order(result.order_id)
                comp_status = (
                    OrderStatus.COMPENSATION_NEEDED if not cancelled else OrderStatus.CANCELLED
                )
                await self.order_repo.update_status(
                    order_record.id,
                    comp_status,
                    error_message="Trade recording failed after broker fill",
                )
                return OrderResult(
                    order_id=result.order_id,
                    symbol=symbol,
                    side=OrderSide(side),
                    qty=effective_qty,
                    status=OrderStatus.COMPENSATION_NEEDED,
                    error_message="Trade recording failed — compensation initiated",
                )

        return result

    async def get_trading_status(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get automated trading status for a user."""
        status = await self.redis.get(f"trading:{user_id}:status")
        if status is not None:
            return {
                "tradingEnabled": status == "active",
                "status": status,
                "lastChanged": "",
            }

        if self.user_repo:
            enabled = await self.user_repo.get_trading_enabled(user_id)
            db_status = "active" if enabled else "inactive"
            await self.redis.setex(f"trading:{user_id}:status", 86400, db_status)
            return {
                "tradingEnabled": enabled,
                "status": db_status,
                "lastChanged": "",
            }

        return {"tradingEnabled": False, "status": "inactive", "lastChanged": ""}

    async def start_trading(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Start automated trading for a user."""
        await self.redis.setex(f"trading:{user_id}:status", 86400, "active")
        if self.user_repo:
            await self.user_repo.update_trading_enabled(user_id, True)
        return {"tradingEnabled": True, "status": "active"}

    async def stop_trading(self, user_id: uuid.UUID, mode: str = "soft") -> dict[str, Any]:
        """Stop automated trading for a user."""
        status = f"{mode}_stopped"
        await self.redis.setex(f"trading:{user_id}:status", 86400, status)
        if self.user_repo:
            await self.user_repo.update_trading_enabled(user_id, False)
        return {"tradingEnabled": False, "status": status}
