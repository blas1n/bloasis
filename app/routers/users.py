"""Users router — /v1/users/{userId}/*"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import Field, model_validator

from ..core.broker import BrokerAdapter
from ..core.models import RiskProfile, UserPreferences
from ..core.responses import BrokerStatusResponse, BrokerUpdateResponse, CamelModel
from ..dependencies import (
    get_broker_adapter,
    get_portfolio_service,
    get_user_service,
    verify_user_access,
)
from ..services.portfolio import PortfolioService
from ..services.user import UserService

router = APIRouter()


class PreferencesUpdate(CamelModel):
    risk_profile: RiskProfile | None = None
    max_portfolio_risk: Decimal | None = Field(default=None, ge=Decimal("0.01"), le=Decimal("1.0"))
    max_position_size: Decimal | None = Field(default=None, ge=Decimal("0.01"), le=Decimal("1.0"))
    preferred_sectors: list[str] | None = None
    excluded_sectors: list[str] | None = None
    enable_notifications: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "PreferencesUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("At least one field must be provided")
        return self


class BrokerConfigUpdate(CamelModel):
    api_key: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)
    paper: bool = True


@router.get("/{user_id}/preferences", response_model=UserPreferences)
async def get_preferences(
    user_id: uuid.UUID = Depends(verify_user_access),
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Get user risk profile and preferences."""
    prefs = await user_svc.get_preferences(user_id)
    return prefs.model_dump()


@router.patch("/{user_id}/preferences", response_model=UserPreferences)
async def update_preferences(
    user_id: uuid.UUID = Depends(verify_user_access),
    body: PreferencesUpdate = Body(),
    user_svc: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Partially update user preferences. Only provided fields are changed."""
    snake_updates = body.model_dump(exclude_none=True)
    result = await user_svc.patch_preferences(user_id, snake_updates)
    return result.model_dump()


@router.get("/{user_id}/broker", response_model=BrokerStatusResponse)
async def get_broker_status(
    user_id: uuid.UUID = Depends(verify_user_access),
    user_svc: UserService = Depends(get_user_service),
    broker: BrokerAdapter = Depends(get_broker_adapter),
) -> dict[str, Any]:
    """Get broker connection status."""
    return await user_svc.get_broker_status(user_id, broker)


@router.put("/{user_id}/broker", response_model=BrokerUpdateResponse)
async def update_broker_config(
    user_id: uuid.UUID = Depends(verify_user_access),
    body: BrokerConfigUpdate = Body(),
    user_svc: UserService = Depends(get_user_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Save broker API credentials and sync positions."""
    return await user_svc.update_broker_config(
        user_id,
        body.api_key,
        body.secret_key,
        body.paper,
        portfolio_svc=portfolio_svc,
    )
