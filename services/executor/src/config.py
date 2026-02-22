"""Configuration for Executor Service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Service configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service settings
    service_name: str = "executor"
    grpc_port: int = 50060

    # Redis connection
    redis_host: str = "redis"
    redis_port: int = 6379

    # Redpanda Event Streaming
    redpanda_brokers: str = "redpanda:9092"

    # User Service (for dynamic broker config)
    user_service_host: str = "user"
    user_service_port: int = 50052

    # Consul Service Discovery
    consul_host: str = "consul"
    consul_port: int = 8500


config = Settings()
