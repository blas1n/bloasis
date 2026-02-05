"""Executor Service - Order execution management."""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import grpc
from shared.generated import executor_pb2, executor_pb2_grpc

from .models import OrderStatus, OrderType

if TYPE_CHECKING:
    from .alpaca_client import AlpacaClient
    from .utils.event_publisher import EventPublisher
    from .utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class ExecutorServicer(executor_pb2_grpc.ExecutorServiceServicer):
    """gRPC service for order execution.

    This service handles order execution through Alpaca paper trading.
    All orders must be approved by Risk Committee before execution.
    """

    def __init__(
        self,
        alpaca_client: "AlpacaClient",
        event_publisher: "EventPublisher",
        redis_client: "RedisClient",
    ) -> None:
        """Initialize Executor servicer.

        Args:
            alpaca_client: Client for Alpaca trading API
            event_publisher: Publisher for execution events
            redis_client: Redis client for order tracking
        """
        self.alpaca = alpaca_client
        self.publisher = event_publisher
        self.redis = redis_client

    async def ExecuteOrder(
        self,
        request: executor_pb2.ExecuteOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> executor_pb2.ExecuteOrderResponse:
        """Execute a single order.

        Prerequisites:
        - Order must be approved by Risk Committee

        Args:
            request: Order execution request
            context: gRPC context

        Returns:
            Execution result with order ID and status
        """
        logger.info(f"Executing order: {request.symbol} {request.side} {request.qty}")

        # Validate request
        if not request.user_id:
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message="user_id is required",
            )

        if not request.symbol:
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message="symbol is required",
            )

        if request.qty <= 0:
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message="qty must be positive",
            )

        # Verify risk approval
        if not await self._verify_risk_approval(request.risk_approval_id):
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message="Risk approval not found or expired",
            )

        # Generate client order ID
        client_order_id = f"bloasis-{uuid4().hex[:8]}"

        # Submit order based on type
        order_type = request.order_type.lower() if request.order_type else "market"

        try:
            if order_type == OrderType.MARKET.value:
                result = await self.alpaca.submit_market_order(
                    symbol=request.symbol,
                    qty=Decimal(str(request.qty)),
                    side=request.side,
                    client_order_id=client_order_id,
                )
            elif order_type == OrderType.LIMIT.value:
                if request.limit_price <= 0:
                    return executor_pb2.ExecuteOrderResponse(
                        success=False,
                        error_message="limit_price required for limit orders",
                    )
                result = await self.alpaca.submit_limit_order(
                    symbol=request.symbol,
                    qty=Decimal(str(request.qty)),
                    side=request.side,
                    limit_price=Decimal(str(request.limit_price)),
                    client_order_id=client_order_id,
                )
            elif order_type == OrderType.BRACKET.value:
                if request.stop_loss <= 0 or request.take_profit <= 0:
                    return executor_pb2.ExecuteOrderResponse(
                        success=False,
                        error_message="stop_loss and take_profit required for bracket orders",
                    )
                result = await self.alpaca.submit_bracket_order(
                    symbol=request.symbol,
                    qty=Decimal(str(request.qty)),
                    side=request.side,
                    stop_loss=Decimal(str(request.stop_loss)),
                    take_profit=Decimal(str(request.take_profit)),
                    client_order_id=client_order_id,
                )
            else:
                return executor_pb2.ExecuteOrderResponse(
                    success=False,
                    error_message=f"Unknown order type: {request.order_type}",
                )
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message=str(e),
            )

        # Store order mapping for tracking
        if result.order_id:
            await self._store_order_mapping(request.user_id, result)

        # Publish execution event
        await self._publish_execution_event(request.user_id, result)

        success = result.status != OrderStatus.REJECTED

        logger.info(
            f"Order execution result: {request.symbol} {request.side} - "
            f"status={result.status.value}, order_id={result.order_id}"
        )

        return executor_pb2.ExecuteOrderResponse(
            success=success,
            order_id=result.order_id,
            client_order_id=result.client_order_id,
            status=result.status.value,
            error_message=result.error_message or "",
        )

    async def GetOrderStatus(
        self,
        request: executor_pb2.GetOrderStatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> executor_pb2.GetOrderStatusResponse:
        """Get status of an order.

        Args:
            request: Order status request
            context: gRPC context

        Returns:
            Current order status and fill details
        """
        logger.info(f"Getting order status: {request.order_id}")

        if not request.order_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "order_id is required")

        try:
            result = await self.alpaca.get_order_status(request.order_id)

            return executor_pb2.GetOrderStatusResponse(
                order_id=result.order_id,
                status=result.status.value,
                filled_qty=float(result.filled_qty),
                filled_avg_price=float(result.filled_avg_price or 0),
                submitted_at=result.submitted_at,
                filled_at=result.filled_at or "",
            )
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Order not found: {e}")

    async def CancelOrder(
        self,
        request: executor_pb2.CancelOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> executor_pb2.CancelOrderResponse:
        """Cancel an open order.

        Args:
            request: Cancel order request
            context: gRPC context

        Returns:
            Cancellation result
        """
        logger.info(f"Cancelling order: {request.order_id}")

        if not request.order_id:
            return executor_pb2.CancelOrderResponse(
                success=False,
                message="order_id is required",
            )

        success = await self.alpaca.cancel_order(request.order_id)

        if success:
            await self.publisher.publish_order_cancelled(
                user_id=request.user_id,
                order_id=request.order_id,
            )
            return executor_pb2.CancelOrderResponse(
                success=True,
                message="Order cancelled successfully",
            )

        return executor_pb2.CancelOrderResponse(
            success=False,
            message="Failed to cancel order",
        )

    async def GetAccount(
        self,
        request: executor_pb2.GetAccountRequest,
        context: grpc.aio.ServicerContext,
    ) -> executor_pb2.GetAccountResponse:
        """Get account information.

        Args:
            request: Account request
            context: gRPC context

        Returns:
            Account balance information
        """
        logger.info(f"Getting account info for user: {request.user_id}")

        try:
            account = await self.alpaca.get_account()

            return executor_pb2.GetAccountResponse(
                cash=float(account.cash),
                buying_power=float(account.buying_power),
                portfolio_value=float(account.portfolio_value),
                equity=float(account.equity),
            )
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to get account: {e}")

    async def _verify_risk_approval(self, approval_id: str) -> bool:
        """Verify risk approval exists and is valid.

        Args:
            approval_id: Risk approval ID from Risk Committee

        Returns:
            True if approval is valid, False otherwise
        """
        if not approval_id:
            logger.warning("No risk approval ID provided")
            return False

        key = f"risk:approval:{approval_id}"
        try:
            exists = await self.redis.exists(key)
            if not exists:
                logger.warning(f"Risk approval not found: {approval_id}")
            return exists
        except Exception as e:
            logger.error(f"Failed to verify risk approval: {e}")
            return False

    async def _store_order_mapping(self, user_id: str, result) -> None:
        """Store order mapping for tracking.

        Args:
            user_id: User who placed the order
            result: Order result from Alpaca
        """
        key = f"order:{result.order_id}"
        try:
            await self.redis.hset(
                key,
                {
                    "user_id": user_id,
                    "symbol": result.symbol,
                    "side": result.side,
                    "qty": str(result.qty),
                    "status": result.status.value,
                    "client_order_id": result.client_order_id,
                },
            )
            # Set expiry to 7 days
            await self.redis.expire(key, 86400 * 7)
            logger.debug(f"Stored order mapping: {key}")
        except Exception as e:
            logger.warning(f"Failed to store order mapping: {e}")

    async def _publish_execution_event(self, user_id: str, result) -> None:
        """Publish order execution event.

        Args:
            user_id: User who placed the order
            result: Order result from Alpaca
        """
        try:
            await self.publisher.publish_order_executed(
                user_id=user_id,
                order_id=result.order_id,
                symbol=result.symbol,
                side=result.side,
                qty=float(result.qty),
                status=result.status.value,
                filled_qty=float(result.filled_qty),
                filled_price=float(result.filled_avg_price or 0),
            )
        except Exception as e:
            logger.warning(f"Failed to publish execution event: {e}")
