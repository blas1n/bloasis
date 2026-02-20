"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Classification Service.
All environment variables are validated at startup.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class ServiceConfig(BaseSettings):
    """Configuration for Classification Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "classification"
    grpc_port: int = 50054

    # Redis configuration (Layer 2 caching)
    redis_host: str = "localhost"
    redis_port: int = 6379
    cache_ttl: int = 21600  # 6 hours (Tier 2 shared)

    # Market Regime Service (gRPC)
    market_regime_host: str = "market-regime"
    market_regime_port: int = 50051

    # Claude API key and model (required — server will not start without this)
    anthropic_api_key: str = Field(default="", min_length=1)
    claude_model: str = "claude-haiku-4-5-20251001"


# Global config instance - validated at import time
config = ServiceConfig()
