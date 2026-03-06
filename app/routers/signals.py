"""Signals router — /v1/users/{userId}/signals"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import get_strategy_service, get_user_service, verify_user_access
from ..rate_limit import limiter
from ..services.strategy import StrategyService
from ..services.user import UserService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{user_id}/signals")
@limiter.limit("30/minute")
async def get_signals(
    request: Request,
    user_id: str = Depends(verify_user_access),
    strategy_svc: StrategyService = Depends(get_strategy_service),
    user_svc: UserService = Depends(get_user_service),
):
    """Get latest analysis signals (from cache or fresh)."""
    prefs = await user_svc.get_preferences(user_id)
    try:
        result = await strategy_svc.run_analysis(
            user_id=user_id,
            risk_profile=prefs.risk_profile,
            preferred_sectors=prefs.preferred_sectors,
            excluded_sectors=prefs.excluded_sectors,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="AI analysis temporarily unavailable")
    return result.model_dump()


@router.post("/{user_id}/signals")
@limiter.limit("5/minute")
async def trigger_analysis(
    request: Request,
    user_id: str = Depends(verify_user_access),
    strategy_svc: StrategyService = Depends(get_strategy_service),
    user_svc: UserService = Depends(get_user_service),
):
    """Trigger fresh analysis (bypass cache)."""
    await strategy_svc.invalidate_user_cache(user_id)

    prefs = await user_svc.get_preferences(user_id)
    try:
        result = await strategy_svc.run_analysis(
            user_id=user_id,
            risk_profile=prefs.risk_profile,
            preferred_sectors=prefs.preferred_sectors,
            excluded_sectors=prefs.excluded_sectors,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="AI analysis temporarily unavailable")
    return result.model_dump()
