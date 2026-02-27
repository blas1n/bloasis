"""Executor Service - Order execution management."""

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import grpc
from shared.generated import executor_pb2, executor_pb2_grpc

from .config import config
from .models import OrderStatus, OrderType

if TYPE_CHECKING:
    from .alpaca_client import AlpacaClient
    from .clients.risk_committee_client import RiskCommitteeClient
    from .clients.strategy_client import StrategyClient
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
        risk_committee_client: "RiskCommitteeClient | None" = None,
        strategy_client: "StrategyClient | None" = None,
    ) -> None:
        """Initialize Executor servicer.

        Args:
            alpaca_client: Client for Alpaca trading API (None at startup, created dynamically)
            event_publisher: Publisher for execution events
            redis_client: Redis client for order tracking
            user_client: User Service gRPC client for dynamic broker config
            risk_committee_client: Risk Committee gRPC client for order approval
            strategy_client: Strategy Service gRPC client for AI analysis trigger
        """
        self.alpaca = alpaca_client
        self.publisher = event_publisher
        self.redis = redis_client
        self.user_client = user_client
        self.risk_committee = risk_committee_client
        self.strategy = strategy_client
        self.user_trading_status: dict[str, dict] = {}  # {user_id: {enabled, stop_mode, timestamp}}
        self.trading_control_consumer = None
        self.strategy_signal_consumer = None
        self._analysis_timers: dict[str, asyncio.Task] = {}  # {user_id: periodic_task}

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
            logger.error(
                f"Redis unavailable for risk approval check: {e}. "
                f"Allowing execution for approval_id={approval_id} (degraded mode)"
            )
            return True

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
            "trading_control", self._handle_trading_control_event
        )
        await self.trading_control_consumer.start()
        logger.info("Trading control consumer started")

    async def start_strategy_signal_consumer(self, brokers: str) -> None:
        """Start strategy signal event consumer.

        Subscribes to strategy-events topic and processes trading signals
        through Risk Committee → Executor pipeline.

        Args:
            brokers: Redpanda broker addresses
        """
        from shared.utils.event_consumer import EventConsumer

        self.strategy_signal_consumer = EventConsumer(
            brokers=brokers,
            group_id="executor-signal-consumer",
            topics=["strategy-events"],
        )
        self.strategy_signal_consumer.register_handler(
            "strategy_signal",
            self._handle_strategy_signal,
        )
        await self.strategy_signal_consumer.start()
        logger.info("Strategy signal consumer started")

    async def stop_consumers(self) -> None:
        """Stop all event consumers and scheduled tasks."""
        if self.trading_control_consumer:
            await self.trading_control_consumer.stop()
            logger.info("Trading control consumer stopped")

        if self.strategy_signal_consumer:
            await self.strategy_signal_consumer.stop()
            logger.info("Strategy signal consumer stopped")

        # Cancel all periodic analysis timers
        for user_id, task in self._analysis_timers.items():
            task.cancel()
            logger.info(f"Cancelled analysis timer for user {user_id}")
        self._analysis_timers.clear()

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
                "stopped_at": event.get("timestamp"),
            }

            # Cancel periodic analysis for this user
            if user_id in self._analysis_timers:
                self._analysis_timers[user_id].cancel()
                del self._analysis_timers[user_id]
                logger.info(f"Cancelled analysis timer for user {user_id}")

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
                "started_at": event.get("timestamp"),
            }
            logger.info(f"Trading started for user {user_id}")

            # Trigger initial AI analysis and start periodic scheduler
            await self._start_periodic_analysis(user_id)

    async def _handle_strategy_signal(self, event: dict) -> None:
        """Handle strategy signal event from Redpanda.

        Processes trading signals: Risk Committee approval → Order execution.

        Args:
            event: Strategy signal event from Redpanda
        """
        symbol = event.get("symbol", "")
        action = event.get("action", "")
        params = event.get("parameters", {})
        event_id = event.get("event_id", "unknown")

        # Deduplicate: skip if this event was already processed
        if event_id != "unknown":
            dedup_key = f"signal:processed:{event_id}"
            try:
                is_new = await self.redis.set_nx(dedup_key, "1", ex=86400)
                if not is_new:
                    logger.info(f"Duplicate signal {event_id} for {symbol}, skipping")
                    return
            except Exception as e:
                logger.warning(f"Dedup check failed for {event_id}, proceeding: {e}")

        # Skip non-actionable signals
        if action not in ("buy", "sell"):
            logger.debug(f"Skipping non-actionable signal: {symbol} {action}")
            return

        # Extract user_id from parameters (published by event_publishing_node)
        user_id = params.get("user_id", "")
        if not user_id:
            logger.warning(f"Signal {event_id} missing user_id, skipping")
            return

        # Check if trading is enabled for this user
        if not self._is_trading_enabled(user_id):
            logger.info(f"Trading disabled for user {user_id}, skipping signal {event_id}")
            return

        logger.info(f"Processing strategy signal: {symbol} {action} for user {user_id}")

        # Extract signal parameters
        entry_price = float(params.get("entry_price", 0))
        stop_loss = float(params.get("stop_loss", 0))
        take_profit = float(params.get("take_profit", 0))
        size_pct = float(params.get("size_recommendation", 0))

        if entry_price <= 0 or size_pct <= 0:
            logger.warning(
                f"Invalid signal parameters for {symbol}: price={entry_price}, size={size_pct}"
            )
            return

        # Calculate order quantity from position size percentage
        qty = await self._calculate_order_qty(user_id, symbol, entry_price, size_pct)
        if qty <= 0:
            logger.info(f"Calculated qty=0 for {symbol}, skipping")
            return

        # Request Risk Committee approval
        if not self.risk_committee:
            logger.error("Risk Committee client not available, cannot execute signal")
            return

        try:
            approval = await self.risk_committee.evaluate_order(
                user_id=user_id,
                symbol=symbol,
                action=action,
                size=float(qty),
                price=entry_price,
                order_type="bracket" if stop_loss > 0 and take_profit > 0 else "market",
            )
        except Exception as e:
            logger.error(f"Risk Committee evaluation failed for {symbol}: {e}")
            return

        if not approval.approved:
            logger.info(
                f"Risk Committee rejected {symbol} {action}: "
                f"decision={approval.decision}, score={approval.risk_score:.2f}"
            )
            return

        # Store risk approval in Redis
        approval_id = str(uuid4())
        try:
            key = f"risk:approval:{approval_id}"
            await self.redis.set(key, "approved", ex=3600)  # 1-hour TTL
        except Exception as e:
            logger.warning(f"Failed to store risk approval: {e}")

        # Build and execute order via gRPC self-call
        side = "buy" if action == "buy" else "sell"

        # Validate bracket order prices make sense:
        # Buy: stop_loss < entry_price < take_profit
        # Sell: take_profit < entry_price < stop_loss
        use_bracket = stop_loss > 0 and take_profit > 0
        if use_bracket:
            if side == "buy" and not (stop_loss < entry_price < take_profit):
                logger.warning(
                    f"BRACKET_DOWNGRADE: Invalid bracket prices for buy {symbol}: "
                    f"SL={stop_loss} entry={entry_price} TP={take_profit}. "
                    f"Downgrading to market order without SL/TP protection."
                )
                use_bracket = False
            elif side == "sell" and not (take_profit < entry_price < stop_loss):
                logger.warning(
                    f"BRACKET_DOWNGRADE: Invalid bracket prices for sell {symbol}: "
                    f"TP={take_profit} entry={entry_price} SL={stop_loss}. "
                    f"Downgrading to market order without SL/TP protection."
                )
                use_bracket = False

        order_type = "bracket" if use_bracket else "market"

        request = executor_pb2.ExecuteOrderRequest(
            user_id=user_id,
            symbol=symbol,
            side=side,
            qty=int(qty),
            order_type=order_type,
            risk_approval_id=approval_id,
            stop_loss=stop_loss if use_bracket else 0.0,
            take_profit=take_profit if use_bracket else 0.0,
        )

        # Execute order directly (reuse existing logic)
        response = await self.ExecuteOrder(request, None)

        if response.success:
            logger.info(
                f"Auto-trade executed: {symbol} {side} qty={qty} order_id={response.order_id}"
            )
        else:
            logger.warning(f"Auto-trade failed: {symbol} {side} - {response.error_message}")
            # Clean up unused risk approval
            try:
                await self.redis.delete(f"risk:approval:{approval_id}")
            except Exception as e:
                logger.debug(f"Failed to clean approval {approval_id}: {e}")

    async def _calculate_order_qty(
        self, user_id: str, symbol: str, price: float, size_pct: float
    ) -> int:
        """Calculate order quantity from position size percentage.

        Args:
            user_id: User identifier.
            symbol: Stock symbol.
            price: Current price per share.
            size_pct: Target position size as fraction of portfolio (0.0-1.0).

        Returns:
            Number of shares to order (integer).
        """
        try:
            alpaca = await self._ensure_alpaca_client()
            account = await alpaca.get_account()
            portfolio_value = float(account.portfolio_value)
        except Exception as e:
            logger.warning(f"Failed to get account value for qty calc: {e}")
            return 0

        if portfolio_value <= 0 or price <= 0:
            return 0

        target_value = portfolio_value * size_pct
        qty = int(target_value / price)
        return max(0, qty)

    async def _start_periodic_analysis(self, user_id: str) -> None:
        """Start periodic AI analysis for a user.

        Triggers an immediate AI analysis, then schedules periodic runs.

        Args:
            user_id: User identifier.
        """
        # Cancel existing timer if any
        if user_id in self._analysis_timers:
            self._analysis_timers[user_id].cancel()

        async def _periodic_loop() -> None:
            """Run AI analysis periodically until cancelled."""
            while True:
                try:
                    await self._trigger_ai_analysis(user_id)
                except Exception as e:
                    logger.error(f"Periodic AI analysis failed for {user_id}: {e}")
                await asyncio.sleep(config.ai_analysis_interval)

        self._analysis_timers[user_id] = asyncio.create_task(_periodic_loop())
        logger.info(
            f"Started periodic AI analysis for user {user_id} "
            f"(interval: {config.ai_analysis_interval}s)"
        )

    async def _trigger_ai_analysis(self, user_id: str) -> None:
        """Trigger AI analysis via Strategy Service.

        Args:
            user_id: User identifier.
        """
        if not self.strategy:
            logger.warning("Strategy client not available, cannot trigger AI analysis")
            return

        if not self._is_trading_enabled(user_id):
            logger.info(f"Trading disabled for {user_id}, skipping AI analysis trigger")
            return

        try:
            response = await self.strategy.run_ai_analysis(user_id)
            logger.info(
                f"AI analysis triggered for user {user_id}: "
                f"phase={response.phase}, signals={response.signals_published}"
            )
        except Exception as e:
            logger.error(f"Failed to trigger AI analysis for {user_id}: {e}")

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
                    if order_data.get("user_id") == user_id and order_data.get("status") in [
                        "new",
                        "partially_filled",
                    ]:
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
