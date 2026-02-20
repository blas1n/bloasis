"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Market Regime Service.
All environment variables are validated at startup.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class ServiceConfig(BaseSettings):
    """Configuration for Market Regime Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "market-regime"
    grpc_port: int = 50051
    service_address: str = "host.docker.internal"  # For Consul registration (Envoy in Docker)

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Redpanda configuration
    redpanda_brokers: str = "localhost:9092"

    # Database configuration
    database_url: str = ""

    # Claude API key and model
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # FRED API (for macro data)
    fred_api_key: str = ""

    # Cache TTL
    regime_cache_ttl: int = 21600  # 6 hours (Tier 1 shared)

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True


# Global config instance - validated at import time
config = ServiceConfig()
