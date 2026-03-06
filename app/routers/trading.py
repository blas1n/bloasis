"""Trading router — /v1/users/{userId}/trading"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_executor_service, verify_user_access
from ..services.executor import ExecutorService

router = APIRouter()


class StopTradingRequest(BaseModel):
    mode: Literal["soft", "hard"] = "soft"


@router.get("/{user_id}/trading")
async def get_trading_status(
    user_id: str = Depends(verify_user_access),
    executor_svc: ExecutorService = Depends(get_executor_service),
):
    """Get automated trading session status."""
    return await executor_svc.get_trading_status(user_id)


@router.post("/{user_id}/trading")
async def start_trading(
    user_id: str = Depends(verify_user_access),
    executor_svc: ExecutorService = Depends(get_executor_service),
):
    """Start automated trading session."""
    return await executor_svc.start_trading(user_id)


@router.delete("/{user_id}/trading")
async def stop_trading(
    user_id: str = Depends(verify_user_access),
    body: StopTradingRequest | None = None,
    executor_svc: ExecutorService = Depends(get_executor_service),
):
    """Stop automated trading session."""
    mode = body.mode if body else "soft"
    return await executor_svc.stop_trading(user_id, mode)
