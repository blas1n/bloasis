"""Configuration for Executor Service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration loaded from environment."""

    # Service settings
    service_name: str = "executor"
    grpc_port: int = 50060

    # Alpaca settings
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True  # Always paper trading in Phase 1

    # Redis connection
    redis_host: str = "redis"
    redis_port: int = 6379

    # Redpanda Event Streaming
    redpanda_bootstrap_servers: str = "redpanda:9092"

    # Consul Service Discovery
    consul_host: str = "consul"
    consul_port: int = 8500

    class Config:
        """Pydantic config."""

        env_file = ".env"
        extra = "ignore"


config = Settings()
