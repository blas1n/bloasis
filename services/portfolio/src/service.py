"""
Portfolio Service - gRPC Servicer Implementation.

Implements the PortfolioService gRPC interface with:
- Redis caching (1-hour TTL for user-specific data)
- PostgreSQL persistence via Repository pattern
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import grpc

if TYPE_CHECKING:
    from typing import Any

    AlpacaClient = Any  # Executor service's AlpacaClient
from shared.generated import portfolio_pb2, portfolio_pb2_grpc
from shared.generated.common_pb2 import Money
from shared.utils import PostgresClient, RedisClient

from .models import Portfolio, Position
from .pnl_calculator import PnLCalculator
from .repositories import PortfolioRepository, TradeRepository

logger = logging.getLogger(__name__)

# Cache configuration (user-specific caching - Tier 3)
CACHE_TTL = 3600  # 1 hour in seconds


def _portfolio_cache_key(user_id: str) -> str:
    """Generate cache key for user portfolio."""
    return f"user:{user_id}:portfolio"


def _positions_cache_key(user_id: str) -> str:
    """Generate cache key for user positions."""
    return f"user:{user_id}:positions"


def _decimal_to_money(value: Decimal, currency: str = "USD") -> Money:
    """
    Convert a Decimal to a proto Money message.

    Args:
        value: Decimal value to convert.
        currency: ISO 4217 currency code.

    Returns:
        Money proto message with string amount for precision.
    """
    return Money(amount=str(value), currency=currency)


def _position_to_proto(position: Position) -> portfolio_pb2.Position:
    """
    Convert a Position domain object to proto message.

    Args:
        position: Position domain object.

    Returns:
        Position proto message.
    """
    return portfolio_pb2.Position(
        symbol=position.symbol,
        quantity=position.quantity,
        avg_cost=_decimal_to_money(position.avg_cost, position.currency),
        current_price=_decimal_to_money(position.current_price, position.currency),
        current_value=_decimal_to_money(position.current_value, position.currency),
        unrealized_pnl=_decimal_to_money(position.unrealized_pnl, position.currency),
        unrealized_pnl_percent=position.unrealized_pnl_percent,
    )


def _portfolio_to_cache_dict(portfolio: Portfolio) -> dict:
    """
    Convert a Portfolio domain object to a cache-friendly dict.

    Args:
        portfolio: Portfolio domain object.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    return {
        "user_id": portfolio.user_id,
        "total_value": str(portfolio.total_value),
        "cash_balance": str(portfolio.cash_balance),
        "invested_value": str(portfolio.invested_value),
        "total_return": portfolio.total_return,
        "total_return_amount": str(portfolio.total_return_amount),
        "currency": portfolio.currency,
        "timestamp": portfolio.timestamp,
    }


def _cache_dict_to_portfolio(data: dict) -> Portfolio:
    """
    Convert a cached dict back to a Portfolio domain object.

    Args:
        data: Dictionary from cache.

    Returns:
        Portfolio domain object.
    """
    return Portfolio(
        user_id=data["user_id"],
        total_value=Decimal(data["total_value"]),
        cash_balance=Decimal(data["cash_balance"]),
        invested_value=Decimal(data["invested_value"]),
        total_return=data["total_return"],
        total_return_amount=Decimal(data["total_return_amount"]),
        currency=data["currency"],
        timestamp=data["timestamp"],
    )


def _positions_to_cache_list(positions: list[Position]) -> list[dict]:
    """
    Convert Position domain objects to a cache-friendly list.

    Args:
        positions: List of Position domain objects.

    Returns:
        List of dictionaries suitable for JSON serialization.
    """
    return [
        {
            "symbol": p.symbol,
            "quantity": p.quantity,
            "avg_cost": str(p.avg_cost),
            "current_price": str(p.current_price),
            "current_value": str(p.current_value),
            "unrealized_pnl": str(p.unrealized_pnl),
            "unrealized_pnl_percent": p.unrealized_pnl_percent,
            "currency": p.currency,
        }
        for p in positions
    ]


