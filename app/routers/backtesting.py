"""Backtesting router -- /v1/backtesting/*

REST endpoints for running backtests, retrieving results, and comparing strategies.
"""

import re
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..dependencies import get_backtesting_service, get_current_user
from ..services.backtesting import BacktestingService

router = APIRouter()


# --- Request / Response Models ---


class RunBacktestRequest(BaseModel):
    """Request body for POST /v1/backtesting/run."""

    symbols: list[str] = Field(min_length=1, max_length=50)
    strategyType: str = Field(description="Strategy type: ma_crossover or rsi")
    period: str = Field(default="1y", description="Data period (e.g., 1mo, 3mo, 1y)")
    initialCash: Decimal = Field(
        default=Decimal("100000.00"),
        description="Initial cash for simulation",
    )
    commission: float = Field(default=0.001, ge=0, le=0.1)
    slippage: float = Field(default=0.001, ge=0, le=0.1)
    stopLoss: float = Field(default=0.0, ge=0, le=1)
    takeProfit: float = Field(default=0.0, ge=0, le=10)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        cleaned = []
        for sym in v:
            sym = sym.strip().upper()
            if not re.match(r"^[A-Z]{1,10}$", sym):
                raise ValueError(f"Invalid symbol: {sym}")
            cleaned.append(sym)
        return cleaned

    @field_validator("strategyType")
    @classmethod
    def validate_strategy_type(cls, v: str) -> str:
        v = v.lower()
        if v not in ("ma_crossover", "rsi"):
            raise ValueError("strategyType must be 'ma_crossover' or 'rsi'")
        return v

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        valid_periods = ("1mo", "3mo", "6mo", "1y", "2y", "5y")
        if v not in valid_periods:
            raise ValueError(f"period must be one of {valid_periods}")
        return v


class CompareRequest(BaseModel):
    """Request body for POST /v1/backtesting/compare."""

    backtestIds: list[str] = Field(min_length=2)


# --- Endpoints ---


@router.post("/run")
async def run_backtest(
    body: RunBacktestRequest,
    current_user: uuid.UUID = Depends(get_current_user),
    backtesting_svc: BacktestingService = Depends(get_backtesting_service),
):
    """Run a VectorBT backtest for the given symbols and strategy."""
    from ..core.backtesting.models import BacktestConfig

    config = BacktestConfig(
        initial_cash=body.initialCash,
        commission=body.commission,
        slippage=body.slippage,
        stop_loss=body.stopLoss,
        take_profit=body.takeProfit,
    )

    try:
        result = await backtesting_svc.run_backtest(
            symbols=body.symbols,
            strategy_type=body.strategyType,
            config=config,
            period=body.period,
            user_id=str(current_user),
        )
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/results/{backtest_id}")
async def get_backtest_results(
    backtest_id: str,
    current_user: uuid.UUID = Depends(get_current_user),
    backtesting_svc: BacktestingService = Depends(get_backtesting_service),
):
    """Get cached backtest results by ID."""
    result = await backtesting_svc.get_results(backtest_id, user_id=str(current_user))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Backtest not found: {backtest_id}")
    return result.model_dump()


@router.post("/compare")
async def compare_strategies(
    body: CompareRequest,
    current_user: uuid.UUID = Depends(get_current_user),
    backtesting_svc: BacktestingService = Depends(get_backtesting_service),
):
    """Compare multiple backtest results, ranked by Sharpe ratio."""
    try:
        return await backtesting_svc.compare_strategies(body.backtestIds, user_id=str(current_user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
