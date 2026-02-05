"""Pydantic models for Backtesting Service.

These models are service-specific and used for internal business logic.
Inter-service communication uses Proto messages only (gRPC).
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    """Configuration parameters for backtest simulation."""

    initial_cash: Decimal = Field(
        default=Decimal("100000.00"), description="Initial capital for simulation (USD)"
    )
    commission: float = Field(
        default=0.001, ge=0, le=0.1, description="Commission per trade (e.g., 0.001 = 0.1%)"
    )
    slippage: float = Field(
        default=0.001, ge=0, le=0.1, description="Slippage per trade (e.g., 0.001 = 0.1%)"
    )
    stop_loss: float = Field(
        default=0.0, ge=0, le=1, description="Stop loss threshold (0 = disabled)"
    )
    take_profit: float = Field(
        default=0.0, ge=0, le=10, description="Take profit threshold (0 = disabled)"
    )


class SymbolResult(BaseModel):
    """Backtest results for a single symbol."""

    symbol: str = Field(description="Stock ticker symbol")
    total_return: float = Field(description="Total return percentage")
    sharpe_ratio: float = Field(default=0.0, description="Sharpe ratio")
    sortino_ratio: float = Field(default=0.0, description="Sortino ratio")
    max_drawdown: float = Field(default=0.0, description="Maximum drawdown percentage")
    win_rate: float = Field(default=0.0, ge=0, le=1, description="Win rate percentage")
    profit_factor: float = Field(default=0.0, ge=0, description="Profit factor")
    total_trades: int = Field(default=0, ge=0, description="Total number of trades")
    avg_trade_duration_days: float = Field(
        default=0.0, ge=0, description="Average trade duration in days"
    )
    calmar_ratio: float = Field(default=0.0, description="Calmar ratio")
    passed: bool = Field(default=False, description="Whether strategy passes minimum criteria")


class PortfolioMetrics(BaseModel):
    """Aggregated portfolio-level metrics."""

    total_return: float = Field(default=0.0, description="Average total return across all symbols")
    sharpe_ratio: float = Field(default=0.0, description="Average Sharpe ratio")
    max_drawdown: float = Field(default=0.0, description="Maximum drawdown (worst across symbols)")
    volatility: float = Field(default=0.0, description="Return volatility")


class BacktestResponse(BaseModel):
    """Complete backtest response."""

    backtest_id: str = Field(description="Unique backtest identifier")
    results: list[SymbolResult] = Field(default_factory=list, description="Per-symbol results")
    portfolio_metrics: PortfolioMetrics = Field(
        default_factory=PortfolioMetrics, description="Portfolio-level metrics"
    )
    created_at: str = Field(description="ISO 8601 timestamp when backtest completed")
    strategy_type: str | None = Field(default=None, description="Strategy type used")


class OHLCVBar(BaseModel):
    """Single OHLCV bar/candle."""

    timestamp: str = Field(description="ISO 8601 timestamp")
    open: float = Field(description="Open price")
    high: float = Field(description="High price")
    low: float = Field(description="Low price")
    close: float = Field(description="Close price")
    volume: int = Field(description="Trading volume")
    adj_close: float | None = Field(default=None, description="Adjusted close price")


class BacktestComparison(BaseModel):
    """Comparison entry for a single strategy."""

    backtest_id: str = Field(description="Backtest ID")
    strategy_name: str = Field(description="Strategy name/type")
    metrics: PortfolioMetrics = Field(description="Portfolio metrics for comparison")
    rank: int = Field(ge=0, description="Rank (0 = unranked, 1 = best)")
