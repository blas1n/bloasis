"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Classification Service.
All environment variables are validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for Classification Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars from root .env
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

    # FinGPT configuration (via Hugging Face)
    huggingface_token: str = ""  # Hugging Face API token
    fingpt_model: str = "FinGPT/fingpt-sentiment_llama2-13b_lora"  # HF model ID
    fingpt_timeout: float = 60.0
    use_mock_fingpt: bool = True  # Use mock in development (set False for production)


# Global config instance - validated at import time
config = ServiceConfig()
