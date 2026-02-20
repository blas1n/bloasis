"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Portfolio Service.
All environment variables are validated at startup.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class ServiceConfig(BaseSettings):
    """Configuration for Portfolio Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "portfolio"
    grpc_port: int = 50057

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Redpanda configuration
    redpanda_brokers: str = "localhost:9092"

    # Database configuration
    database_url: str = ""

    # Cache TTL (user-specific data - 1 hour)
    cache_ttl: int = 3600

    # Market Data Service configuration
    market_data_host: str = "market-data"
    market_data_port: int = 50051

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True


# Global config instance - validated at import time
config = ServiceConfig()
