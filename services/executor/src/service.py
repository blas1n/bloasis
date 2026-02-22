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
    from .clients.user_client import UserClient
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
        alpaca_client: "AlpacaClient | None",
        event_publisher: "EventPublisher",
        redis_client: "RedisClient",
        user_client: "UserClient | None" = None,
    ) -> None:
        """Initialize Executor servicer.

        Args:
            alpaca_client: Client for Alpaca trading API (None at startup, created dynamically)
            event_publisher: Publisher for execution events
            redis_client: Redis client for order tracking
            user_client: User Service gRPC client for dynamic broker config
        """
        self.alpaca = alpaca_client
        self.publisher = event_publisher
        self.redis = redis_client
        self.user_client = user_client
        self.user_trading_status: dict[str, dict] = {}  # {user_id: {enabled, stop_mode, timestamp}}
        self.trading_control_consumer = None

    async def _ensure_alpaca_client(self) -> "AlpacaClient":
        """Ensure Alpaca client is configured with valid credentials.

        Fetches credentials from User Service (DB) on first call.
        Credentials are cached in self.alpaca for subsequent calls.

        Returns:
            Configured AlpacaClient instance.

        Raises:
            ValueError: If no Alpaca credentials are available.
        """
        from .alpaca_client import AlpacaClient

        # If already configured with valid keys, skip
        if self.alpaca and self.alpaca.api_key and self.alpaca.secret_key:
            return self.alpaca

        # Fetch from User Service (single source of truth)
        if not self.user_client:
            raise ValueError("Alpaca client not configured and User Service unavailable")

        try:
            broker_config = await self.user_client.get_broker_config()
            if broker_config.configured:
                self.alpaca = AlpacaClient(
                    api_key=broker_config.alpaca_api_key,
                    secret_key=broker_config.alpaca_secret_key,
                    paper=True,
                )
                logger.info("Alpaca client refreshed from User Service broker config")
                return self.alpaca
            else:
                raise ValueError("Alpaca credentials not configured in User Service")
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Failed to fetch broker config from User Service: {e}")
            raise ValueError(f"Alpaca client not configured: {e}") from e

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

        # Ensure Alpaca client has credentials
        alpaca = await self._ensure_alpaca_client()

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

        # Check if trading is enabled for this user
        if not self._is_trading_enabled(request.user_id):
            status = self.user_trading_status.get(request.user_id, {})
            stop_mode = status.get("stop_mode", "unknown")
            return executor_pb2.ExecuteOrderResponse(
                success=False,
                error_message=f"Trading disabled for user (mode: {stop_mode})",
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
                result = await alpaca.submit_market_order(
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
                result = await alpaca.submit_limit_order(
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
                result = await alpaca.submit_bracket_order(
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

        alpaca = await self._ensure_alpaca_client()

        try:
            result = await alpaca.get_order_status(request.order_id)

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

        alpaca = await self._ensure_alpaca_client()

        success = await alpaca.cancel_order(request.order_id)

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

        alpaca = await self._ensure_alpaca_client()

        try:
            account = await alpaca.get_account()

            return executor_pb2.GetAccountResponse(
                cash=float(account.cash),
                buying_power=float(account.buying_power),
                portfolio_value=float(account.portfolio_value),
                equity=float(account.equity),
            )
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to get account info")

    async def GetPositions(
        self,
        request: executor_pb2.GetPositionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> executor_pb2.GetPositionsResponse:
        """Get all open positions from Alpaca.

        Args:
            request: Positions request with user_id
            context: gRPC context

        Returns:
            List of open positions
        """
        logger.info(f"Getting positions for user: {request.user_id}")

        alpaca = await self._ensure_alpaca_client()

        try:
            positions = await alpaca.get_positions()

            proto_positions = [
                executor_pb2.AlpacaPosition(
                    symbol=pos.symbol,
                    qty=float(pos.qty),
                    avg_entry_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    market_value=float(pos.market_value),
                    unrealized_pl=float(pos.unrealized_pl),
                    unrealized_plpc=float(pos.unrealized_plpc),
                    side=pos.side,
                )
                for pos in positions
            ]

            return executor_pb2.GetPositionsResponse(positions=proto_positions)
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to get positions")

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

    # ==================== Trading Control Methods ====================

    async def start_trading_control_consumer(self, brokers: str) -> None:
        """Start trading control event consumer.

        Args:
            brokers: Redpanda broker addresses
        """
        from shared.utils.event_consumer import EventConsumer

        self.trading_control_consumer = EventConsumer(
            brokers=brokers,
            group_id="executor-service",
            topics=["trading-control-events"],
        )
        self.trading_control_consumer.register_handler(
            "trading_control",
            self._handle_trading_control_event
        )
        await self.trading_control_consumer.start()
        logger.info("Trading control consumer started")

    async def stop_trading_control_consumer(self) -> None:
        """Stop trading control event consumer."""
        if self.trading_control_consumer:
            await self.trading_control_consumer.stop()
            logger.info("Trading control consumer stopped")

    async def _handle_trading_control_event(self, event: dict) -> None:
        """Handle trading control event.

        Args:
            event: Trading control event from Redpanda
        """
        user_id = event.get("user_id")
        action = event.get("action")
        stop_mode = event.get("stop_mode", "soft")

        if not user_id:
            return

        if action == "stopped":
            self.user_trading_status[user_id] = {
                "enabled": False,
                "stop_mode": stop_mode,
                "stopped_at": event.get("timestamp")
            }

            # Hard Stop: Cancel all pending orders immediately
            if stop_mode == "hard":
                cancelled = await self._cancel_all_user_orders(user_id)
                logger.info(f"Hard stop for user {user_id}: cancelled {cancelled} orders")
            else:
                logger.info(f"Soft stop for user {user_id}: protective orders only")

        elif action == "started":
            self.user_trading_status[user_id] = {
                "enabled": True,
                "stop_mode": "",
                "started_at": event.get("timestamp")
            }
            logger.info(f"Trading started for user {user_id}")

    async def _cancel_all_user_orders(self, user_id: str) -> int:
        """Cancel all pending orders for a user (hard stop).

        Args:
            user_id: User identifier

        Returns:
            Number of orders cancelled
        """
        cancelled = 0
        alpaca = await self._ensure_alpaca_client()

        # Find all user orders in Redis
        try:
            # Scan for order keys
            pattern = "order:*"
            cursor = 0
            keys_to_check = []

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                keys_to_check.extend(keys)
                if cursor == 0:
                    break

            # Check each order
            for raw_key in keys_to_check:
                try:
                    key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
                    order_data = await self.redis.hgetall(key)
                    if (order_data.get("user_id") == user_id and
                        order_data.get("status") in ["new", "partially_filled"]):
                        order_id = key.split(":")[-1]

                        # Cancel via Alpaca
                        if await alpaca.cancel_order(order_id):
                            cancelled += 1
                            await self.redis.hset(key, {"status": "cancelled"})
                            logger.info(f"Cancelled order {order_id} for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel order {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to cancel user orders: {e}")

        return cancelled

    def _is_trading_enabled(self, user_id: str) -> bool:
        """Check if trading is enabled for a user.

        Args:
            user_id: User identifier

        Returns:
            True if trading is enabled, False otherwise
        """
        status = self.user_trading_status.get(user_id, {"enabled": True})
        return status.get("enabled", True)
