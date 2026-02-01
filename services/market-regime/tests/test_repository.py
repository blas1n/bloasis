"""
Unit tests for MarketRegimeRepository.

Tests the repository layer with mocked PostgreSQL client.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import MarketRegimeRecord, RegimeData
from src.repositories import MarketRegimeRepository


class TestMarketRegimeRepository:
    """Tests for MarketRegimeRepository."""

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

        # Create mock result for scalars().all()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Create async context manager for get_session
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        mock.get_session = mock_get_session
        mock._session = mock_session  # Expose for test assertions
        return mock

    @pytest.mark.asyncio
    async def test_save_with_postgres_client(self, mock_postgres: MagicMock) -> None:
        """Should save regime data to database."""
        repository = MarketRegimeRepository(postgres_client=mock_postgres)

        regime_data = RegimeData(
            regime="bull",
            confidence=0.92,
            timestamp="2025-01-26T14:30:00Z",
            trigger="baseline",
        )
        timestamp = datetime(2025, 1, 26, 14, 30, 0, tzinfo=timezone.utc)

        await repository.save(regime_data, timestamp)

        # Verify session.add was called with a MarketRegimeRecord
        mock_postgres._session.add.assert_called_once()
        added_record = mock_postgres._session.add.call_args[0][0]
        assert added_record.regime == "bull"
        assert added_record.confidence == 0.92
        assert added_record.trigger == "baseline"

    @pytest.mark.asyncio
    async def test_save_without_postgres_client(self) -> None:
        """Should not raise when postgres client is None."""
        repository = MarketRegimeRepository(postgres_client=None)

        regime_data = RegimeData(
            regime="bull",
            confidence=0.92,
            timestamp="2025-01-26T14:30:00Z",
            trigger="baseline",
        )
        timestamp = datetime(2025, 1, 26, 14, 30, 0, tzinfo=timezone.utc)

        # Should not raise
        await repository.save(regime_data, timestamp)

    @pytest.mark.asyncio
    async def test_get_history_with_postgres_client(
        self, mock_postgres: MagicMock
    ) -> None:
        """Should return regime history from database."""
        # Create mock ORM records
        mock_record1 = MagicMock(spec=MarketRegimeRecord)
        mock_record1.regime = "bull"
        mock_record1.confidence = 0.9
        mock_record1.timestamp = datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
        mock_record1.trigger = "baseline"

        mock_record2 = MagicMock(spec=MarketRegimeRecord)
        mock_record2.regime = "crisis"
        mock_record2.confidence = 0.95
        mock_record2.timestamp = datetime(2025, 1, 26, 10, 0, 0, tzinfo=timezone.utc)
        mock_record2.trigger = "circuit_breaker"

        # Setup mock session to return ORM records
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_record1, mock_record2]
        mock_postgres._session.execute.return_value = mock_result

        repository = MarketRegimeRepository(postgres_client=mock_postgres)

        start_time = datetime(2025, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 26, 23, 59, 59, tzinfo=timezone.utc)

        records = await repository.get_history(start_time, end_time)

        assert len(records) == 2
        assert records[0].regime == "bull"
        assert records[1].regime == "crisis"
        mock_postgres._session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_history_without_postgres_client(self) -> None:
        """Should return empty list when postgres client is None."""
        repository = MarketRegimeRepository(postgres_client=None)

        start_time = datetime(2025, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 26, 23, 59, 59, tzinfo=timezone.utc)

        records = await repository.get_history(start_time, end_time)

        assert records == []

    @pytest.mark.asyncio
    async def test_get_history_empty_result(self, mock_postgres: MagicMock) -> None:
        """Should return empty list when no records found."""
        # Setup mock session to return empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_postgres._session.execute.return_value = mock_result

        repository = MarketRegimeRepository(postgres_client=mock_postgres)

        start_time = datetime(2025, 1, 25, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 26, 23, 59, 59, tzinfo=timezone.utc)

        records = await repository.get_history(start_time, end_time)

        assert records == []
