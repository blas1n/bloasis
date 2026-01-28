"""
Shared utilities for BLOASIS services

Contents:
- RedisClient: Caching and session management

Planned:
- RedpandaClient: Event publishing (Kafka API)
- PostgresClient: Database connection
- Logging: Structured JSON logging
"""

from .redis_client import RedisClient

# To be added when utilities are implemented
# from .redpanda_client import RedpandaClient

__all__ = ["RedisClient"]
