"""Configuration for Notification Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service settings
    service_name: str = "notification"
    ws_host: str = "0.0.0.0"
    ws_port: int = 8080

    # Redpanda Event Streaming
    redpanda_brokers: str = "redpanda:9092"

    # Logging
    log_level: str = "INFO"


config = Settings()
