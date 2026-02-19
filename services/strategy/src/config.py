"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Strategy Service.
All environment variables are validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Strategy Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars from root .env
    )

    # Service identity
    service_name: str = "strategy"
    grpc_port: int = 50055

    # Redis configuration (Layer 3 caching - user-specific)
    redis_host: str = "localhost"
    redis_port: int = 6379
    cache_ttl: int = 3600  # 1 hour (Layer 3 user-specific)
    preferences_ttl: int = 86400 * 30  # 30 days for preferences

    # Market Regime Service (gRPC)
    market_regime_host: str = "market-regime"
    market_regime_port: int = 50051

    # Classification Service (gRPC)
    classification_host: str = "classification"
    classification_port: int = 50054

    # Market Data Service (gRPC)
    market_data_host: str = "market-data"
    market_data_port: int = 50053

    # Redpanda (Event Publishing)
    redpanda_brokers: str = "localhost:9092"

    # Claude AI configuration (for macro/regime analysis)
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # Sentiment caching
    sentiment_cache_ttl: int = 3600  # 1 hour TTL for sentiment cache


# Global config instance - validated at import time
config = ServiceConfig()
