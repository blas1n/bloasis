"""Market router — /v1/market/*"""

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, get_market_regime_service
from ..services.market_regime import MarketRegimeService

router = APIRouter()


@router.get("/regimes/current")
async def get_current_regime(
    current_user: str = Depends(get_current_user),
    regime_svc: MarketRegimeService = Depends(get_market_regime_service),
):
    """Get current market regime classification."""
    regime = await regime_svc.get_current()
    return regime.model_dump()
