"""Unified application configuration.

Single Pydantic Settings class for all environment variables.
Replaces 10 separate service config files.
"""

import base64
import logging
from decimal import Decimal
from pathlib import Path

import jwt
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Module-level cache for JWT keys (loaded once, reused across requests)
_jwt_key_cache: dict[str, str] = {}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application ---
    app_name: str = "bloasis"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    mock_broker_enabled: bool = False

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/bloasis"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""

    # --- LLM ---
    llm_model: str = "anthropic/claude-haiku-4-5-20251001"
    llm_api_key: str = ""
    llm_api_base: str | None = None
    llm_timeout: int = 120

    # --- External Data APIs ---
    fred_api_key: str = ""

    # --- Alpaca (Broker) ---
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_paper: bool = True

    # --- JWT (RS256, asymmetric) ---
    jwt_private_key_path: str = "infra/keys/jwt-private.pem"
    jwt_public_key_path: str = "infra/keys/jwt-public.pem"
    jwt_algorithm: str = "RS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # --- Encryption (required for broker config) ---
    fernet_key: str = Field(default="", validation_alias="CREDENTIAL_ENCRYPTION_KEY")

    # --- Cache TTLs (seconds) ---
    cache_regime_ttl: int = 21600  # 6 hours (Tier 1)
    cache_sector_ttl: int = 21600  # 6 hours (Tier 1)
    cache_user_portfolio_ttl: int = 3600  # 1 hour (Tier 2)
    cache_user_preferences_ttl: int = 2592000  # 30 days (Tier 3)
    cache_ohlcv_ttl: int = 300  # 5 minutes
    cache_stock_info_ttl: int = 86400  # 24 hours
    cache_sentiment_ttl: int = 3600  # 1 hour
    cache_macro_ttl: int = 3600  # 1 hour (Tier 1, shared)

    # --- Risk Limits ---
    max_position_size: Decimal = Decimal("0.10")
    max_single_order: Decimal = Decimal("0.05")
    max_sector_concentration: Decimal = Decimal("0.30")
    vix_high_threshold: Decimal = Decimal("30.0")
    vix_extreme_threshold: Decimal = Decimal("40.0")

    @field_validator("fernet_key")
    @classmethod
    def validate_fernet_key_format(cls, v: str) -> str:
        """Validate Fernet key format when provided."""
        if v:
            try:
                decoded = base64.urlsafe_b64decode(v)
                if len(decoded) != 32:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError(
                    "CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key. "
                    'Generate with: python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"'
                )
        return v

    @property
    def jwt_private_key(self) -> str:
        """Load RSA private key for signing tokens (cached after first read)."""
        if "private" not in _jwt_key_cache:
            path = Path(self.jwt_private_key_path)
            if not path.exists():
                raise ValueError(f"JWT private key not found at {path}")
            _jwt_key_cache["private"] = path.read_text()
        return _jwt_key_cache["private"]

    @property
    def jwt_public_key(self) -> str:
        """Load RSA public key for verifying tokens (cached after first read)."""
        if "public" not in _jwt_key_cache:
            path = Path(self.jwt_public_key_path)
            if not path.exists():
                raise ValueError(f"JWT public key not found at {path}")
            _jwt_key_cache["public"] = path.read_text()
        return _jwt_key_cache["public"]

    # --- Trading ---
    scheduler_enabled: bool = False
    analysis_interval_seconds: int = 600  # 10 minutes
    max_stocks_per_analysis: int = 15
    signal_min_confidence: Decimal = Decimal("0.6")
    signal_dedup_ttl: int = 3600  # 1 hour — prevent re-executing same signal

    # --- Backtesting ---
    backtest_default_cash: Decimal = Decimal("100000.00")
    backtest_min_sharpe: float = 0.5
    backtest_max_drawdown: float = 0.30
    backtest_min_win_rate: float = 0.40

    # --- Classification ---
    gics_sectors: list[str] = [
        "Technology",
        "Healthcare",
        "Financials",
        "Consumer Discretionary",
        "Communication Services",
        "Industrials",
        "Consumer Staples",
        "Energy",
        "Utilities",
        "Real Estate",
        "Materials",
    ]

    # --- Fallback candidates (used when LLM classification fails) ---
    fallback_candidates: list[tuple[str, str]] = [
        ("AAPL", "Technology"),
        ("MSFT", "Technology"),
        ("NVDA", "Technology"),
        ("JNJ", "Healthcare"),
        ("UNH", "Healthcare"),
        ("JPM", "Financials"),
        ("V", "Financials"),
        ("PG", "Consumer Staples"),
        ("KO", "Consumer Staples"),
        ("XOM", "Energy"),
    ]

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()


def decode_jwt_user_id(token: str) -> str | None:
    """Decode JWT and extract user_id (sub claim). Returns None on failure.

    Shared helper used by rate_limit.py and UserService.validate_token().
    """
    try:
        payload = jwt.decode(token, settings.jwt_public_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        sub: str | None = payload.get("sub")
        return sub
    except jwt.InvalidTokenError:
        return None
