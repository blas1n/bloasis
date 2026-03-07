"""Market router — /v1/market/*"""

from typing import Any

from fastapi import APIRouter, Depends

from ..core.models import MarketRegime
from ..dependencies import get_current_user, get_market_regime_service
from ..services.market_regime import MarketRegimeService

router = APIRouter()


@router.get("/regimes/current", response_model=MarketRegime)
async def get_current_regime(
    current_user: str = Depends(get_current_user),
    regime_svc: MarketRegimeService = Depends(get_market_regime_service),
) -> dict[str, Any]:
    """Get current market regime classification."""
    regime = await regime_svc.get_current()
    return regime.model_dump()
