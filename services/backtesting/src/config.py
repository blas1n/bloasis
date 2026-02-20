"""Service configuration using Pydantic BaseSettings.

This module provides centralized configuration management for the Backtesting Service.
All environment variables are validated at startup.
"""

from decimal import Decimal
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKSPACE_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class ServiceConfig(BaseSettings):
    """Configuration for Backtesting Service.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(_WORKSPACE_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "backtesting"
    grpc_port: int = 50058

    # Market Data Service (gRPC)
    market_data_host: str = "market-data"
    market_data_port: int = 50053

    # Backtesting Engine Configuration
    default_initial_cash: Decimal = Decimal("100000.00")
    default_commission: float = 0.001  # 0.1%
    default_slippage: float = 0.001  # 0.1%

    # Minimum criteria thresholds (for pass/fail determination)
    min_sharpe_ratio: float = 0.5
    max_drawdown_threshold: float = 0.30  # 30%
    min_win_rate: float = 0.40  # 40%


# Global config instance - validated at import time
config = ServiceConfig()
