"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Auth Service.
All environment variables are validated at startup.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class ServiceConfig(BaseSettings):
    """Configuration for Auth Service.

    All settings can be overridden via environment variables.

    JWT uses RS256 (asymmetric RSA keys):
    - Private key path for signing tokens (Auth Service only)
    - Public key path for verification (shared with Envoy Gateway)
    Generate keys with: ./scripts/generate_jwt_keys.sh
    """

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "auth"
    grpc_port: int = 50056

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379

    # User Service configuration
    user_service_host: str = "localhost"
    user_service_port: int = 50052

    # JWT configuration - RS256 (asymmetric RSA keys)
    jwt_private_key_path: str = "infra/keys/jwt-private.pem"
    jwt_public_key_path: str = "infra/keys/jwt-public.pem"

    # Token expiry settings
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Consul configuration
    consul_host: str = "consul"
    consul_port: int = 8500
    consul_enabled: bool = True


# Global config instance - validated at import time
config = ServiceConfig()
