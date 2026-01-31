"""
Market Regime Service - gRPC Servicer Implementation.

Implements the MarketRegimeService gRPC interface with:
- Redis caching (6-hour TTL for Tier 1 shared data)
- Redpanda event publishing
- PostgreSQL persistence
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import grpc
from shared.generated import market_regime_pb2, market_regime_pb2_grpc
from shared.utils import PostgresClient, RedisClient, RedpandaClient

from .models import RegimeClassifier, RegimeData
from .repositories import MarketRegimeRepository

logger = logging.getLogger(__name__)

# Cache configuration (Tier 1 shared caching)
CACHE_KEY = "market:regime:current"
CACHE_TTL = 21600  # 6 hours in seconds

# Redpanda topic
REGIME_CHANGE_TOPIC = "regime-change"

# Valid regime values
VALID_REGIMES = {
    "crisis",
    "normal_bear",
    "normal_bull",
    "euphoria",
    "high_volatility",
    "low_volatility",
}


class MarketRegimeServicer(market_regime_pb2_grpc.MarketRegimeServiceServicer):
    """
    gRPC servicer implementing the MarketRegimeService interface.

    Provides market regime classification using FinGPT analysis.
    Results are cached for 6 hours (Tier 1 shared across all users).
    """

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        redpanda_client: Optional[RedpandaClient] = None,
        postgres_client: Optional[PostgresClient] = None,
        repository: Optional[MarketRegimeRepository] = None,
    ) -> None:
        """
        Initialize the servicer with required clients.

        Args:
            redis_client: Redis client for caching.
            redpanda_client: Redpanda client for event publishing.
            postgres_client: PostgreSQL client for persistence.
            repository: Repository for database operations.
        """
        self.redis = redis_client
        self.redpanda = redpanda_client
        self.postgres = postgres_client
        self.repository = repository or MarketRegimeRepository(postgres_client)
        self.classifier = RegimeClassifier()

    async def GetCurrentRegime(
        self,
        request: market_regime_pb2.GetCurrentRegimeRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_regime_pb2.GetCurrentRegimeResponse:
        """
        Get the current market regime classification.

        Implements caching strategy:
        1. Check Redis cache (unless force_refresh is true)
        2. If cache miss or force_refresh, classify using FinGPT
        3. Cache the result for 6 hours
        4. Publish regime-change event to Redpanda
        5. Persist to database

        Args:
            request: The gRPC request containing force_refresh flag.
            context: The gRPC servicer context.

        Returns:
            GetCurrentRegimeResponse with regime classification.
        """
        try:
            # Check cache first (unless force_refresh requested)
            if not request.force_refresh and self.redis:
                cached = await self.redis.get(CACHE_KEY)
                if cached and isinstance(cached, dict):
                    logger.info("Cache hit for current regime")
                    return market_regime_pb2.GetCurrentRegimeResponse(
                        regime=cached.get("regime", ""),
                        confidence=cached.get("confidence", 0.0),
                        timestamp=cached.get("timestamp", ""),
                        trigger=cached.get("trigger", ""),
                    )

            # Cache miss or force_refresh - classify regime
            logger.info("Classifying market regime...")
            regime_data: RegimeData = await self.classifier.classify()

            # Create response
            response = market_regime_pb2.GetCurrentRegimeResponse(
                regime=regime_data.regime,
                confidence=regime_data.confidence,
                timestamp=regime_data.timestamp,
                trigger=regime_data.trigger,
            )

            # Cache the result
            if self.redis:
                cache_data = {
                    "regime": regime_data.regime,
                    "confidence": regime_data.confidence,
                    "timestamp": regime_data.timestamp,
                    "trigger": regime_data.trigger,
                }
                await self.redis.setex(CACHE_KEY, CACHE_TTL, cache_data)
                logger.info(f"Cached regime data with TTL {CACHE_TTL}s")

            # Publish event to Redpanda
            if self.redpanda:
                event_data = {
                    "event_type": "regime_classified",
                    "regime": regime_data.regime,
                    "confidence": regime_data.confidence,
                    "timestamp": regime_data.timestamp,
                    "trigger": regime_data.trigger,
                }
                await self.redpanda.publish(REGIME_CHANGE_TOPIC, event_data)
                logger.info(f"Published regime-change event to {REGIME_CHANGE_TOPIC}")

            # Persist to database via repository
            await self._persist_regime(regime_data)

            return response

        except Exception as e:
            logger.error(f"Failed to get current regime: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to classify market regime: {str(e)}")
            return market_regime_pb2.GetCurrentRegimeResponse()

    async def GetRegimeHistory(
        self,
        request: market_regime_pb2.GetRegimeHistoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_regime_pb2.GetRegimeHistoryResponse:
        """
        Get historical regime classifications within a time range.

        Queries the database for regime history between start_date and end_date
        using the Repository pattern.

        Args:
            request: The gRPC request containing time_range.
            context: The gRPC servicer context.

        Returns:
            GetRegimeHistoryResponse with list of regime classifications.
        """
        try:
            if not self.postgres:
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("Database not available")
                return market_regime_pb2.GetRegimeHistoryResponse()

            time_range = request.time_range
            if not time_range.start_date or not time_range.end_date:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("time_range with start_date and end_date is required")
                return market_regime_pb2.GetRegimeHistoryResponse()

            # Parse ISO 8601 timestamps
            start_time = datetime.fromisoformat(
                time_range.start_date.replace("Z", "+00:00")
            )
            end_time = datetime.fromisoformat(
                time_range.end_date.replace("Z", "+00:00")
            )

            # Query database via repository
            records = await self.repository.get_history(start_time, end_time)

            # Build response from ORM records
            regimes = []
            for record in records:
                regime_response = market_regime_pb2.GetCurrentRegimeResponse(
                    regime=record.regime,
                    confidence=record.confidence,
                    timestamp=record.timestamp.isoformat() if record.timestamp else "",
                    trigger=record.trigger,
                )
                regimes.append(regime_response)

            logger.info(f"Retrieved {len(regimes)} historical regime records")
            return market_regime_pb2.GetRegimeHistoryResponse(regimes=regimes)

        except Exception as e:
            logger.error(f"Failed to get regime history: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to retrieve regime history: {str(e)}")
            return market_regime_pb2.GetRegimeHistoryResponse()

    async def _persist_regime(self, regime_data: RegimeData) -> None:
        """
        Persist regime classification to database via repository.

        Args:
            regime_data: The regime data to persist.
        """
        try:
            # Parse ISO 8601 timestamp string to datetime
            timestamp_dt = datetime.fromisoformat(
                regime_data.timestamp.replace("Z", "+00:00")
            )

            await self.repository.save(regime_data, timestamp_dt)
            logger.info("Persisted regime to database")

        except Exception as e:
            # Log but don't fail the request if persistence fails
            logger.warning(f"Failed to persist regime to database: {e}")

    async def SaveRegime(
        self,
        request: market_regime_pb2.SaveRegimeRequest,
        context: grpc.aio.ServicerContext,
    ) -> market_regime_pb2.SaveRegimeResponse:
        """
        Save a regime classification to the database.

        Used by schedulers or external services to record regime changes.
        Also updates cache and publishes event to Redpanda.

        Args:
            request: The gRPC request containing regime data.
            context: The gRPC servicer context.

        Returns:
            SaveRegimeResponse with success status and saved regime data.
        """
        try:
            # Validate regime value
            if request.regime not in VALID_REGIMES:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(
                    f"Invalid regime value: {request.regime}. "
                    f"Must be one of: {', '.join(sorted(VALID_REGIMES))}"
                )
                return market_regime_pb2.SaveRegimeResponse(success=False)

            # Validate confidence score
            if not (0.0 <= request.confidence <= 1.0):
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(
                    f"Invalid confidence value: {request.confidence}. "
                    "Must be between 0.0 and 1.0"
                )
                return market_regime_pb2.SaveRegimeResponse(success=False)

            # Use provided timestamp or current UTC time
            if request.timestamp:
                timestamp_str = request.timestamp
                try:
                    # Validate timestamp format
                    timestamp_dt = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(
                        f"Invalid timestamp format: {request.timestamp}. "
                        "Must be ISO 8601 format."
                    )
                    return market_regime_pb2.SaveRegimeResponse(success=False)
            else:
                timestamp_dt = datetime.now(timezone.utc)
                timestamp_str = timestamp_dt.isoformat()

            # Create RegimeData
            regime_data = RegimeData(
                regime=request.regime,
                confidence=request.confidence,
                timestamp=timestamp_str,
                trigger=request.trigger or "baseline",
            )

            # Persist to database via repository
            await self._persist_regime(regime_data)

            # Update Redis cache with new regime
            if self.redis:
                cache_data = {
                    "regime": regime_data.regime,
                    "confidence": regime_data.confidence,
                    "timestamp": regime_data.timestamp,
                    "trigger": regime_data.trigger,
                }
                await self.redis.setex(CACHE_KEY, CACHE_TTL, cache_data)
                logger.info(f"Updated cache with new regime: {regime_data.regime}")

            # Publish regime-change event to Redpanda
            if self.redpanda:
                event_data = {
                    "event_type": "regime_saved",
                    "regime": regime_data.regime,
                    "confidence": regime_data.confidence,
                    "timestamp": regime_data.timestamp,
                    "trigger": regime_data.trigger,
                }
                await self.redpanda.publish(REGIME_CHANGE_TOPIC, event_data)
                logger.info(f"Published regime-saved event to {REGIME_CHANGE_TOPIC}")

            # Build response
            regime_response = market_regime_pb2.GetCurrentRegimeResponse(
                regime=regime_data.regime,
                confidence=regime_data.confidence,
                timestamp=regime_data.timestamp,
                trigger=regime_data.trigger,
            )

            logger.info(
                f"Successfully saved regime: {regime_data.regime} "
                f"(confidence: {regime_data.confidence})"
            )

            return market_regime_pb2.SaveRegimeResponse(
                success=True,
                regime=regime_response,
            )

        except Exception as e:
            logger.error(f"Failed to save regime: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to save regime: {str(e)}")
            return market_regime_pb2.SaveRegimeResponse(success=False)
