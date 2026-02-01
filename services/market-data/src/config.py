"""Service configuration using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Market Data Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "market-data"
    grpc_port: int = 50053

    # Redis configuration (for caching)
    redis_host: str = "redis"
    redis_port: int = 6379
    cache_ttl: int = 300  # 5 minutes for real-time data

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True

    # PostgreSQL configuration (for TimescaleDB storage)
    postgres_enabled: bool = True


config = ServiceConfig()
