"""
Portfolio Service - gRPC Servicer Implementation.

Implements the PortfolioService gRPC interface with:
- Redis caching (1-hour TTL for user-specific data)
- PostgreSQL persistence via Repository pattern
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import grpc
from shared.generated import portfolio_pb2, portfolio_pb2_grpc
from shared.generated.common_pb2 import Money
from shared.utils import PostgresClient, RedisClient

from .models import Portfolio, Position
from .repositories import PortfolioRepository

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
    ) -> None:
        """
        Initialize the servicer with required clients.

        Args:
            redis_client: Redis client for caching.
            postgres_client: PostgreSQL client for persistence.
            repository: Repository for database operations.
        """
        self.redis = redis_client
        self.postgres = postgres_client
        self.repository = repository or PortfolioRepository(postgres_client)

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
