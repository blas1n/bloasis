"""
Shared utilities for BLOASIS services

Contents:
- ConsulClient: Service registration and discovery
- RedisClient: Caching and session management
- RedpandaClient: Event publishing (Kafka API)
- EventPublisher: Typed event publishing with priority support
- EventConsumer: Event consumption with priority handling
- EventPriority: Priority levels for event routing
- PostgresClient: Database connection
- JSONFormatter: Custom JSON log formatter
- setup_logger: Logger configuration utility
"""

from .consul_client import ConsulClient, get_local_ip
from .event_consumer import EventConsumer
from .event_publisher import EventPriority, EventPublisher
from .logging import JSONFormatter, setup_logger
from .postgres_client import PostgresClient
from .redis_client import RedisClient
from .redpanda_client import RedpandaClient

__all__ = [
    "ConsulClient",
    "EventConsumer",
    "EventPriority",
    "EventPublisher",
    "JSONFormatter",
    "PostgresClient",
    "RedisClient",
    "RedpandaClient",
    "get_local_ip",
    "setup_logger",
]
