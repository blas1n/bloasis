"""
Unit tests for Portfolio Service.

All external dependencies (Redis, PostgreSQL) are mocked.
Target: 80%+ code coverage.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import Portfolio, Position


class TestPosition:
    """Tests for Position domain model."""

    def test_position_creation(self) -> None:
        """Should create Position with all fields."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.25"),
            current_price=Decimal("175.50"),
            current_value=Decimal("17550.00"),
            unrealized_pnl=Decimal("2525.00"),
            unrealized_pnl_percent=16.81,
            currency="USD",
        )
        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.avg_cost == Decimal("150.25")
        assert position.current_price == Decimal("175.50")
        assert position.unrealized_pnl == Decimal("2525.00")

    def test_position_from_record(self) -> None:
        """Should create Position from database record."""
        from src.models import PositionRecord

        mock_record = MagicMock(spec=PositionRecord)
        mock_record.symbol = "GOOGL"
        mock_record.quantity = 50
        mock_record.avg_cost = Decimal("2500.00")
        mock_record.current_price = Decimal("2750.00")
        mock_record.currency = "USD"

        position = Position.from_record(mock_record)

        assert position.symbol == "GOOGL"
        assert position.quantity == 50
        assert position.avg_cost == Decimal("2500.00")
        assert position.current_price == Decimal("2750.00")
        assert position.current_value == Decimal("137500.00")  # 50 * 2750
        assert position.unrealized_pnl == Decimal("12500.00")  # (2750 - 2500) * 50
        assert position.unrealized_pnl_percent == pytest.approx(10.0, rel=0.01)

    def test_position_from_record_zero_cost(self) -> None:
        """Should handle zero avg_cost without division error."""
        from src.models import PositionRecord

        mock_record = MagicMock(spec=PositionRecord)
        mock_record.symbol = "TEST"
        mock_record.quantity = 100
        mock_record.avg_cost = Decimal("0")
        mock_record.current_price = Decimal("100.00")
        mock_record.currency = "USD"

        position = Position.from_record(mock_record)

        assert position.unrealized_pnl_percent == 0.0


class TestPortfolio:
    """Tests for Portfolio domain model."""

    def test_portfolio_creation(self) -> None:
        """Should create Portfolio with all fields."""
        portfolio = Portfolio(
            user_id="user123",
            total_value=Decimal("100000.00"),
            cash_balance=Decimal("25000.00"),
            invested_value=Decimal("75000.00"),
            total_return=15.5,
            total_return_amount=Decimal("10000.00"),
            currency="USD",
            timestamp="2025-01-26T14:30:00Z",
        )
        assert portfolio.user_id == "user123"
        assert portfolio.total_value == Decimal("100000.00")
        assert portfolio.cash_balance == Decimal("25000.00")
        assert portfolio.invested_value == Decimal("75000.00")
        assert portfolio.total_return == 15.5

    def test_portfolio_from_records_with_data(self) -> None:
        """Should create Portfolio from database records."""
        from src.models import PortfolioRecord

        mock_portfolio_record = MagicMock(spec=PortfolioRecord)
        mock_portfolio_record.user_id = "user123"
        mock_portfolio_record.cash_balance = Decimal("25000.00")
        mock_portfolio_record.currency = "USD"

        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                current_price=Decimal("175.00"),
                current_value=Decimal("17500.00"),
                unrealized_pnl=Decimal("2500.00"),
                unrealized_pnl_percent=16.67,
                currency="USD",
            ),
            Position(
                symbol="GOOGL",
                quantity=50,
                avg_cost=Decimal("2500.00"),
                current_price=Decimal("2750.00"),
                current_value=Decimal("137500.00"),
                unrealized_pnl=Decimal("12500.00"),
                unrealized_pnl_percent=10.0,
                currency="USD",
            ),
        ]

        portfolio = Portfolio.from_records(mock_portfolio_record, positions, "2025-01-26T14:30:00Z")

        assert portfolio.user_id == "user123"
        assert portfolio.cash_balance == Decimal("25000.00")
        assert portfolio.invested_value == Decimal("155000.00")  # 17500 + 137500
        assert portfolio.total_value == Decimal("180000.00")  # 25000 + 155000
        assert portfolio.total_return_amount == Decimal("15000.00")  # 2500 + 12500

    def test_portfolio_from_records_no_portfolio(self) -> None:
        """Should return empty portfolio when no record exists."""
        portfolio = Portfolio.from_records(None, [], "2025-01-26T14:30:00Z")

        assert portfolio.total_value == Decimal("0")
        assert portfolio.cash_balance == Decimal("0")
        assert portfolio.invested_value == Decimal("0")
        assert portfolio.total_return == 0.0

    def test_portfolio_from_records_no_positions(self) -> None:
        """Should handle portfolio with no positions."""
        from src.models import PortfolioRecord

        mock_portfolio_record = MagicMock(spec=PortfolioRecord)
        mock_portfolio_record.user_id = "user123"
        mock_portfolio_record.cash_balance = Decimal("50000.00")
        mock_portfolio_record.currency = "USD"

        portfolio = Portfolio.from_records(mock_portfolio_record, [], "2025-01-26T14:30:00Z")

        assert portfolio.cash_balance == Decimal("50000.00")
        assert portfolio.invested_value == Decimal("0")
        assert portfolio.total_value == Decimal("50000.00")
        assert portfolio.total_return == 0.0


