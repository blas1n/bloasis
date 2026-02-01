"""Unit tests for MarketDataRepository."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from src.repository import MarketDataRepository


class MockSessionContext:
    """Reusable async context manager for mocking postgres sessions."""

    def __init__(self, session: AsyncMock):
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *args) -> None:
        pass


class TestMarketDataRepository:
    """Tests for MarketDataRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock SQLAlchemy async session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_postgres(self, mock_session: AsyncMock) -> MagicMock:
        """Create a mock PostgresClient with session context manager."""
        mock = MagicMock()
        mock.get_session = MagicMock(return_value=MockSessionContext(mock_session))
        return mock

    @pytest.fixture
    def repository(self, mock_postgres: MagicMock) -> MarketDataRepository:
        """Create a repository with mocked PostgresClient."""
        return MarketDataRepository(mock_postgres)

    @pytest.mark.asyncio
    async def test_save_ohlcv_empty_dataframe(
        self, repository: MarketDataRepository
    ) -> None:
        """Test saving empty DataFrame returns 0."""
        df = pd.DataFrame()
        result = await repository.save_ohlcv("AAPL", "1d", df)
        assert result == 0

    @pytest.mark.asyncio
    async def test_save_ohlcv_with_data(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test saving OHLCV data."""
        df = pd.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [99.0, 100.0],
                "close": [104.0, 105.0],
                "volume": [1000000, 1100000],
                "adj_close": [104.0, 105.0],
            }
        )

        result = await repository.save_ohlcv("AAPL", "1d", df)
        assert result == 2
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_ohlcv_empty_result(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test retrieving OHLCV data when no data exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.get_ohlcv("AAPL", "1d")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @pytest.mark.asyncio
    async def test_get_ohlcv_with_data(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test retrieving OHLCV data."""
        mock_record = MagicMock()
        mock_record.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_record.symbol = "AAPL"
        mock_record.interval = "1d"
        mock_record.open = Decimal("100.00")
        mock_record.high = Decimal("105.00")
        mock_record.low = Decimal("99.00")
        mock_record.close = Decimal("104.00")
        mock_record.volume = 1000000
        mock_record.adj_close = Decimal("104.00")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record]
        mock_session.execute.return_value = mock_result

        result = await repository.get_ohlcv("AAPL", "1d")
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "AAPL"
        assert result.iloc[0]["close"] == 104.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_with_time_range(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test retrieving OHLCV data with time range filter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        await repository.get_ohlcv("AAPL", "1d", start_time=start, end_time=end)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_ohlcv_time_no_data(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting latest time when no data exists."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_latest_ohlcv_time("AAPL", "1d")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_ohlcv_time_with_data(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting latest time with existing data."""
        expected_time = datetime(2024, 1, 15, tzinfo=timezone.utc)
        mock_result = MagicMock()
        mock_result.scalar.return_value = expected_time
        mock_session.execute.return_value = mock_result

        result = await repository.get_latest_ohlcv_time("AAPL", "1d")
        assert result == expected_time

    @pytest.mark.asyncio
    async def test_save_stock_info(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test saving stock info."""
        info = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NASDAQ",
            "currency": "USD",
            "market_cap": 3000000000000,
            "pe_ratio": 28.5,
            "dividend_yield": 0.005,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 150.0,
        }

        result = await repository.save_stock_info("AAPL", info)
        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stock_info_not_found(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting stock info when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_stock_info("INVALID")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_stock_info_with_data(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting stock info with existing data."""
        mock_record = MagicMock()
        mock_record.symbol = "AAPL"
        mock_record.name = "Apple Inc."
        mock_record.sector = "Technology"
        mock_record.industry = "Consumer Electronics"
        mock_record.exchange = "NASDAQ"
        mock_record.currency = "USD"
        mock_record.market_cap = Decimal("3000000000000")
        mock_record.pe_ratio = Decimal("28.5")
        mock_record.dividend_yield = Decimal("0.005")
        mock_record.fifty_two_week_high = Decimal("200.0")
        mock_record.fifty_two_week_low = Decimal("150.0")
        mock_record.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute.return_value = mock_result

        result = await repository.get_stock_info("AAPL")
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"
        assert result["market_cap"] == 3000000000000.0

    @pytest.mark.asyncio
    async def test_get_symbols_by_sector(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting symbols by sector."""
        mock_result = MagicMock()
        mock_result.all.return_value = [("AAPL",), ("MSFT",), ("GOOGL",)]
        mock_session.execute.return_value = mock_result

        result = await repository.get_symbols_by_sector("Technology")
        assert result == ["AAPL", "MSFT", "GOOGL"]

    @pytest.mark.asyncio
    async def test_list_symbols_no_filter(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test listing symbols without filter."""
        # First call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 10

        # Second call: symbols query
        mock_symbols_result = MagicMock()
        mock_symbols_result.all.return_value = [("AAPL",), ("MSFT",)]

        mock_session.execute.side_effect = [mock_count_result, mock_symbols_result]

        symbols, total = await repository.list_symbols()
        assert symbols == ["AAPL", "MSFT"]
        assert total == 10

    @pytest.mark.asyncio
    async def test_list_symbols_with_sector_filter(
        self, repository: MarketDataRepository, mock_session: AsyncMock
    ) -> None:
        """Test listing symbols with sector filter."""
        # First call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        # Second call: symbols query
        mock_symbols_result = MagicMock()
        mock_symbols_result.all.return_value = [("AAPL",), ("MSFT",), ("GOOGL",)]

        mock_session.execute.side_effect = [mock_count_result, mock_symbols_result]

        symbols, total = await repository.list_symbols(sector="Technology", limit=50)
        assert symbols == ["AAPL", "MSFT", "GOOGL"]
        assert total == 5
