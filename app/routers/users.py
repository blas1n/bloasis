"""Users router — /v1/users/{userId}/*"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from ..core.models import RiskProfile, UserPreferences
from ..dependencies import get_user_service, verify_user_access
from ..services.user import UserService

router = APIRouter()


class PreferencesUpdate(BaseModel):
    riskProfile: RiskProfile = RiskProfile.MODERATE
    maxPortfolioRisk: Decimal = Field(
        default=Decimal("0.20"), ge=Decimal("0.01"), le=Decimal("1.0")
    )
    maxPositionSize: Decimal = Field(default=Decimal("0.10"), ge=Decimal("0.01"), le=Decimal("1.0"))
    preferredSectors: list[str] = []
    excludedSectors: list[str] = []
    enableNotifications: bool = True
    tradingEnabled: bool = False


class BrokerConfigUpdate(BaseModel):
    apiKey: str = Field(min_length=1)
    secretKey: str = Field(min_length=1)
    paper: bool = True


@router.get("/{user_id}/preferences")
async def get_preferences(
    user_id: uuid.UUID = Depends(verify_user_access),
    user_svc: UserService = Depends(get_user_service),
):
    """Get user risk profile and preferences."""
    prefs = await user_svc.get_preferences(user_id)
    return prefs.model_dump()


@router.put("/{user_id}/preferences")
async def update_preferences(
    user_id: uuid.UUID = Depends(verify_user_access),
    body: PreferencesUpdate = Body(),
    user_svc: UserService = Depends(get_user_service),
):
    """Update user risk profile and preferences."""
    prefs = UserPreferences(
        user_id=str(user_id),
        risk_profile=body.riskProfile,
        max_portfolio_risk=body.maxPortfolioRisk,
        max_position_size=body.maxPositionSize,
        preferred_sectors=body.preferredSectors,
        excluded_sectors=body.excludedSectors,
        enable_notifications=body.enableNotifications,
        trading_enabled=body.tradingEnabled,
    )
    result = await user_svc.update_preferences(user_id, prefs)
    return result.model_dump()


@router.get("/{user_id}/broker")
async def get_broker_status(
    user_id: uuid.UUID = Depends(verify_user_access),
    user_svc: UserService = Depends(get_user_service),
):
    """Get broker connection status."""
    return await user_svc.get_broker_status(user_id)


@router.put("/{user_id}/broker")
async def update_broker_config(
    user_id: uuid.UUID = Depends(verify_user_access),
    body: BrokerConfigUpdate = Body(),
    user_svc: UserService = Depends(get_user_service),
):
    """Save broker API credentials."""
    return await user_svc.update_broker_config(
        user_id,
        body.apiKey,
        body.secretKey,
        body.paper,
    )
