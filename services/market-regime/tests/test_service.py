"""
Unit tests for Market Regime Service.

All external dependencies (Redis, Redpanda, PostgreSQL, FinGPT) are mocked.
Target: 80%+ code coverage.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRegimeData:
    """Tests for RegimeData dataclass."""

    def test_regime_data_creation(self) -> None:
        """Should create RegimeData with all fields."""
        from src.models import RegimeData

        data = RegimeData(
            regime="normal_bull",
            confidence=0.92,
            timestamp="2025-01-26T14:30:00Z",
            trigger="baseline",
        )
        assert data.regime == "normal_bull"
        assert data.confidence == 0.92
        assert data.timestamp == "2025-01-26T14:30:00Z"
        assert data.trigger == "baseline"


class TestRegimeClassifier:
    """Tests for RegimeClassifier."""

    @pytest.mark.asyncio
    async def test_classify_with_fingpt_success(self) -> None:
        """Should use FinGPT result when available."""
        from src.models import RegimeClassifier

        mock_fingpt = AsyncMock()
        mock_fingpt.analyze.return_value = {
            "regime": "crisis",
            "confidence": 0.95,
            "trigger": "circuit_breaker",
        }

        classifier = RegimeClassifier(fingpt_client=mock_fingpt)
        result = await classifier.classify()

        assert result.regime == "crisis"
        assert result.confidence == 0.95
        assert result.trigger == "circuit_breaker"
        mock_fingpt.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_classify_fingpt_failure_fallback(self) -> None:
        """Should fall back to mock data when FinGPT fails."""
        from src.models import RegimeClassifier

        mock_fingpt = AsyncMock()
        mock_fingpt.analyze.side_effect = Exception("API error")

        classifier = RegimeClassifier(fingpt_client=mock_fingpt)
        result = await classifier.classify()

        # Fallback values
        assert result.regime == "normal_bull"
        assert result.confidence == 0.92
        assert result.trigger == "baseline"

    @pytest.mark.asyncio
    async def test_classify_fingpt_invalid_response(self) -> None:
        """Should fall back when FinGPT returns invalid data."""
        from src.models import RegimeClassifier

        mock_fingpt = AsyncMock()
        mock_fingpt.analyze.return_value = {}  # Missing 'regime' key

        classifier = RegimeClassifier(fingpt_client=mock_fingpt)
        result = await classifier.classify()

        # Fallback values
        assert result.regime == "normal_bull"

    @pytest.mark.asyncio
    async def test_classify_timestamp_format(self) -> None:
        """Should return ISO 8601 formatted timestamp."""
        from src.models import RegimeClassifier

        mock_fingpt = AsyncMock()
        mock_fingpt.analyze.return_value = {
            "regime": "normal_bull",
            "confidence": 0.9,
            "trigger": "baseline",
        }

        classifier = RegimeClassifier(fingpt_client=mock_fingpt)
        result = await classifier.classify()

        # Verify timestamp is valid ISO 8601
        assert "T" in result.timestamp
        assert result.timestamp.endswith("+00:00") or result.timestamp.endswith("Z")


class TestFinGPTClient:
    """Tests for FinGPTClient."""

    def test_init_without_api_key(self) -> None:
        """Should initialize without API key (will use mock data)."""
        import os

        from src.clients.fingpt_client import FinGPTClient

        with patch.dict(os.environ, {}, clear=True):
            client = FinGPTClient()
            assert client.api_key is None

    def test_init_with_api_key_env(self) -> None:
        """Should read API key from environment."""
        import os

        from src.clients.fingpt_client import FinGPTClient

        with patch.dict(os.environ, {"FINGPT_API_KEY": "test-key"}):
            client = FinGPTClient()
            assert client.api_key == "test-key"

    def test_init_with_explicit_api_key(self) -> None:
        """Should use explicit API key over env var."""
        import os

        from src.clients.fingpt_client import FinGPTClient

        with patch.dict(os.environ, {"FINGPT_API_KEY": "env-key"}):
            client = FinGPTClient(api_key="explicit-key")
            assert client.api_key == "explicit-key"

    @pytest.mark.asyncio
    async def test_analyze_returns_mock_data(self) -> None:
        """Should return mock data when API is not configured."""
        from src.clients.fingpt_client import FinGPTClient

        client = FinGPTClient()
        result = await client.analyze()

        assert "regime" in result
        assert "confidence" in result
        assert "trigger" in result
        assert result["regime"] == "normal_bull"

    @pytest.mark.asyncio
    async def test_analyze_sentiment_returns_mock_data(self) -> None:
        """Should return mock sentiment data."""
        from src.clients.fingpt_client import FinGPTClient

        client = FinGPTClient()
        result = await client.analyze_sentiment(["AAPL", "GOOGL"])

        assert "symbols" in result
        assert "AAPL" in result["symbols"]
        assert "GOOGL" in result["symbols"]

    @pytest.mark.asyncio
    async def test_health_check_without_api_key(self) -> None:
        """Should return False when API key is not set."""
        import os

        from src.clients.fingpt_client import FinGPTClient

        with patch.dict(os.environ, {}, clear=True):
            client = FinGPTClient()
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_with_api_key(self) -> None:
        """Should return True when API key is set."""
        from src.clients.fingpt_client import FinGPTClient

        client = FinGPTClient(api_key="test-key")
        result = await client.health_check()
        assert result is True


class TestMarketRegimeServicer:
    """Tests for MarketRegimeServicer gRPC implementation."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_redpanda(self) -> AsyncMock:
        """Create mock Redpanda client."""
        mock = AsyncMock()
        mock.publish = AsyncMock()
        mock.producer = MagicMock()
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
        mock.save = AsyncMock()
        mock.get_history = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_current_regime_cache_hit(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return cached regime data on cache hit."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        # Setup cache hit
        mock_redis.get.return_value = {
            "regime": "crisis",
            "confidence": 0.95,
            "timestamp": "2025-01-26T14:30:00Z",
            "trigger": "circuit_breaker",
        }

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        assert response.regime == "crisis"
        assert response.confidence == 0.95
        mock_redis.get.assert_called_once_with("market:regime:current")
        # Should not call classifier on cache hit
        mock_redpanda.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_current_regime_cache_miss(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should classify and cache on cache miss."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        # Setup cache miss
        mock_redis.get.return_value = None

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        # Should return classified data
        assert response.regime == "normal_bull"  # Mock fallback
        assert response.confidence == 0.92

        # Should cache result
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "market:regime:current"
        assert call_args[0][1] == 21600  # 6 hours

        # Should publish event
        mock_redpanda.publish.assert_called_once()

        # Should persist via repository
        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_regime_force_refresh(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should bypass cache when force_refresh is true."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        # Setup cache data (should be ignored)
        mock_redis.get.return_value = {
            "regime": "crisis",
            "confidence": 0.95,
            "timestamp": "2025-01-26T14:30:00Z",
            "trigger": "circuit_breaker",
        }

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=True)
        response = await servicer.GetCurrentRegime(request, mock_context)

        # Should return fresh classification, not cached
        assert response.regime == "normal_bull"  # Mock fallback
        # Cache should not be read
        mock_redis.get.assert_not_called()
        # Should update cache
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_regime_no_redis(
        self, mock_redpanda: AsyncMock, mock_postgres: MagicMock,
        mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=None,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        response = await servicer.GetCurrentRegime(request, mock_context)

        assert response.regime == "normal_bull"

    @pytest.mark.asyncio
    async def test_get_regime_history_success(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return historical regime data using Repository."""
        from shared.generated import market_regime_pb2
        from shared.generated.common_pb2 import TimeRange

        from src.models import MarketRegimeRecord
        from src.service import MarketRegimeServicer

        # Create mock ORM records
        mock_record1 = MagicMock(spec=MarketRegimeRecord)
        mock_record1.regime = "normal_bull"
        mock_record1.confidence = 0.9
        mock_record1.timestamp = datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
        mock_record1.trigger = "baseline"

        mock_record2 = MagicMock(spec=MarketRegimeRecord)
        mock_record2.regime = "crisis"
        mock_record2.confidence = 0.95
        mock_record2.timestamp = datetime(2025, 1, 26, 10, 0, 0, tzinfo=timezone.utc)
        mock_record2.trigger = "circuit_breaker"

        # Setup mock repository to return ORM records
        mock_repository.get_history.return_value = [mock_record1, mock_record2]

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        time_range = TimeRange(
            start_date="2025-01-25T00:00:00Z",
            end_date="2025-01-26T23:59:59Z",
        )
        request = market_regime_pb2.GetRegimeHistoryRequest(time_range=time_range)
        response = await servicer.GetRegimeHistory(request, mock_context)

        assert len(response.regimes) == 2
        assert response.regimes[0].regime == "normal_bull"
        assert response.regimes[1].regime == "crisis"
        mock_repository.get_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_regime_history_no_postgres(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error when PostgreSQL is not available."""
        from shared.generated import market_regime_pb2
        from shared.generated.common_pb2 import TimeRange

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=None,
            repository=mock_repository,
        )

        time_range = TimeRange(
            start_date="2025-01-25T00:00:00Z",
            end_date="2025-01-26T23:59:59Z",
        )
        request = market_regime_pb2.GetRegimeHistoryRequest(time_range=time_range)
        response = await servicer.GetRegimeHistory(request, mock_context)

        # Should set error code
        mock_context.set_code.assert_called()
        assert len(response.regimes) == 0

    @pytest.mark.asyncio
    async def test_get_regime_history_missing_time_range(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error when time_range is missing dates."""
        from shared.generated import market_regime_pb2
        from shared.generated.common_pb2 import TimeRange

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        # Empty time range
        time_range = TimeRange(start_date="", end_date="")
        request = market_regime_pb2.GetRegimeHistoryRequest(time_range=time_range)
        response = await servicer.GetRegimeHistory(request, mock_context)

        # Should set INVALID_ARGUMENT error
        mock_context.set_code.assert_called()
        assert len(response.regimes) == 0

    @pytest.mark.asyncio
    async def test_persist_regime_success(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should persist regime data to database using Repository."""
        from src.models import RegimeData
        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        regime_data = RegimeData(
            regime="normal_bull",
            confidence=0.92,
            timestamp="2025-01-26T14:30:00Z",
            trigger="baseline",
        )

        await servicer._persist_regime(regime_data)

        # Verify repository.save was called with correct data
        mock_repository.save.assert_called_once()
        call_args = mock_repository.save.call_args[0]
        assert call_args[0].regime == "normal_bull"
        assert call_args[0].confidence == 0.92
        assert call_args[0].trigger == "baseline"

    @pytest.mark.asyncio
    async def test_persist_regime_failure_does_not_raise(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_context: MagicMock
    ) -> None:
        """Should not raise on database persist failure."""
        from src.models import RegimeData
        from src.service import MarketRegimeServicer

        # Create a mock repository that raises on save
        mock_repository = AsyncMock()
        mock_repository.save = AsyncMock(side_effect=Exception("DB error"))

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        regime_data = RegimeData(
            regime="normal_bull",
            confidence=0.92,
            timestamp="2025-01-26T14:30:00Z",
            trigger="baseline",
        )

        # Should not raise
        await servicer._persist_regime(regime_data)


class TestMainModule:
    """Tests for main.py module."""

    @pytest.mark.asyncio
    async def test_serve_initializes_clients(self) -> None:
        """Should initialize all clients on serve."""
        import asyncio

        # Import the module first so patches work correctly
        import src.main as main_module

        with patch.object(main_module, "RedisClient") as mock_redis_cls, \
             patch.object(main_module, "RedpandaClient") as mock_redpanda_cls, \
             patch.object(main_module, "PostgresClient") as mock_postgres_cls, \
             patch.object(main_module, "grpc") as mock_grpc, \
             patch.object(main_module, "health") as mock_health_module, \
             patch.object(main_module, "health_pb2") as mock_health_pb2, \
             patch.object(main_module, "health_pb2_grpc"), \
             patch.object(main_module, "market_regime_pb2_grpc"):

            # Setup mocks
            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_redpanda = AsyncMock()
            mock_redpanda_cls.return_value = mock_redpanda

            mock_postgres = AsyncMock()
            mock_postgres_cls.return_value = mock_postgres

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(
                side_effect=asyncio.CancelledError()
            )
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
            mock_redpanda.start.assert_called_once()
            mock_postgres.connect.assert_called_once()

            # Verify gRPC server was started
            mock_grpc.aio.server.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health check was set up
            mock_health_servicer.set.assert_called()


class TestSaveRegime:
    """Tests for SaveRegime gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_redpanda(self) -> AsyncMock:
        """Create mock Redpanda client."""
        mock = AsyncMock()
        mock.publish = AsyncMock()
        mock.producer = MagicMock()
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
        mock.save = AsyncMock()
        mock.get_history = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_save_regime_success(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should save valid regime successfully."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="crisis",
            confidence=0.95,
            trigger="circuit_breaker",
            timestamp="2025-01-26T14:30:00Z",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True
        assert response.regime.regime == "crisis"
        assert response.regime.confidence == 0.95
        assert response.regime.trigger == "circuit_breaker"
        assert response.regime.timestamp == "2025-01-26T14:30:00Z"

        # Verify repository.save was called
        mock_repository.save.assert_called_once()

        # Verify cache was updated
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "market:regime:current"
        assert call_args[1] == 21600  # 6 hours

        # Verify event was published
        mock_redpanda.publish.assert_called_once()
        publish_args = mock_redpanda.publish.call_args[0]
        assert publish_args[0] == "regime-change"
        assert publish_args[1]["event_type"] == "regime_saved"
        assert publish_args[1]["regime"] == "crisis"

    @pytest.mark.asyncio
    async def test_save_regime_invalid_regime(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error for invalid regime value."""
        import grpc
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="invalid_regime",
            confidence=0.95,
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is False
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
        mock_context.set_details.assert_called_once()
        assert "invalid_regime" in mock_context.set_details.call_args[0][0]

        # Verify nothing was saved
        mock_repository.save.assert_not_called()
        mock_redis.setex.assert_not_called()
        mock_redpanda.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_regime_invalid_confidence_too_high(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error for confidence > 1.0."""
        import grpc
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=1.5,  # Invalid
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is False
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)

    @pytest.mark.asyncio
    async def test_save_regime_invalid_confidence_negative(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error for confidence < 0.0."""
        import grpc
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=-0.5,  # Invalid
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is False
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)

    @pytest.mark.asyncio
    async def test_save_regime_updates_cache(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should update cache after saving regime."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="euphoria",
            confidence=0.88,
            trigger="fomc",
            timestamp="2025-01-26T14:30:00Z",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True

        # Verify cache was updated with correct data
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "market:regime:current"
        assert call_args[1] == 21600
        cache_data = call_args[2]
        assert cache_data["regime"] == "euphoria"
        assert cache_data["confidence"] == 0.88
        assert cache_data["trigger"] == "fomc"

    @pytest.mark.asyncio
    async def test_save_regime_publishes_event(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should publish event to Redpanda after saving regime."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="low_volatility",
            confidence=0.75,
            trigger="earnings_season",
            timestamp="2025-01-26T14:30:00Z",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True

        # Verify event was published
        mock_redpanda.publish.assert_called_once()
        publish_args = mock_redpanda.publish.call_args[0]
        assert publish_args[0] == "regime-change"
        event_data = publish_args[1]
        assert event_data["event_type"] == "regime_saved"
        assert event_data["regime"] == "low_volatility"
        assert event_data["confidence"] == 0.75
        assert event_data["trigger"] == "earnings_season"

    @pytest.mark.asyncio
    async def test_save_regime_without_timestamp(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should use current time when timestamp not provided."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bear",
            confidence=0.80,
            trigger="geopolitical",
            # No timestamp provided
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True
        assert response.regime.regime == "normal_bear"
        # Timestamp should be set to current time (ISO 8601 format)
        assert "T" in response.regime.timestamp
        assert response.regime.timestamp.endswith("+00:00")

    @pytest.mark.asyncio
    async def test_save_regime_invalid_timestamp_format(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should return error for invalid timestamp format."""
        import grpc
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=0.85,
            trigger="baseline",
            timestamp="not-a-valid-timestamp",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is False
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
        assert "timestamp" in mock_context.set_details.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_save_regime_default_trigger(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should use 'baseline' as default trigger when not provided."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="high_volatility",
            confidence=0.90,
            # No trigger provided
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True
        assert response.regime.trigger == "baseline"

    @pytest.mark.asyncio
    async def test_save_regime_no_redis(
        self, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=None,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=0.85,
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True
        # Verify event still published
        mock_redpanda.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_regime_no_redpanda(
        self, mock_redis: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should work without Redpanda client."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=None,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=0.85,
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        assert response.success is True
        # Verify cache still updated
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_regime_all_valid_regimes(
        self, mock_redis: AsyncMock, mock_redpanda: AsyncMock,
        mock_postgres: MagicMock, mock_repository: AsyncMock, mock_context: MagicMock
    ) -> None:
        """Should accept all valid regime values."""
        from shared.generated import market_regime_pb2

        from src.service import VALID_REGIMES, MarketRegimeServicer

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=mock_redpanda,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        for regime in VALID_REGIMES:
            # Reset mocks for each iteration
            mock_redis.reset_mock()
            mock_redpanda.reset_mock()
            mock_repository.reset_mock()
            mock_context.reset_mock()

            request = market_regime_pb2.SaveRegimeRequest(
                regime=regime,
                confidence=0.85,
                trigger="baseline",
            )
            response = await servicer.SaveRegime(request, mock_context)

            assert response.success is True, f"Failed for regime: {regime}"
            assert response.regime.regime == regime


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
    async def test_get_current_regime_exception(
        self, mock_context: MagicMock
    ) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        # Create mock that raises exception
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=None,
            postgres_client=None,
        )

        request = market_regime_pb2.GetCurrentRegimeRequest(force_refresh=False)
        _ = await servicer.GetCurrentRegime(request, mock_context)

        # Should set error code
        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_regime_history_database_error(
        self, mock_context: MagicMock
    ) -> None:
        """Should handle database errors gracefully."""
        from shared.generated import market_regime_pb2
        from shared.generated.common_pb2 import TimeRange

        from src.service import MarketRegimeServicer

        # Create a mock postgres client
        mock_postgres = MagicMock()
        mock_postgres.engine = MagicMock()

        # Create a mock repository that raises on get_history
        mock_repository = AsyncMock()
        mock_repository.get_history = AsyncMock(side_effect=Exception("DB error"))

        servicer = MarketRegimeServicer(
            redis_client=None,
            redpanda_client=None,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        time_range = TimeRange(
            start_date="2025-01-25T00:00:00Z",
            end_date="2025-01-26T23:59:59Z",
        )
        request = market_regime_pb2.GetRegimeHistoryRequest(time_range=time_range)
        response = await servicer.GetRegimeHistory(request, mock_context)

        # Should set error code
        mock_context.set_code.assert_called()
        assert len(response.regimes) == 0

    @pytest.mark.asyncio
    async def test_save_regime_exception(
        self, mock_context: MagicMock
    ) -> None:
        """Should handle unexpected exceptions in SaveRegime gracefully."""
        import grpc
        from shared.generated import market_regime_pb2

        from src.service import MarketRegimeServicer

        # Create a mock redis that raises an unexpected exception
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Unexpected Redis error"))

        # Create a mock repository that works fine
        mock_repository = AsyncMock()
        mock_repository.save = AsyncMock()

        servicer = MarketRegimeServicer(
            redis_client=mock_redis,
            redpanda_client=None,
            postgres_client=None,
            repository=mock_repository,
        )

        request = market_regime_pb2.SaveRegimeRequest(
            regime="normal_bull",
            confidence=0.85,
            trigger="baseline",
        )
        response = await servicer.SaveRegime(request, mock_context)

        # Should set error code
        mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
        assert response.success is False
