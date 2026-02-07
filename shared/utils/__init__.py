"""
Shared utilities for BLOASIS services

Contents:
- ConsulClient: Service registration and discovery
- RedisClient: Caching and session management
- CacheManager: Unified cache strategy (Tier 1-3)
- CacheConfig: Cache configuration dataclass
- CacheTier: Cache tier enum
- create_cache_manager: Factory function for CacheManager
- RedpandaClient: Event publishing (Kafka API)
- EventPublisher: Typed event publishing with priority support
- EventConsumer: Event consumption with priority handling
- EventPriority: Priority levels for event routing
- PostgresClient: Database connection
- JSONFormatter: Custom JSON log formatter
- setup_logger: Logger configuration utility
"""

from .cache_strategy import (
    CACHE_CONFIGS,
    CacheConfig,
    CacheManager,
    CacheTier,
    create_cache_manager,
)
from .consul_client import ConsulClient, get_local_ip
from .event_consumer import EventConsumer
from .event_publisher import EventPriority, EventPublisher
from .logging import JSONFormatter, setup_logger
from .postgres_client import PostgresClient
from .redis_client import RedisClient
from .redpanda_client import RedpandaClient

__all__ = [
    "CACHE_CONFIGS",
    "CacheConfig",
    "CacheManager",
    "CacheTier",
    "ConsulClient",
    "EventConsumer",
    "EventPriority",
    "EventPublisher",
    "JSONFormatter",
    "PostgresClient",
    "RedisClient",
    "RedpandaClient",
    "create_cache_manager",
    "get_local_ip",
    "setup_logger",
]
