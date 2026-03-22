"""API response models for OpenAPI schema generation."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .models import (
    MarketRegime,
    Position,
    StockPick,
    Trade,
    TradingSignal,
)

# Re-export models used directly as response_model in routers
__all__ = [
    "MarketRegime",
    "StockPick",
    "TradingSignal",
]


def _to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CamelModel(BaseModel):
    """Base model that accepts both snake_case and camelCase keys."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_to_camel,
    )


# --- Auth ---
class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    user_id: str
    name: str = ""


class RefreshTokenResponse(CamelModel):
    access_token: str
    refresh_token: str


class UserInfoResponse(CamelModel):
    user_id: str
    name: str
    email: str


# --- Portfolio ---
class PortfolioSummaryResponse(CamelModel):
    user_id: str
    total_value: Decimal
    total_equity: Decimal
    cash_balance: Decimal
    buying_power: Decimal
    invested_value: Decimal
    market_value: Decimal
    total_return: Decimal
    total_return_amount: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    daily_pnl: Decimal
    daily_pnl_pct: Decimal
    position_count: int
    currency: str


class PositionsResponse(CamelModel):
    user_id: str
    positions: list[Position]


class TradeHistoryResponse(CamelModel):
    trades: list[Trade]
    total_realized_pnl: Decimal


# --- Trading Control ---
class TradingControlResponse(CamelModel):
    trading_enabled: bool
    status: str


class TradingStatusResponse(CamelModel):
    trading_enabled: bool
    status: str
    last_changed: str


# --- Broker ---
class BrokerStatusResponse(CamelModel):
    configured: bool
    connected: bool
    equity: Decimal = Decimal("0")
    cash: Decimal = Decimal("0")
    error_message: str = ""


class BrokerUpdateResponse(CamelModel):
    configured: bool
    connected: bool = False
    positions_synced: int = 0
    error_message: str = ""


# --- Sync ---
class SyncResponse(CamelModel):
    success: bool
    positions_synced: int = 0
    error_message: str = ""


# --- Simple ---
class SuccessResponse(CamelModel):
    success: bool


class MessageResponse(CamelModel):
    message: str
