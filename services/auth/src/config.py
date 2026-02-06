"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Auth Service.
All environment variables are validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Auth Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars from root .env
    )

    # Service identity
    service_name: str = "auth"
    grpc_port: int = 50059

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379

    # User Service configuration
    user_service_host: str = "localhost"
    user_service_port: int = 50058

    # JWT configuration
    jwt_secret_key: str = ""  # REQUIRED: Must be set via environment
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True


# Global config instance - validated at import time
config = ServiceConfig()
