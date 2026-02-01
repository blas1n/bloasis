"""
Integration tests for Market Regime Service.

These tests verify the service works correctly with mocked external dependencies.
For full integration tests with real services, use docker-compose.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestServiceIntegration:
    """Integration tests for MarketRegimeServicer with all components."""

    @pytest.fixture
    def mock_clients(self) -> tuple[AsyncMock, AsyncMock, MagicMock]:
        """Create all mock clients with ORM session support."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        redis.client = MagicMock()

        redpanda = AsyncMock()
        redpanda.publish = AsyncMock()
        redpanda.producer = MagicMock()

        postgres = MagicMock()
        postgres.engine = MagicMock()

        # Create a mock session for ORM operations
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

        postgres.get_session = mock_get_session
        postgres._session = mock_session  # Expose for test assertions

        return redis, redpanda, postgres

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_full_classification_flow(
        self,
        mock_clients: tuple[AsyncMock, AsyncMock, MagicMock],
        mock_context: MagicMock,
    ) -> None:
        """Test complete flow: classify -> cache -> publish -> persist."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        redis, redpanda, postgres = mock_clients

        servicer = MarketRegimeServicer(
            redis_client=redis,
            redpanda_client=redpanda,
            postgres_client=postgres,
        )

        # Make request
        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        # Verify classification (rule-based fallback with default VIX=20)
        assert response.regime == "sideways"
        assert response.confidence == 0.65

        # Verify cache was set
        redis.setex.assert_called_once()

        # Verify event was published (topic changed to regime-events)
        redpanda.publish.assert_called_once()
        publish_call = redpanda.publish.call_args
        assert publish_call[0][0] == "regime-events"
        assert publish_call[0][1]["event_type"] == "regime_classified"

        # Verify database insert via ORM session.add
        postgres._session.add.assert_called_once()
        added_record = postgres._session.add.call_args[0][0]
        assert added_record.regime == "sideways"

    @pytest.mark.asyncio
    async def test_cache_and_refresh_cycle(
        self,
        mock_clients: tuple[AsyncMock, AsyncMock, MagicMock],
        mock_context: MagicMock,
    ) -> None:
        """Test cache hit followed by force refresh."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        redis, redpanda, postgres = mock_clients

        servicer = MarketRegimeServicer(
            redis_client=redis,
            redpanda_client=redpanda,
            postgres_client=postgres,
        )

        # First request - cache miss
        request1 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        await servicer.GetCurrentRegime(request1, mock_context)

        # Second request - simulate cache hit
        redis.get.return_value = {
            "regime": "bull",
            "confidence": 0.92,
            "timestamp": "2025-01-26T14:30:00Z",
            "trigger": "baseline",
        }

        request2 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response2 = await servicer.GetCurrentRegime(request2, mock_context)

        # Should use cached data
        assert response2.regime == "bull"
        # Cache set should only be called once (from first request)
        assert redis.setex.call_count == 1

        # Third request - force refresh
        redis.setex.reset_mock()
        redpanda.publish.reset_mock()

        request3 = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=True)
        await servicer.GetCurrentRegime(request3, mock_context)

        # Should update cache even though it exists
        redis.setex.assert_called_once()
        redpanda.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_query_with_results(
        self,
        mock_clients: tuple[AsyncMock, AsyncMock, MagicMock],
        mock_context: MagicMock,
    ) -> None:
        """Test history query returns properly formatted data using ORM."""
        from shared.generated import market_regime_pb2
        from shared.generated.common_pb2 import TimeRange

        from src.models import MarketRegimeRecord
        from src.service import MarketRegimeServicer

        redis, redpanda, postgres = mock_clients

        # Create mock ORM records
        mock_record1 = MagicMock(spec=MarketRegimeRecord)
        mock_record1.regime = "bull"
        mock_record1.confidence = 0.85
        mock_record1.timestamp = datetime(2025, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
        mock_record1.trigger = "baseline"

        mock_record2 = MagicMock(spec=MarketRegimeRecord)
        mock_record2.regime = "crisis"
        mock_record2.confidence = 0.78
        mock_record2.timestamp = datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
        mock_record2.trigger = "fomc"

        mock_record3 = MagicMock(spec=MarketRegimeRecord)
        mock_record3.regime = "crisis"
        mock_record3.confidence = 0.95
        mock_record3.timestamp = datetime(2025, 1, 26, 10, 0, 0, tzinfo=timezone.utc)
        mock_record3.trigger = "circuit_breaker"

        # Setup mock session to return ORM records
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_record1, mock_record2, mock_record3
        ]
        postgres._session.execute.return_value = mock_result

        servicer = MarketRegimeServicer(
            redis_client=redis,
            redpanda_client=redpanda,
            postgres_client=postgres,
        )

        time_range = TimeRange(
            start_date="2025-01-24T00:00:00Z",
            end_date="2025-01-26T23:59:59Z",
        )
        request = market_regime_pb2.GetRegimeHistoryRequest(time_range=time_range)
        response = await servicer.GetRegimeHistory(request, mock_context)

        assert len(response.regimes) == 3
        assert response.regimes[0].regime == "bull"
        assert response.regimes[1].regime == "crisis"
        assert response.regimes[2].regime == "crisis"

        # Verify session.execute was called
        postgres._session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_redis(
        self,
        mock_clients: tuple[AsyncMock, AsyncMock, MagicMock],
        mock_context: MagicMock,
    ) -> None:
        """Test service works without Redis (no caching)."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        _, redpanda, postgres = mock_clients

        servicer = MarketRegimeServicer(
            redis_client=None,  # No Redis
            redpanda_client=redpanda,
            postgres_client=postgres,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        # Should still work (rule-based fallback)
        assert response.regime == "sideways"
        # Event should still be published
        redpanda.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_redpanda(
        self,
        mock_clients: tuple[AsyncMock, AsyncMock, MagicMock],
        mock_context: MagicMock,
    ) -> None:
        """Test service works without Redpanda (no events)."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        redis, _, postgres = mock_clients

        servicer = MarketRegimeServicer(
            redis_client=redis,
            redpanda_client=None,  # No Redpanda
            postgres_client=postgres,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        # Should still work (rule-based fallback)
        assert response.regime == "sideways"
        # Cache should still be set
        redis.setex.assert_called_once()
