"""
Integration tests for Portfolio Service.

Tests gRPC service interaction with mocked infrastructure.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import Portfolio, Position


class TestPortfolioServiceIntegration:
    """Integration tests for Portfolio Service gRPC endpoints."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> AsyncMock:
        """Create mock PostgreSQL client."""
        mock = AsyncMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.engine = MagicMock()
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_full_portfolio_workflow(
        self,
        mock_redis: AsyncMock,
        mock_postgres: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test complete portfolio retrieval workflow."""
        from shared.generated import portfolio_pb2

        from src.repositories import PortfolioRepository
        from src.service import PortfolioServicer

        # Create mock repository
        mock_repository = AsyncMock(spec=PortfolioRepository)
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

        # Create servicer
        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        # First request - cache miss
        request = portfolio_pb2.GetPortfolioRequest(user_id="user123")
        response = await servicer.GetPortfolio(request, mock_context)

        assert response.user_id == "user123"
        assert response.total_value.amount == "100000.00"
        assert response.total_value.currency == "USD"
        mock_redis.setex.assert_called_once()

        # Simulate cache hit for second request
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

        # Second request - cache hit
        response2 = await servicer.GetPortfolio(request, mock_context)
        assert response2.user_id == "user123"

        # Repository should not be called again
        assert mock_repository.get_full_portfolio.call_count == 1

    @pytest.mark.asyncio
    async def test_full_positions_workflow(
        self,
        mock_redis: AsyncMock,
        mock_postgres: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test complete positions retrieval workflow."""
        from shared.generated import portfolio_pb2

        from src.repositories import PortfolioRepository
        from src.service import PortfolioServicer

        # Create mock repository
        mock_repository = AsyncMock(spec=PortfolioRepository)
        mock_repository.get_position_domain_objects.return_value = [
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

        # Create servicer
        servicer = PortfolioServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        # Request positions
        request = portfolio_pb2.GetPositionsRequest(user_id="user123")
        response = await servicer.GetPositions(request, mock_context)

        assert response.user_id == "user123"
        assert len(response.positions) == 2

        # Verify first position
        aapl = response.positions[0]
        assert aapl.symbol == "AAPL"
        assert aapl.quantity == 100
        assert aapl.avg_cost.amount == "150.00"
        assert aapl.current_price.amount == "175.00"
        assert aapl.unrealized_pnl.amount == "2500.00"

        # Verify second position
        googl = response.positions[1]
        assert googl.symbol == "GOOGL"
        assert googl.quantity == 50

        # Verify caching
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_startup_and_shutdown(self) -> None:
        """Test service lifecycle with mocked clients."""
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

            # Verify startup
            mock_redis.connect.assert_called_once()
            mock_postgres.connect.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health service registered
            assert mock_health_servicer.set.call_count >= 2


class TestDecimalPrecision:
    """Tests to verify Decimal precision in financial calculations."""

    def test_position_calculation_precision(self) -> None:
        """Verify no floating point errors in position calculations."""
        from src.models import PositionRecord

        # Use values that would cause floating point errors
        mock_record = MagicMock(spec=PositionRecord)
        mock_record.symbol = "TEST"
        mock_record.quantity = 3
        mock_record.avg_cost = Decimal("0.1")  # 0.1 + 0.1 + 0.1 = 0.3 exactly
        mock_record.current_price = Decimal("0.3")
        mock_record.currency = "USD"

        position = Position.from_record(mock_record)

        # With Decimal, 0.1 * 3 = 0.3 exactly
        assert position.current_value == Decimal("0.9")
        # PnL should be exactly (0.3 - 0.1) * 3 = 0.6
        assert position.unrealized_pnl == Decimal("0.6")

    def test_portfolio_calculation_precision(self) -> None:
        """Verify no floating point errors in portfolio totals."""
        from src.models import PortfolioRecord

        mock_portfolio_record = MagicMock(spec=PortfolioRecord)
        mock_portfolio_record.user_id = "user123"
        mock_portfolio_record.cash_balance = Decimal("0.1")
        mock_portfolio_record.currency = "USD"

        positions = [
            Position(
                symbol="A",
                quantity=1,
                avg_cost=Decimal("0.1"),
                current_price=Decimal("0.2"),
                current_value=Decimal("0.2"),
                unrealized_pnl=Decimal("0.1"),
                unrealized_pnl_percent=100.0,
                currency="USD",
            ),
            Position(
                symbol="B",
                quantity=1,
                avg_cost=Decimal("0.2"),
                current_price=Decimal("0.3"),
                current_value=Decimal("0.3"),
                unrealized_pnl=Decimal("0.1"),
                unrealized_pnl_percent=50.0,
                currency="USD",
            ),
        ]

        portfolio = Portfolio.from_records(mock_portfolio_record, positions, "2025-01-26T14:30:00Z")

        # With Decimal: 0.2 + 0.3 = 0.5 exactly
        assert portfolio.invested_value == Decimal("0.5")
        # Total: 0.1 + 0.5 = 0.6 exactly
        assert portfolio.total_value == Decimal("0.6")
        # Total return: 0.1 + 0.1 = 0.2 exactly
        assert portfolio.total_return_amount == Decimal("0.2")
