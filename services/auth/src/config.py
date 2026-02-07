"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Auth Service.
All environment variables are validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Auth Service.

    All settings can be overridden via environment variables.

    JWT Algorithm Configuration:
    - RS256 (default, recommended): Uses asymmetric RSA keys
        - Set jwt_private_key_path for signing
        - Set jwt_public_key_path for verification
    - HS256 (legacy): Uses symmetric secret key
        - Set jwt_secret_key for both signing and verification
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

    # JWT configuration - RS256 (default, recommended)
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "infra/keys/jwt-private.pem"
    jwt_public_key_path: str = "infra/keys/jwt-public.pem"

    # JWT configuration - HS256 (legacy support)
    # If jwt_secret_key is set and jwt_algorithm is HS256, uses symmetric key
    jwt_secret_key: str = ""

    # Token expiry settings
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True


# Global config instance - validated at import time
config = ServiceConfig()
