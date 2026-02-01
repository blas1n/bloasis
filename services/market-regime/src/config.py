"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Market Regime Service.
All environment variables are validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Market Regime Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars from root .env
    )

    # Service identity
    service_name: str = "market-regime"
    grpc_port: int = 50051

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Redpanda configuration
    redpanda_brokers: str = "localhost:9092"

    # Database configuration
    database_url: str = ""

    # External API keys (optional)
    fingpt_api_key: str = ""

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True
    service_host: str = "market-regime"  # Hostname for Consul registration


# Global config instance - validated at import time
config = ServiceConfig()