class TestPortfolioServicer:
    """Tests for PortfolioServicer gRPC implementation."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.engine = MagicMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository for database operations."""
        mock = AsyncMock()
        mock.get_portfolio = AsyncMock(return_value=None)
        mock.get_positions = AsyncMock(return_value=[])
        mock.get_full_portfolio = AsyncMock()
        mock.get_position_domain_objects = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_portfolio_cache_hit(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return cached portfolio data on cache hit."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Setup cache hit
        mock_redis.get.return_value = {
            "user_id": "user123",
            "total_value": "100000.00",
            "cash_balance": "25000.00",
            "invested_value": "75000.00",
            "total_return": 15.5,
            "total_return_amount": "10000.00",
            "currency": "USD",
            "timestamp": "2025-01-26T14:30:00Z",
        }

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPortfolioRequest(user_id="user123")
        response = await servicer.GetPortfolio(request, mock_context)

        assert response.user_id == "user123"
        assert response.total_value.amount == "100000.00"
        assert response.cash_balance.amount == "25000.00"
        mock_redis.get.assert_called_once_with("user:user123:portfolio")
        mock_repository.get_full_portfolio.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_portfolio_cache_miss(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should query database and cache on cache miss."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Setup cache miss
        mock_redis.get.return_value = None

        # Setup repository response
        mock_repository.get_full_portfolio.return_value = Portfolio(
            user_id="user123",
            total_value=Decimal("100000.00"),
            cash_balance=Decimal("25000.00"),
            invested_value=Decimal("75000.00"),
            total_return=15.5,
            total_return_amount=Decimal("10000.00"),
            currency="USD",
            timestamp="2025-01-26T14:30:00Z",
        )

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPortfolioRequest(user_id="user123")
        response = await servicer.GetPortfolio(request, mock_context)

        assert response.user_id == "user123"
        assert response.total_value.amount == "100000.00"

        # Should cache result
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "user:user123:portfolio"
        assert call_args[0][1] == 3600  # 1 hour TTL

    @pytest.mark.asyncio
    async def test_get_portfolio_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPortfolioRequest(user_id="")
        await servicer.GetPortfolio(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_portfolio_no_redis(
        self,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        mock_repository.get_full_portfolio.return_value = Portfolio(
            user_id="user123",
            total_value=Decimal("50000.00"),
            cash_balance=Decimal("50000.00"),
            invested_value=Decimal("0"),
            total_return=0.0,
            total_return_amount=Decimal("0"),
            currency="USD",
            timestamp="2025-01-26T14:30:00Z",
        )

        servicer = PortfolioServicer(
            redis_client=None,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPortfolioRequest(user_id="user123")
        response = await servicer.GetPortfolio(request, mock_context)

        assert response.user_id == "user123"

    @pytest.mark.asyncio
    async def test_get_positions_cache_hit(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return cached positions on cache hit."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Setup cache hit
        mock_redis.get.return_value = [
            {
                "symbol": "AAPL",
                "quantity": 100,
                "avg_cost": "150.00",
                "current_price": "175.00",
                "current_value": "17500.00",
                "unrealized_pnl": "2500.00",
                "unrealized_pnl_percent": 16.67,
                "currency": "USD",
            }
        ]

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPositionsRequest(user_id="user123")
        response = await servicer.GetPositions(request, mock_context)

        assert response.user_id == "user123"
        assert len(response.positions) == 1
        assert response.positions[0].symbol == "AAPL"
        mock_redis.get.assert_called_once_with("user:user123:positions")

    @pytest.mark.asyncio
    async def test_get_positions_cache_miss(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should query database and cache on cache miss."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Setup cache miss
        mock_redis.get.return_value = None

        # Setup repository response
        mock_repository.get_position_domain_objects.return_value = [
            Position(
                symbol="GOOGL",
                quantity=50,
                avg_cost=Decimal("2500.00"),
                current_price=Decimal("2750.00"),
                current_value=Decimal("137500.00"),
                unrealized_pnl=Decimal("12500.00"),
                unrealized_pnl_percent=10.0,
                currency="USD",
            )
        ]

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPositionsRequest(user_id="user123")
        response = await servicer.GetPositions(request, mock_context)

        assert response.user_id == "user123"
        assert len(response.positions) == 1
        assert response.positions[0].symbol == "GOOGL"

        # Should cache result
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_positions_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPositionsRequest(user_id="")
        await servicer.GetPositions(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_positions_no_redis(
        self,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        mock_repository.get_position_domain_objects.return_value = []

        servicer = PortfolioServicer(
            redis_client=None,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.GetPositionsRequest(user_id="user123")
        response = await servicer.GetPositions(request, mock_context)

        assert response.user_id == "user123"
        assert len(response.positions) == 0


class TestServiceHelperFunctions:
    """Tests for service helper functions."""

    def test_decimal_to_money(self) -> None:
        """Should convert Decimal to Money proto."""
        from src.service import _decimal_to_money

        money = _decimal_to_money(Decimal("150.25"), "USD")
        assert money.amount == "150.25"
        assert money.currency == "USD"

    def test_position_to_proto(self) -> None:
        """Should convert Position domain object to proto."""
        from src.service import _position_to_proto

        position = Position(
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
            current_value=Decimal("17500.00"),
            unrealized_pnl=Decimal("2500.00"),
            unrealized_pnl_percent=16.67,
            currency="USD",
        )

        proto = _position_to_proto(position)

        assert proto.symbol == "AAPL"
        assert proto.quantity == 100
        assert proto.avg_cost.amount == "150.00"
        assert proto.current_price.amount == "175.00"
        assert proto.unrealized_pnl_percent == pytest.approx(16.67, rel=0.01)

    def test_portfolio_cache_roundtrip(self) -> None:
        """Should convert Portfolio to cache dict and back."""
        from src.service import _cache_dict_to_portfolio, _portfolio_to_cache_dict

        portfolio = Portfolio(
            user_id="user123",
            total_value=Decimal("100000.00"),
            cash_balance=Decimal("25000.00"),
            invested_value=Decimal("75000.00"),
            total_return=15.5,
            total_return_amount=Decimal("10000.00"),
            currency="USD",
            timestamp="2025-01-26T14:30:00Z",
        )

        cache_dict = _portfolio_to_cache_dict(portfolio)
        restored = _cache_dict_to_portfolio(cache_dict)

        assert restored.user_id == portfolio.user_id
        assert restored.total_value == portfolio.total_value
        assert restored.cash_balance == portfolio.cash_balance
        assert restored.total_return == portfolio.total_return

    def test_positions_cache_roundtrip(self) -> None:
        """Should convert positions to cache list and back."""
        from src.service import _cache_list_to_positions, _positions_to_cache_list

        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                current_price=Decimal("175.00"),
                current_value=Decimal("17500.00"),
                unrealized_pnl=Decimal("2500.00"),
                unrealized_pnl_percent=16.67,
                currency="USD",
            )
        ]

        cache_list = _positions_to_cache_list(positions)
        restored = _cache_list_to_positions(cache_list)

        assert len(restored) == 1
        assert restored[0].symbol == positions[0].symbol
        assert restored[0].quantity == positions[0].quantity
        assert restored[0].avg_cost == positions[0].avg_cost


class TestUpdateCashBalance:
    """Tests for UpdateCashBalance gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.engine = MagicMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository for database operations."""
        mock = AsyncMock()
        mock.update_cash_balance = AsyncMock(return_value=Decimal("50000.00"))
        mock.get_position_by_symbol = AsyncMock(return_value=None)
        mock.create_position = AsyncMock()
        mock.update_position = AsyncMock()
        mock.delete_position = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_update_cash_balance_set_operation(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should set cash balance to absolute value."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        mock_repository.update_cash_balance.return_value = Decimal("50000.00")

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdateCashBalanceRequest(
            user_id="user123",
            amount=Money(amount="50000.00", currency="USD"),
            operation="set",
        )
        response = await servicer.UpdateCashBalance(request, mock_context)

        assert response.success is True
        assert response.new_balance.amount == "50000.00"
        mock_repository.update_cash_balance.assert_called_once_with(
            "user123", Decimal("50000.00"), "set"
        )

    @pytest.mark.asyncio
    async def test_update_cash_balance_delta_operation(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should add to cash balance with delta operation."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        mock_repository.update_cash_balance.return_value = Decimal("15000.00")

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdateCashBalanceRequest(
            user_id="user123",
            amount=Money(amount="5000.00", currency="USD"),
            operation="delta",
        )
        response = await servicer.UpdateCashBalance(request, mock_context)

        assert response.success is True
        assert response.new_balance.amount == "15000.00"

    @pytest.mark.asyncio
    async def test_update_cash_balance_invalid_operation(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for invalid operation."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdateCashBalanceRequest(
            user_id="user123",
            amount=Money(amount="5000.00", currency="USD"),
            operation="invalid",
        )
        await servicer.UpdateCashBalance(request, mock_context)

        mock_context.set_code.assert_called()
        mock_context.set_details.assert_called()

    @pytest.mark.asyncio
    async def test_update_cash_balance_invalidates_cache(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should invalidate cache after updating cash balance."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdateCashBalanceRequest(
            user_id="user123",
            amount=Money(amount="50000.00", currency="USD"),
            operation="set",
        )
        await servicer.UpdateCashBalance(request, mock_context)

        # Should delete both portfolio and positions cache
        assert mock_redis.delete.call_count == 2
        mock_redis.delete.assert_any_call("user:user123:portfolio")
        mock_redis.delete.assert_any_call("user:user123:positions")

    @pytest.mark.asyncio
    async def test_update_cash_balance_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdateCashBalanceRequest(user_id="", operation="set")
        await servicer.UpdateCashBalance(request, mock_context)

        mock_context.set_code.assert_called()


class TestCreatePosition:
    """Tests for CreatePosition gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository."""
        from src.models import PositionRecord

        mock = AsyncMock()
        mock.get_position_by_symbol = AsyncMock(return_value=None)

        position_record = MagicMock(spec=PositionRecord)
        position_record.symbol = "AAPL"
        position_record.quantity = 100
        position_record.avg_cost = Decimal("150.00")
        position_record.current_price = Decimal("150.00")
        position_record.currency = "USD"
        mock.create_position = AsyncMock(return_value=position_record)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_create_position_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should create a new position successfully."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.CreatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity=100,
            cost_per_share=Money(amount="150.00", currency="USD"),
            currency="USD",
        )
        response = await servicer.CreatePosition(request, mock_context)

        assert response.success is True
        assert response.position.symbol == "AAPL"
        assert response.position.quantity == 100
        mock_repository.create_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_position_already_exists(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when position already exists."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.models import PositionRecord
        from src.service import PortfolioServicer

        # Position already exists
        existing_position = MagicMock(spec=PositionRecord)
        mock_repository.get_position_by_symbol.return_value = existing_position

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.CreatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity=100,
            cost_per_share=Money(amount="150.00", currency="USD"),
        )
        await servicer.CreatePosition(request, mock_context)

        mock_context.set_code.assert_called()
        mock_repository.create_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_position_invalid_quantity(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when quantity is invalid."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.CreatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity=0,
            cost_per_share=Money(amount="150.00", currency="USD"),
        )
        await servicer.CreatePosition(request, mock_context)

        mock_context.set_code.assert_called()
        mock_context.set_details.assert_called()

    @pytest.mark.asyncio
    async def test_create_position_invalidates_cache(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should invalidate cache after creating position."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.CreatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity=100,
            cost_per_share=Money(amount="150.00", currency="USD"),
        )
        await servicer.CreatePosition(request, mock_context)

        assert mock_redis.delete.call_count == 2


class TestUpdatePosition:
    """Tests for UpdatePosition gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository."""
        from src.models import PositionRecord

        mock = AsyncMock()

        # Existing position
        existing = MagicMock(spec=PositionRecord)
        existing.symbol = "AAPL"
        mock.get_position_by_symbol = AsyncMock(return_value=existing)

        # Updated position
        updated_position = MagicMock(spec=PositionRecord)
        updated_position.symbol = "AAPL"
        updated_position.quantity = 150
        updated_position.avg_cost = Decimal("160.00")
        updated_position.current_price = Decimal("185.00")
        updated_position.currency = "USD"
        mock.update_position = AsyncMock(return_value=updated_position)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_update_position_add_shares(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should add shares to existing position."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity_delta=50,
            cost_per_share=Money(amount="180.00", currency="USD"),
            current_price=Money(amount="185.00", currency="USD"),
        )
        response = await servicer.UpdatePosition(request, mock_context)

        assert response.success is True
        assert response.position.symbol == "AAPL"
        assert response.position.quantity == 150
        mock_repository.update_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_position_reduce_shares(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should reduce shares in existing position."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.models import PositionRecord
        from src.service import PortfolioServicer

        # Updated position after reduction
        updated_position = MagicMock(spec=PositionRecord)
        updated_position.symbol = "AAPL"
        updated_position.quantity = 70
        updated_position.avg_cost = Decimal("150.00")  # unchanged
        updated_position.current_price = Decimal("180.00")
        updated_position.currency = "USD"
        mock_repository.update_position.return_value = updated_position

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity_delta=-30,
            current_price=Money(amount="180.00", currency="USD"),
        )
        response = await servicer.UpdatePosition(request, mock_context)

        assert response.success is True
        assert response.position.quantity == 70

    @pytest.mark.asyncio
    async def test_update_position_not_found(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return NOT_FOUND when position doesn't exist."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        mock_repository.get_position_by_symbol.return_value = None

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdatePositionRequest(
            user_id="user123",
            symbol="NONEXISTENT",
            quantity_delta=50,
        )
        await servicer.UpdatePosition(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_update_position_invalidates_cache(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should invalidate cache after updating position."""
        from shared.generated import portfolio_pb2
        from shared.generated.common_pb2 import Money

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.UpdatePositionRequest(
            user_id="user123",
            symbol="AAPL",
            quantity_delta=50,
            cost_per_share=Money(amount="180.00", currency="USD"),
        )
        await servicer.UpdatePosition(request, mock_context)

        assert mock_redis.delete.call_count == 2


class TestDeletePosition:
    """Tests for DeletePosition gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository."""
        mock = AsyncMock()
        mock.delete_position = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_delete_position_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should delete position successfully."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.DeletePositionRequest(
            user_id="user123",
            symbol="AAPL",
        )
        response = await servicer.DeletePosition(request, mock_context)

        assert response.success is True
        mock_repository.delete_position.assert_called_once_with("user123", "AAPL")

    @pytest.mark.asyncio
    async def test_delete_position_not_found(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return NOT_FOUND when position doesn't exist."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        mock_repository.delete_position.return_value = False

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.DeletePositionRequest(
            user_id="user123",
            symbol="NONEXISTENT",
        )
        await servicer.DeletePosition(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_delete_position_invalidates_cache(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should invalidate cache after deleting position."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.DeletePositionRequest(
            user_id="user123",
            symbol="AAPL",
        )
        await servicer.DeletePosition(request, mock_context)

        assert mock_redis.delete.call_count == 2
        mock_redis.delete.assert_any_call("user:user123:portfolio")
        mock_redis.delete.assert_any_call("user:user123:positions")

    @pytest.mark.asyncio
    async def test_delete_position_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.DeletePositionRequest(user_id="", symbol="AAPL")
        await servicer.DeletePosition(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_delete_position_missing_symbol(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when symbol is missing."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = portfolio_pb2.DeletePositionRequest(user_id="user123", symbol="")
        await servicer.DeletePosition(request, mock_context)

        mock_context.set_code.assert_called()


class TestServicerErrors:
    """Test error handling in servicer."""

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_portfolio_exception(self, mock_context: MagicMock) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Create mock that raises exception
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=None,
        )

        request = portfolio_pb2.GetPortfolioRequest(user_id="user123")
        await servicer.GetPortfolio(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_positions_exception(self, mock_context: MagicMock) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import portfolio_pb2

        from src.service import PortfolioServicer

        # Create mock that raises exception
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=None,
        )

        request = portfolio_pb2.GetPositionsRequest(user_id="user123")
        await servicer.GetPositions(request, mock_context)

        mock_context.set_code.assert_called()


class TestMainModule:
    """Tests for main.py module."""

    @pytest.mark.asyncio
    async def test_serve_initializes_clients(self) -> None:
        """Should initialize all clients on serve."""
        import asyncio
        from unittest.mock import patch

        # Import the module first so patches work correctly
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "PostgresClient") as mock_postgres_cls,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "portfolio_pb2_grpc"),
        ):
            # Setup mocks
            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_postgres = AsyncMock()
            mock_postgres_cls.return_value = mock_postgres

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(side_effect=asyncio.CancelledError())
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer

            mock_health_pb2.HealthCheckResponse.SERVING = 1

            # Run serve (will be cancelled immediately)
            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            # Verify clients were initialized
            mock_redis.connect.assert_called_once()
            mock_postgres.connect.assert_called_once()

            # Verify gRPC server was started
            mock_grpc.aio.server.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health check was set up
            mock_health_servicer.set.assert_called()
