"""
Unit tests for PortfolioRepository.

Tests the repository layer with mocked PostgreSQL client.
"""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import PortfolioRecord, Position, PositionRecord
from src.repositories import PortfolioRepository


class TestPortfolioRepository:
    """Tests for PortfolioRepository."""

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client with ORM session support."""
        mock = MagicMock()
        mock.engine = MagicMock()

        # Create a mock session
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.merge = AsyncMock()

        # Create mock result for scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Create async context manager for get_session
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        mock.get_session = mock_get_session
        mock._session = mock_session  # Expose for test assertions
        mock._result = mock_result  # Expose for test assertions
        return mock

    @pytest.mark.asyncio
    async def test_get_portfolio_with_data(self, mock_postgres: MagicMock) -> None:
        """Should return portfolio record from database."""
        # Create mock portfolio record
        mock_record = MagicMock(spec=PortfolioRecord)
        mock_record.user_id = "user123"
        mock_record.cash_balance = Decimal("25000.00")
        mock_record.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_record

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_portfolio("user123")

        assert result is not None
        assert result.user_id == "user123"
        mock_postgres._session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_portfolio_not_found(self, mock_postgres: MagicMock) -> None:
        """Should return None when portfolio not found."""
        mock_postgres._result.scalar_one_or_none.return_value = None

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_portfolio("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_portfolio_without_postgres(self) -> None:
        """Should return None when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)
        result = await repository.get_portfolio("user123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_positions_with_data(self, mock_postgres: MagicMock) -> None:
        """Should return position records from database."""
        # Create mock position records
        mock_record1 = MagicMock(spec=PositionRecord)
        mock_record1.symbol = "AAPL"
        mock_record1.quantity = 100
        mock_record1.avg_cost = Decimal("150.00")
        mock_record1.current_price = Decimal("175.00")
        mock_record1.currency = "USD"

        mock_record2 = MagicMock(spec=PositionRecord)
        mock_record2.symbol = "GOOGL"
        mock_record2.quantity = 50
        mock_record2.avg_cost = Decimal("2500.00")
        mock_record2.current_price = Decimal("2750.00")
        mock_record2.currency = "USD"

        mock_postgres._result.scalars.return_value.all.return_value = [
            mock_record1,
            mock_record2,
        ]

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_positions("user123")

        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[1].symbol == "GOOGL"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, mock_postgres: MagicMock) -> None:
        """Should return empty list when no positions found."""
        mock_postgres._result.scalars.return_value.all.return_value = []

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_positions("user123")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_positions_without_postgres(self) -> None:
        """Should return empty list when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)
        result = await repository.get_positions("user123")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_full_portfolio(self, mock_postgres: MagicMock) -> None:
        """Should return full portfolio with calculated values."""
        # Create mock portfolio record
        mock_portfolio = MagicMock(spec=PortfolioRecord)
        mock_portfolio.user_id = "user123"
        mock_portfolio.cash_balance = Decimal("25000.00")
        mock_portfolio.currency = "USD"

        # Create mock position record
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.symbol = "AAPL"
        mock_position.quantity = 100
        mock_position.avg_cost = Decimal("150.00")
        mock_position.current_price = Decimal("175.00")
        mock_position.currency = "USD"

        # We need to handle two separate calls to get_session
        call_count = [0]
        results = [mock_portfolio, [mock_position]]

        @asynccontextmanager
        async def mock_get_session():
            mock_session = AsyncMock()
            mock_result = MagicMock()

            if call_count[0] == 0:
                mock_result.scalar_one_or_none.return_value = results[0]
            else:
                mock_result.scalars.return_value.all.return_value = results[1]

            mock_session.execute.return_value = mock_result
            call_count[0] += 1
            yield mock_session

        mock_postgres.get_session = mock_get_session

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_full_portfolio("user123", "2025-01-26T14:30:00Z")

        assert result.user_id == "user123"
        assert result.cash_balance == Decimal("25000.00")
        assert result.timestamp == "2025-01-26T14:30:00Z"

    @pytest.mark.asyncio
    async def test_get_position_domain_objects(self, mock_postgres: MagicMock) -> None:
        """Should return positions as domain objects."""
        # Create mock position record
        mock_record = MagicMock(spec=PositionRecord)
        mock_record.symbol = "AAPL"
        mock_record.quantity = 100
        mock_record.avg_cost = Decimal("150.00")
        mock_record.current_price = Decimal("175.00")
        mock_record.currency = "USD"

        mock_postgres._result.scalars.return_value.all.return_value = [mock_record]

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_position_domain_objects("user123")

        assert len(result) == 1
        assert isinstance(result[0], Position)
        assert result[0].symbol == "AAPL"
        assert result[0].current_value == Decimal("17500.00")

    @pytest.mark.asyncio
    async def test_save_portfolio(self, mock_postgres: MagicMock) -> None:
        """Should save portfolio record to database."""
        portfolio_record = MagicMock(spec=PortfolioRecord)
        portfolio_record.user_id = "user123"

        repository = PortfolioRepository(postgres_client=mock_postgres)
        await repository.save_portfolio(portfolio_record)

        mock_postgres._session.merge.assert_called_once_with(portfolio_record)

    @pytest.mark.asyncio
    async def test_save_portfolio_without_postgres(self) -> None:
        """Should not raise when postgres client is None."""
        portfolio_record = MagicMock(spec=PortfolioRecord)

        repository = PortfolioRepository(postgres_client=None)
        await repository.save_portfolio(portfolio_record)

    @pytest.mark.asyncio
    async def test_save_position(self, mock_postgres: MagicMock) -> None:
        """Should save position record to database."""
        position_record = MagicMock(spec=PositionRecord)
        position_record.symbol = "AAPL"

        repository = PortfolioRepository(postgres_client=mock_postgres)
        await repository.save_position(position_record)

        mock_postgres._session.merge.assert_called_once_with(position_record)

    @pytest.mark.asyncio
    async def test_save_position_without_postgres(self) -> None:
        """Should not raise when postgres client is None."""
        position_record = MagicMock(spec=PositionRecord)

        repository = PortfolioRepository(postgres_client=None)
        await repository.save_position(position_record)

    @pytest.mark.asyncio
    async def test_get_position_by_symbol(self, mock_postgres: MagicMock) -> None:
        """Should return position record by user_id and symbol."""
        # Create mock position record
        mock_record = MagicMock(spec=PositionRecord)
        mock_record.user_id = "user123"
        mock_record.symbol = "AAPL"
        mock_record.quantity = 100
        mock_record.avg_cost = Decimal("150.00")
        mock_record.current_price = Decimal("175.00")
        mock_record.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_record

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_position_by_symbol("user123", "AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.user_id == "user123"
        mock_postgres._session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_position_by_symbol_not_found(self, mock_postgres: MagicMock) -> None:
        """Should return None when position not found."""
        mock_postgres._result.scalar_one_or_none.return_value = None

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.get_position_by_symbol("user123", "NONEXISTENT")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_position_by_symbol_without_postgres(self) -> None:
        """Should return None when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)
        result = await repository.get_position_by_symbol("user123", "AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_cash_balance_set(self, mock_postgres: MagicMock) -> None:
        """Should set cash balance to absolute value."""
        # Create mock portfolio record
        mock_portfolio = MagicMock(spec=PortfolioRecord)
        mock_portfolio.user_id = "user123"
        mock_portfolio.cash_balance = Decimal("10000.00")
        mock_portfolio.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_portfolio

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_cash_balance("user123", Decimal("50000.00"), "set")

        assert result == Decimal("50000.00")
        assert mock_portfolio.cash_balance == Decimal("50000.00")
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cash_balance_delta(self, mock_postgres: MagicMock) -> None:
        """Should add/subtract from current cash balance."""
        # Create mock portfolio record
        mock_portfolio = MagicMock(spec=PortfolioRecord)
        mock_portfolio.user_id = "user123"
        mock_portfolio.cash_balance = Decimal("10000.00")
        mock_portfolio.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_portfolio

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_cash_balance("user123", Decimal("5000.00"), "delta")

        assert result == Decimal("15000.00")
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cash_balance_delta_negative(self, mock_postgres: MagicMock) -> None:
        """Should subtract from current cash balance with negative delta."""
        # Create mock portfolio record
        mock_portfolio = MagicMock(spec=PortfolioRecord)
        mock_portfolio.user_id = "user123"
        mock_portfolio.cash_balance = Decimal("10000.00")
        mock_portfolio.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_portfolio

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_cash_balance("user123", Decimal("-3000.00"), "delta")

        assert result == Decimal("7000.00")

    @pytest.mark.asyncio
    async def test_update_cash_balance_creates_portfolio(self, mock_postgres: MagicMock) -> None:
        """Should create new portfolio if not exists."""
        mock_postgres._result.scalar_one_or_none.return_value = None

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_cash_balance("newuser", Decimal("25000.00"), "set")

        assert result == Decimal("25000.00")
        mock_postgres._session.add.assert_called_once()
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cash_balance_invalid_operation(self, mock_postgres: MagicMock) -> None:
        """Should raise ValueError for invalid operation."""
        mock_portfolio = MagicMock(spec=PortfolioRecord)
        mock_portfolio.cash_balance = Decimal("10000.00")
        mock_postgres._result.scalar_one_or_none.return_value = mock_portfolio

        repository = PortfolioRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="Invalid operation"):
            await repository.update_cash_balance("user123", Decimal("5000.00"), "invalid")

    @pytest.mark.asyncio
    async def test_update_cash_balance_without_postgres(self) -> None:
        """Should raise ValueError when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.update_cash_balance("user123", Decimal("5000.00"), "set")

    @pytest.mark.asyncio
    async def test_create_position(self, mock_postgres: MagicMock) -> None:
        """Should create a new position in the database."""
        # Setup mock to return the created position
        created_position = MagicMock(spec=PositionRecord)
        created_position.user_id = "user123"
        created_position.symbol = "AAPL"
        created_position.quantity = 100
        created_position.avg_cost = Decimal("150.00")
        created_position.current_price = Decimal("150.00")
        created_position.currency = "USD"

        mock_postgres._session.refresh = AsyncMock()

        repository = PortfolioRepository(postgres_client=mock_postgres)

        # Patch the PositionRecord class to return our mock
        with patch("src.repositories.portfolio_repository.PositionRecord") as mock_position_cls:
            mock_position_cls.return_value = created_position

            result = await repository.create_position(
                user_id="user123",
                symbol="AAPL",
                quantity=100,
                cost_per_share=Decimal("150.00"),
                currency="USD",
            )

        assert result.symbol == "AAPL"
        assert result.quantity == 100
        mock_postgres._session.add.assert_called_once()
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_position_without_postgres(self) -> None:
        """Should raise ValueError when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.create_position(
                user_id="user123",
                symbol="AAPL",
                quantity=100,
                cost_per_share=Decimal("150.00"),
            )

    @pytest.mark.asyncio
    async def test_update_position_add_shares(self, mock_postgres: MagicMock) -> None:
        """Should add shares and recalculate avg_cost."""
        # Create mock position record
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.user_id = "user123"
        mock_position.symbol = "AAPL"
        mock_position.quantity = 100
        mock_position.avg_cost = Decimal("150.00")
        mock_position.current_price = Decimal("175.00")
        mock_position.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_position
        mock_postgres._session.refresh = AsyncMock()

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_position(
            user_id="user123",
            symbol="AAPL",
            quantity_delta=50,
            cost_per_share=Decimal("180.00"),
            current_price=Decimal("185.00"),
        )

        assert result is not None
        assert result.quantity == 150
        # New avg_cost = ((100 * 150) + (50 * 180)) / 150 = 24000 / 150 = 160
        expected_avg_cost = Decimal("160.00")
        assert result.avg_cost == expected_avg_cost
        assert result.current_price == Decimal("185.00")
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_position_reduce_shares(self, mock_postgres: MagicMock) -> None:
        """Should reduce shares without changing avg_cost."""
        # Create mock position record
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.user_id = "user123"
        mock_position.symbol = "AAPL"
        mock_position.quantity = 100
        mock_position.avg_cost = Decimal("150.00")
        mock_position.current_price = Decimal("175.00")
        mock_position.currency = "USD"

        mock_postgres._result.scalar_one_or_none.return_value = mock_position
        mock_postgres._session.refresh = AsyncMock()

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_position(
            user_id="user123",
            symbol="AAPL",
            quantity_delta=-30,
            current_price=Decimal("180.00"),
        )

        assert result is not None
        assert result.quantity == 70
        # avg_cost should remain unchanged when reducing shares
        assert result.avg_cost == Decimal("150.00")
        assert result.current_price == Decimal("180.00")

    @pytest.mark.asyncio
    async def test_update_position_not_found(self, mock_postgres: MagicMock) -> None:
        """Should return None when position not found."""
        mock_postgres._result.scalar_one_or_none.return_value = None

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.update_position(
            user_id="user123",
            symbol="NONEXISTENT",
            quantity_delta=50,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_position_negative_quantity_error(self, mock_postgres: MagicMock) -> None:
        """Should raise ValueError when reducing below 0."""
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.quantity = 50
        mock_position.avg_cost = Decimal("150.00")

        mock_postgres._result.scalar_one_or_none.return_value = mock_position

        repository = PortfolioRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="Cannot reduce position below 0"):
            await repository.update_position(
                user_id="user123",
                symbol="AAPL",
                quantity_delta=-100,
            )

    @pytest.mark.asyncio
    async def test_update_position_add_without_cost_error(self, mock_postgres: MagicMock) -> None:
        """Should raise ValueError when adding shares without cost_per_share."""
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.quantity = 100
        mock_position.avg_cost = Decimal("150.00")

        mock_postgres._result.scalar_one_or_none.return_value = mock_position

        repository = PortfolioRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="cost_per_share is required"):
            await repository.update_position(
                user_id="user123",
                symbol="AAPL",
                quantity_delta=50,
            )

    @pytest.mark.asyncio
    async def test_update_position_without_postgres(self) -> None:
        """Should raise ValueError when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.update_position(
                user_id="user123",
                symbol="AAPL",
                quantity_delta=50,
            )

    @pytest.mark.asyncio
    async def test_delete_position(self, mock_postgres: MagicMock) -> None:
        """Should delete position and return True."""
        mock_position = MagicMock(spec=PositionRecord)
        mock_position.symbol = "AAPL"

        mock_postgres._result.scalar_one_or_none.return_value = mock_position
        mock_postgres._session.delete = AsyncMock()

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.delete_position("user123", "AAPL")

        assert result is True
        mock_postgres._session.delete.assert_called_once_with(mock_position)
        mock_postgres._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_position_not_found(self, mock_postgres: MagicMock) -> None:
        """Should return False when position not found."""
        mock_postgres._result.scalar_one_or_none.return_value = None

        repository = PortfolioRepository(postgres_client=mock_postgres)
        result = await repository.delete_position("user123", "NONEXISTENT")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_position_without_postgres(self) -> None:
        """Should raise ValueError when postgres client is None."""
        repository = PortfolioRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.delete_position("user123", "AAPL")