def _cache_list_to_positions(data: list[dict]) -> list[Position]:
    """
    Convert cached list back to Position domain objects.

    Args:
        data: List of dictionaries from cache.

    Returns:
        List of Position domain objects.
    """
    return [
        Position(
            symbol=d["symbol"],
            quantity=d["quantity"],
            avg_cost=Decimal(d["avg_cost"]),
            current_price=Decimal(d["current_price"]),
            current_value=Decimal(d["current_value"]),
            unrealized_pnl=Decimal(d["unrealized_pnl"]),
            unrealized_pnl_percent=d["unrealized_pnl_percent"],
            currency=d["currency"],
        )
        for d in data
    ]


class PortfolioServicer(portfolio_pb2_grpc.PortfolioServiceServicer):
    """
    gRPC servicer implementing the PortfolioService interface.

    Provides portfolio and position retrieval for users.
    Results are cached for 1 hour (user-specific data).
    """

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        postgres_client: Optional[PostgresClient] = None,
        repository: Optional[PortfolioRepository] = None,
        trade_repository: Optional[TradeRepository] = None,
        alpaca_client: Optional["AlpacaClient"] = None,
    ) -> None:
        """
        Initialize the servicer with required clients.

        Args:
            redis_client: Redis client for caching.
            postgres_client: PostgreSQL client for persistence.
            repository: Repository for database operations.
            trade_repository: Repository for trade operations.
            alpaca_client: Alpaca client for broker sync.
        """
        self.redis = redis_client
        self.postgres = postgres_client
        self.repository = repository or PortfolioRepository(postgres_client)
        self.trade_repository = trade_repository
        self.alpaca_client = alpaca_client

    async def GetPortfolio(
        self,
        request: portfolio_pb2.GetPortfolioRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPortfolioResponse:
        """
        Get the current portfolio summary for a user.

        Implements caching strategy:
        1. Check Redis cache
        2. If cache miss, query database via repository
        3. Cache the result for 1 hour

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetPortfolioResponse with portfolio summary.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.GetPortfolioResponse()

            cache_key = _portfolio_cache_key(user_id)

            # Check cache first
            if self.redis:
                cached = await self.redis.get(cache_key)
                if cached and isinstance(cached, dict):
                    logger.info(f"Cache hit for portfolio: {user_id}")
                    portfolio = _cache_dict_to_portfolio(cached)
                    return self._portfolio_to_response(portfolio)

            # Cache miss - query database
            logger.info(f"Cache miss for portfolio: {user_id}")
            timestamp = datetime.now(timezone.utc).isoformat()
            portfolio = await self.repository.get_full_portfolio(user_id, timestamp)

            # Cache the result
            if self.redis:
                cache_data = _portfolio_to_cache_dict(portfolio)
                await self.redis.setex(cache_key, CACHE_TTL, cache_data)
                logger.info(f"Cached portfolio for user {user_id} with TTL {CACHE_TTL}s")

            return self._portfolio_to_response(portfolio)

        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get portfolio: {str(e)}")
            return portfolio_pb2.GetPortfolioResponse()

    async def GetPositions(
        self,
        request: portfolio_pb2.GetPositionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPositionsResponse:
        """
        Get all positions for a user's portfolio.

        Implements caching strategy:
        1. Check Redis cache
        2. If cache miss, query database via repository
        3. Cache the result for 1 hour

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetPositionsResponse with list of positions.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.GetPositionsResponse()

            cache_key = _positions_cache_key(user_id)
            timestamp = datetime.now(timezone.utc).isoformat()

            # Check cache first
            if self.redis:
                cached = await self.redis.get(cache_key)
                if cached and isinstance(cached, list):
                    logger.info(f"Cache hit for positions: {user_id}")
                    positions = _cache_list_to_positions(cached)
                    return self._positions_to_response(user_id, positions, timestamp)

            # Cache miss - query database
            logger.info(f"Cache miss for positions: {user_id}")
            positions = await self.repository.get_position_domain_objects(user_id)

            # Cache the result
            if self.redis:
                cache_data = _positions_to_cache_list(positions)
                await self.redis.setex(cache_key, CACHE_TTL, cache_data)
                logger.info(f"Cached positions for user {user_id} with TTL {CACHE_TTL}s")

            return self._positions_to_response(user_id, positions, timestamp)

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get positions: {str(e)}")
            return portfolio_pb2.GetPositionsResponse()

    def _portfolio_to_response(self, portfolio: Portfolio) -> portfolio_pb2.GetPortfolioResponse:
        """
        Convert a Portfolio domain object to gRPC response.

        Args:
            portfolio: Portfolio domain object.

        Returns:
            GetPortfolioResponse proto message.
        """
        return portfolio_pb2.GetPortfolioResponse(
            user_id=portfolio.user_id,
            total_value=_decimal_to_money(portfolio.total_value, portfolio.currency),
            cash_balance=_decimal_to_money(portfolio.cash_balance, portfolio.currency),
            invested_value=_decimal_to_money(portfolio.invested_value, portfolio.currency),
            total_return=portfolio.total_return,
            total_return_amount=_decimal_to_money(
                portfolio.total_return_amount, portfolio.currency
            ),
            timestamp=portfolio.timestamp or "",
        )

    def _positions_to_response(
        self, user_id: str, positions: list[Position], timestamp: str
    ) -> portfolio_pb2.GetPositionsResponse:
        """
        Convert Position domain objects to gRPC response.

        Args:
            user_id: User identifier.
            positions: List of Position domain objects.
            timestamp: ISO 8601 timestamp.

        Returns:
            GetPositionsResponse proto message.
        """
        proto_positions = [_position_to_proto(p) for p in positions]
        return portfolio_pb2.GetPositionsResponse(
            user_id=user_id,
            positions=proto_positions,
            timestamp=timestamp,
        )

    async def _invalidate_user_cache(self, user_id: str) -> None:
        """
        Invalidate all cache keys for a user after write operations.

        Args:
            user_id: User identifier whose cache should be invalidated.
        """
        if self.redis:
            await self.redis.delete(_portfolio_cache_key(user_id))
            await self.redis.delete(_positions_cache_key(user_id))
            logger.info(f"Invalidated cache for user {user_id}")

    async def UpdateCashBalance(
        self,
        request: portfolio_pb2.UpdateCashBalanceRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.UpdateCashBalanceResponse:
        """
        Update the cash balance for a user's portfolio.

        Args:
            request: The gRPC request containing user_id, amount, and operation.
            context: The gRPC servicer context.

        Returns:
            UpdateCashBalanceResponse with new balance.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.UpdateCashBalanceResponse()

            operation = request.operation
            if operation not in ("set", "delta"):
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("operation must be 'set' or 'delta'")
                return portfolio_pb2.UpdateCashBalanceResponse()

            # Parse amount from Money proto
            amount = Decimal(request.amount.amount) if request.amount.amount else Decimal("0")

            # Update cash balance in database
            new_balance = await self.repository.update_cash_balance(user_id, amount, operation)

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            timestamp = datetime.now(timezone.utc).isoformat()
            return portfolio_pb2.UpdateCashBalanceResponse(
                success=True,
                new_balance=_decimal_to_money(new_balance, "USD"),
                timestamp=timestamp,
            )

        except ValueError as e:
            logger.error(f"Failed to update cash balance: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return portfolio_pb2.UpdateCashBalanceResponse()
        except Exception as e:
            logger.error(f"Failed to update cash balance: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to update cash balance: {str(e)}")
            return portfolio_pb2.UpdateCashBalanceResponse()

    async def CreatePosition(
        self,
        request: portfolio_pb2.CreatePositionRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.CreatePositionResponse:
        """
        Create a new position in the user's portfolio.

        Args:
            request: The gRPC request containing position details.
            context: The gRPC servicer context.

        Returns:
            CreatePositionResponse with created position.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.CreatePositionResponse()

            symbol = request.symbol
            if not symbol:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("symbol is required")
                return portfolio_pb2.CreatePositionResponse()

            quantity = request.quantity
            if quantity <= 0:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("quantity must be greater than 0")
                return portfolio_pb2.CreatePositionResponse()

            cost_per_share = (
                Decimal(request.cost_per_share.amount)
                if request.cost_per_share.amount
                else Decimal("0")
            )
            if cost_per_share <= 0:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("cost_per_share must be greater than 0")
                return portfolio_pb2.CreatePositionResponse()

            currency = request.currency if request.currency else "USD"

            # Check if position already exists
            existing = await self.repository.get_position_by_symbol(user_id, symbol)
            if existing is not None:
                context.set_code(grpc.StatusCode.ALREADY_EXISTS)
                context.set_details(f"Position for symbol {symbol} already exists")
                return portfolio_pb2.CreatePositionResponse()

            # Create position in database
            position_record = await self.repository.create_position(
                user_id=user_id,
                symbol=symbol,
                quantity=quantity,
                cost_per_share=cost_per_share,
                currency=currency,
            )

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            # Convert to domain object for response
            position = Position.from_record(position_record)
            timestamp = datetime.now(timezone.utc).isoformat()

            return portfolio_pb2.CreatePositionResponse(
                success=True,
                position=_position_to_proto(position),
                timestamp=timestamp,
            )

        except ValueError as e:
            logger.error(f"Failed to create position: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return portfolio_pb2.CreatePositionResponse()
        except Exception as e:
            logger.error(f"Failed to create position: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create position: {str(e)}")
            return portfolio_pb2.CreatePositionResponse()

    async def UpdatePosition(
        self,
        request: portfolio_pb2.UpdatePositionRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.UpdatePositionResponse:
        """
        Update an existing position in the user's portfolio.

        Args:
            request: The gRPC request containing update details.
            context: The gRPC servicer context.

        Returns:
            UpdatePositionResponse with updated position.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.UpdatePositionResponse()

            symbol = request.symbol
            if not symbol:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("symbol is required")
                return portfolio_pb2.UpdatePositionResponse()

            # Check if position exists
            existing = await self.repository.get_position_by_symbol(user_id, symbol)
            if existing is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Position for symbol {symbol} not found")
                return portfolio_pb2.UpdatePositionResponse()

            quantity_delta = request.quantity_delta
            cost_per_share = (
                Decimal(request.cost_per_share.amount)
                if request.cost_per_share and request.cost_per_share.amount
                else None
            )
            current_price = (
                Decimal(request.current_price.amount)
                if request.current_price and request.current_price.amount
                else None
            )

            # Update position in database
            position_record = await self.repository.update_position(
                user_id=user_id,
                symbol=symbol,
                quantity_delta=quantity_delta,
                cost_per_share=cost_per_share,
                current_price=current_price,
            )

            if position_record is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Position for symbol {symbol} not found")
                return portfolio_pb2.UpdatePositionResponse()

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            # Convert to domain object for response
            position = Position.from_record(position_record)
            timestamp = datetime.now(timezone.utc).isoformat()

            return portfolio_pb2.UpdatePositionResponse(
                success=True,
                position=_position_to_proto(position),
                timestamp=timestamp,
            )

        except ValueError as e:
            logger.error(f"Failed to update position: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return portfolio_pb2.UpdatePositionResponse()
        except Exception as e:
            logger.error(f"Failed to update position: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to update position: {str(e)}")
            return portfolio_pb2.UpdatePositionResponse()

    async def DeletePosition(
        self,
        request: portfolio_pb2.DeletePositionRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.DeletePositionResponse:
        """
        Delete a position from the user's portfolio.

        Args:
            request: The gRPC request containing user_id and symbol.
            context: The gRPC servicer context.

        Returns:
            DeletePositionResponse with success status.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.DeletePositionResponse()

            symbol = request.symbol
            if not symbol:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("symbol is required")
                return portfolio_pb2.DeletePositionResponse()

            # Delete position from database
            deleted = await self.repository.delete_position(user_id, symbol)

            if not deleted:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Position for symbol {symbol} not found")
                return portfolio_pb2.DeletePositionResponse()

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            timestamp = datetime.now(timezone.utc).isoformat()
            return portfolio_pb2.DeletePositionResponse(
                success=True,
                timestamp=timestamp,
            )

        except ValueError as e:
            logger.error(f"Failed to delete position: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return portfolio_pb2.DeletePositionResponse()
        except Exception as e:
            logger.error(f"Failed to delete position: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to delete position: {str(e)}")
            return portfolio_pb2.DeletePositionResponse()

    async def GetPortfolioSummary(
        self,
        request: portfolio_pb2.GetPortfolioSummaryRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPortfolioSummaryResponse:
        """Get detailed portfolio summary with P&L.

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetPortfolioSummaryResponse with P&L details.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.GetPortfolioSummaryResponse()

            # Get positions
            positions = await self.repository.get_position_domain_objects(user_id)

            # Get realized P&L from trade history
            realized_pnl = Decimal("0")
            if self.trade_repository:
                realized_pnl = await self.trade_repository.get_realized_pnl(user_id)

            # Calculate P&L
            pnl_calculator = PnLCalculator()
            position_dicts = [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                }
                for p in positions
            ]
            portfolio_pnl = await pnl_calculator.calculate_portfolio_pnl(
                position_dicts, realized_pnl
            )

            # Get cash balance
            portfolio = await self.repository.get_full_portfolio(
                user_id, datetime.now(timezone.utc).isoformat()
            )
            cash = portfolio.cash_balance
            total_equity = cash + portfolio_pnl.total_market_value

            return portfolio_pb2.GetPortfolioSummaryResponse(
                total_equity=float(total_equity),
                cash=float(cash),
                buying_power=float(cash),  # Simplified - no margin
                market_value=float(portfolio_pnl.total_market_value),
                unrealized_pnl=float(portfolio_pnl.total_unrealized_pnl),
                unrealized_pnl_pct=float(portfolio_pnl.total_unrealized_pnl_pct),
                realized_pnl=float(portfolio_pnl.total_realized_pnl),
                daily_pnl=float(portfolio_pnl.total_daily_pnl),
                daily_pnl_pct=float(portfolio_pnl.total_daily_pnl_pct),
                position_count=len(positions),
            )

        except Exception as e:
            logger.error(f"Failed to get portfolio summary: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get portfolio summary: {str(e)}")
            return portfolio_pb2.GetPortfolioSummaryResponse()

    async def SyncWithAlpaca(
        self,
        request: portfolio_pb2.SyncWithAlpacaRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.SyncWithAlpacaResponse:
        """Sync positions with Alpaca account.

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            SyncWithAlpacaResponse with sync results.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.SyncWithAlpacaResponse()

            if self.alpaca_client is None:
                return portfolio_pb2.SyncWithAlpacaResponse(
                    success=False,
                    positions_synced=0,
                    error_message="Alpaca client not configured",
                )

            # Get positions from Alpaca
            alpaca_positions = await self.alpaca_client.get_positions()
            synced_count = 0

            for pos in alpaca_positions:
                # Update or create position
                existing = await self.repository.get_position_by_symbol(user_id, pos.symbol)

                if existing:
                    await self.repository.update_position(
                        user_id=user_id,
                        symbol=pos.symbol,
                        quantity_delta=int(pos.qty) - existing.quantity,
                        cost_per_share=Decimal(str(pos.avg_entry_price)),
                        current_price=Decimal(str(pos.current_price)),
                    )
                else:
                    await self.repository.create_position(
                        user_id=user_id,
                        symbol=pos.symbol,
                        quantity=int(pos.qty),
                        cost_per_share=Decimal(str(pos.avg_entry_price)),
                        currency="USD",
                    )
                synced_count += 1

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            return portfolio_pb2.SyncWithAlpacaResponse(
                success=True,
                positions_synced=synced_count,
            )

        except Exception as e:
            logger.error(f"Failed to sync with Alpaca: {e}")
            return portfolio_pb2.SyncWithAlpacaResponse(
                success=False,
                positions_synced=0,
                error_message=str(e),
            )

    async def RecordTrade(
        self,
        request: portfolio_pb2.RecordTradeRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.RecordTradeResponse:
        """Record a completed trade for P&L tracking.

        Args:
            request: The gRPC request containing trade details.
            context: The gRPC servicer context.

        Returns:
            RecordTradeResponse with success status.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.RecordTradeResponse()

            if not request.order_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("order_id is required")
                return portfolio_pb2.RecordTradeResponse()

            if self.trade_repository is None:
                return portfolio_pb2.RecordTradeResponse(
                    success=False,
                    error_message="Trade repository not configured",
                )

            # Calculate realized P&L for sell trades
            realized_pnl = Decimal("0")
            if request.side.lower() == "sell":
                # Get position to calculate realized P&L
                position = await self.repository.get_position_by_symbol(user_id, request.symbol)
                if position:
                    pnl_calculator = PnLCalculator()
                    realized_pnl = pnl_calculator.calculate_trade_pnl(
                        side=request.side,
                        qty=Decimal(str(request.qty)),
                        price=Decimal(str(request.price)),
                        avg_cost=position.avg_cost,
                        commission=Decimal(str(request.commission)),
                    )

            # Save trade
            await self.trade_repository.save_trade(
                user_id=user_id,
                order_id=request.order_id,
                symbol=request.symbol,
                side=request.side,
                qty=Decimal(str(request.qty)),
                price=Decimal(str(request.price)),
                commission=Decimal(str(request.commission)),
                realized_pnl=realized_pnl,
            )

            # Update position based on trade
            await self._update_position_from_trade(
                user_id=user_id,
                symbol=request.symbol,
                side=request.side,
                qty=Decimal(str(request.qty)),
                price=Decimal(str(request.price)),
            )

            # Invalidate cache
            await self._invalidate_user_cache(user_id)

            return portfolio_pb2.RecordTradeResponse(success=True)

        except Exception as e:
            logger.error(f"Failed to record trade: {e}")
            return portfolio_pb2.RecordTradeResponse(
                success=False,
                error_message=str(e),
            )

    async def GetTradeHistory(
        self,
        request: portfolio_pb2.GetTradeHistoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetTradeHistoryResponse:
        """Get trade history for a user.

        Args:
            request: The gRPC request with filters.
            context: The gRPC servicer context.

        Returns:
            GetTradeHistoryResponse with trade list.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return portfolio_pb2.GetTradeHistoryResponse()

            if self.trade_repository is None:
                return portfolio_pb2.GetTradeHistoryResponse()

            # Parse date filters
            start_date = None
            end_date = None
            if request.start_date:
                start_date = datetime.fromisoformat(request.start_date.replace("Z", "+00:00"))
            if request.end_date:
                end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

            # Get trades
            trades = await self.trade_repository.get_trades(
                user_id=user_id,
                symbol=request.symbol if request.symbol else None,
                start_date=start_date,
                end_date=end_date,
                limit=request.limit if request.limit > 0 else 100,
            )

            # Calculate total realized P&L
            total_realized_pnl = sum((t.realized_pnl for t in trades), Decimal("0"))

            # Convert to proto
            proto_trades = [
                portfolio_pb2.Trade(
                    order_id=t.order_id,
                    symbol=t.symbol,
                    side=t.side,
                    qty=float(t.qty),
                    price=float(t.price),
                    commission=float(t.commission),
                    executed_at=t.executed_at.isoformat(),
                    realized_pnl=float(t.realized_pnl),
                )
                for t in trades
            ]

            return portfolio_pb2.GetTradeHistoryResponse(
                trades=proto_trades,
                total_realized_pnl=float(total_realized_pnl),
            )

        except Exception as e:
            logger.error(f"Failed to get trade history: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get trade history: {str(e)}")
            return portfolio_pb2.GetTradeHistoryResponse()

    async def _update_position_from_trade(
        self,
        user_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> None:
        """Update position based on a trade.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol.
            side: Trade side ("buy" or "sell").
            qty: Trade quantity.
            price: Execution price.
        """
        existing = await self.repository.get_position_by_symbol(user_id, symbol)

        if side.lower() == "buy":
            if existing:
                # Update existing position with new average cost
                old_qty = Decimal(str(existing.quantity))
                old_cost = existing.avg_cost
                new_qty = old_qty + qty
                # Weighted average cost
                new_avg_cost = ((old_qty * old_cost) + (qty * price)) / new_qty

                await self.repository.update_position(
                    user_id=user_id,
                    symbol=symbol,
                    quantity_delta=int(qty),
                    cost_per_share=new_avg_cost,
                    current_price=price,
                )
            else:
                # Create new position
                await self.repository.create_position(
                    user_id=user_id,
                    symbol=symbol,
                    quantity=int(qty),
                    cost_per_share=price,
                    currency="USD",
                )
        elif side.lower() == "sell":
            if existing:
                new_qty = existing.quantity - int(qty)
                if new_qty <= 0:
                    # Close position entirely
                    await self.repository.delete_position(user_id, symbol)
                else:
                    # Reduce position
                    await self.repository.update_position(
                        user_id=user_id,
                        symbol=symbol,
                        quantity_delta=-int(qty),
                        current_price=price,
                    )
