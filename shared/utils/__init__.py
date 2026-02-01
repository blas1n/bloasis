"""
Shared utilities for BLOASIS services

Contents:
- ConsulClient: Service registration and discovery
- RedisClient: Caching and session management
- RedpandaClient: Event publishing (Kafka API)
- PostgresClient: Database connection
- JSONFormatter: Custom JSON log formatter
- setup_logger: Logger configuration utility
"""

from .consul_client import ConsulClient
from .logging import JSONFormatter, setup_logger
from .postgres_client import PostgresClient
from .redis_client import RedisClient
from .redpanda_client import RedpandaClient

__all__ = [
    "ConsulClient",
    "JSONFormatter",
    "PostgresClient",
    "RedisClient",
    "RedpandaClient",
    "setup_logger",
]
