"""Portfolios router — /v1/portfolios/{userId}/*"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..core.responses import (
    PortfolioSummaryResponse,
    PositionsResponse,
    SyncResponse,
    TradeHistoryResponse,
)
from ..dependencies import get_portfolio_service, verify_user_access
from ..services.portfolio import PortfolioService

router = APIRouter()


@router.get("/{user_id}", response_model=PortfolioSummaryResponse)
async def get_portfolio(
    user_id: uuid.UUID = Depends(verify_user_access),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Get portfolio summary with computed metrics."""
    portfolio = await portfolio_svc.get_portfolio(user_id)
    data = portfolio.model_dump()
    total_value = portfolio.total_value
    unrealized_pnl = sum((p.unrealized_pnl for p in portfolio.positions), Decimal("0"))
    data["total_equity"] = total_value
    data["buying_power"] = portfolio.cash_balance
    data["market_value"] = portfolio.invested_value
    data["unrealized_pnl"] = unrealized_pnl
    data["unrealized_pnl_pct"] = (
        unrealized_pnl / total_value * 100 if total_value > 0 else Decimal("0")
    )
    data["realized_pnl"] = portfolio.total_return_amount
    data["daily_pnl"] = portfolio.daily_pnl
    data["daily_pnl_pct"] = portfolio.daily_pnl_pct
    data["position_count"] = len(portfolio.positions)
    return data


@router.get("/{user_id}/positions", response_model=PositionsResponse)
async def get_positions(
    user_id: uuid.UUID = Depends(verify_user_access),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Get all portfolio positions."""
    positions = await portfolio_svc.get_positions(user_id)
    return {"userId": str(user_id), "positions": [p.model_dump() for p in positions]}


@router.get("/{user_id}/trades", response_model=TradeHistoryResponse)
async def get_trades(
    user_id: uuid.UUID = Depends(verify_user_access),
    limit: int = Query(default=20, ge=1, le=100),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Get trade history."""
    trades = await portfolio_svc.get_trades(user_id, limit=limit)
    total_pnl = sum((t.realized_pnl for t in trades), Decimal("0"))
    return {
        "trades": [t.model_dump() for t in trades],
        "totalRealizedPnl": total_pnl,
    }


@router.post("/{user_id}/sync", response_model=SyncResponse)
async def sync_portfolio(
    user_id: uuid.UUID = Depends(verify_user_access),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, Any]:
    """Sync positions from Alpaca broker."""
    return await portfolio_svc.sync_with_alpaca(user_id)
