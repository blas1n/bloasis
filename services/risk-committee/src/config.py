"""Configuration for Risk Committee Service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration loaded from environment."""

    # Service settings
    service_name: str = "risk-committee"
    grpc_port: int = 50059

    # Portfolio Service connection
    portfolio_host: str = "portfolio"
    portfolio_port: int = 50060

    # Market Data Service connection
    market_data_host: str = "market-data"
    market_data_port: int = 50052

    # Consul Service Discovery
    consul_host: str = "consul"
    consul_port: int = 8500

    # Redpanda Event Streaming
    redpanda_bootstrap_servers: str = "redpanda:9092"

    # Default risk limits
    default_max_position_size: float = 0.10  # 10% max per position
    default_max_single_order: float = 0.05  # 5% max single order
    default_max_sector_concentration: float = 0.30  # 30% max per sector

    # VIX thresholds
    vix_high_threshold: float = 30.0
    vix_extreme_threshold: float = 40.0

    class Config:
        """Pydantic config."""

        env_file = ".env"
        extra = "ignore"


config = Settings()
