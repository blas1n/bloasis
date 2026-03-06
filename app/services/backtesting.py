"""Backtesting Service -- run and compare VectorBT backtests.

Replaces: services/backtesting/ (gRPC servicer -> plain class)
Key simplifications:
- No gRPC/proto, plain method calls
- Redis caching replaces in-memory dict
- MarketDataService injected via constructor
"""

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.backtesting.metrics import MetricsCalculator
from ..core.backtesting.models import (
    BacktestComparison,
    BacktestConfig,
    BacktestResult,
    SymbolResult,
)
from ..core.backtesting.vectorbt_engine import VectorBTEngine
from .market_data import MarketDataService

logger = logging.getLogger(__name__)

# Cache TTL for backtest results (1 hour)
_RESULT_CACHE_TTL = 3600


class BacktestingService:
    """Backtesting service with VectorBT engine and Redis caching."""

    def __init__(
        self,
        redis: RedisClient,
        market_data_svc: MarketDataService,
    ) -> None:
        self.redis = redis
        self.market_data_svc = market_data_svc
        self.engine = VectorBTEngine(
            min_sharpe=settings.backtest_min_sharpe,
            max_drawdown=settings.backtest_max_drawdown,
            min_win_rate=settings.backtest_min_win_rate,
        )
        self.metrics = MetricsCalculator()

    async def run_backtest(
        self,
        symbols: list[str],
        strategy_type: str,
        config: BacktestConfig | None = None,
        period: str = "1y",
        user_id: str = "",
    ) -> BacktestResult:
        """Run VectorBT backtest for given symbols and strategy.

        Args:
            symbols: List of stock ticker symbols.
            strategy_type: Strategy type (ma_crossover, rsi).
            config: Backtest configuration (uses defaults if None).
            period: Data period for OHLCV fetch.

        Returns:
            BacktestResult with per-symbol results and portfolio metrics.

        Raises:
            ValueError: If symbols list is empty or strategy_type is invalid.
        """
        if not symbols:
            raise ValueError("At least one symbol is required")

        valid_strategies = ("ma_crossover", "rsi")
        strategy_type = strategy_type.lower()
        if strategy_type not in valid_strategies:
            raise ValueError(
                f"Invalid strategy_type: {strategy_type}. Supported: {', '.join(valid_strategies)}"
            )

        if config is None:
            config = BacktestConfig(
                initial_cash=settings.backtest_default_cash,
            )

        logger.info(
            "RunBacktest: symbols=%s, strategy=%s, period=%s",
            symbols,
            strategy_type,
            period,
        )

        results: list[SymbolResult] = []
        for symbol in symbols:
            try:
                ohlcv = await self.market_data_svc.get_ohlcv(symbol, period=period)
                if strategy_type == "ma_crossover":
                    result = self.engine.backtest_ma_crossover(
                        symbol=symbol,
                        ohlcv=ohlcv,
                        backtest_config=config,
                    )
                else:
                    result = self.engine.backtest_rsi(
                        symbol=symbol,
                        ohlcv=ohlcv,
                        backtest_config=config,
                    )
                results.append(result)
            except Exception as e:
                logger.error("Backtest failed for %s: %s", symbol, e)
                continue

        portfolio_metrics = self.metrics.calculate_portfolio_metrics(results)

        backtest_id = f"backtest_{uuid4()}"
        created_at = datetime.now(UTC).isoformat()

        response = BacktestResult(
            backtest_id=backtest_id,
            results=results,
            portfolio_metrics=portfolio_metrics,
            created_at=created_at,
            strategy_type=strategy_type,
        )

        # Cache in Redis
        await self._cache_result(user_id, backtest_id, response)

        logger.info(
            "RunBacktest completed: backtest_id=%s, results=%d, avg_sharpe=%.2f",
            backtest_id,
            len(results),
            portfolio_metrics.sharpe_ratio,
        )

        return response

    async def get_results(self, backtest_id: str, user_id: str = "") -> BacktestResult | None:
        """Retrieve cached backtest results.

        Args:
            backtest_id: Unique backtest identifier.

        Returns:
            BacktestResult if found, None otherwise.
        """
        if not backtest_id:
            return None

        cache_key = f"backtest:result:{user_id}:{backtest_id}"
        cached = await self.redis.get(cache_key)
        if cached is None:
            return None

        try:
            data = json.loads(cached) if isinstance(cached, str) else cached
            return BacktestResult.model_validate(data)
        except Exception as e:
            logger.warning("Failed to deserialize cached backtest %s: %s", backtest_id, e)
            return None

    async def compare_strategies(
        self,
        backtest_ids: list[str],
        user_id: str = "",
    ) -> dict:
        """Compare multiple backtest results.

        Ranks strategies by Sharpe ratio and identifies the best performer.

        Args:
            backtest_ids: List of backtest IDs to compare.

        Returns:
            Dict with 'comparisons' (ranked list) and 'best_strategy_id'.

        Raises:
            ValueError: If fewer than 2 backtest IDs are provided.
        """
        if len(backtest_ids) < 2:
            raise ValueError("At least 2 backtest_ids required for comparison")

        comparisons: list[BacktestComparison] = []

        for backtest_id in backtest_ids:
            cached = await self.get_results(backtest_id, user_id=user_id)
            if cached is not None:
                comparisons.append(
                    BacktestComparison(
                        backtest_id=backtest_id,
                        strategy_name=cached.strategy_type or "unknown",
                        metrics=cached.portfolio_metrics,
                        rank=0,
                    )
                )

        if not comparisons:
            raise ValueError("No valid backtests found for comparison")

        # Sort by Sharpe ratio (descending)
        comparisons.sort(key=lambda x: x.metrics.sharpe_ratio, reverse=True)
        for i, comparison in enumerate(comparisons):
            comparison.rank = i + 1

        best_strategy_id = comparisons[0].backtest_id

        logger.info(
            "CompareStrategies completed: %d strategies compared, best=%s",
            len(comparisons),
            best_strategy_id,
        )

        return {
            "comparisons": [c.model_dump() for c in comparisons],
            "best_strategy_id": best_strategy_id,
        }

    async def _cache_result(self, user_id: str, backtest_id: str, result: BacktestResult) -> None:
        """Cache backtest result in Redis.

        Args:
            backtest_id: Backtest identifier.
            result: BacktestResult to cache.
        """
        cache_key = f"backtest:result:{user_id}:{backtest_id}"
        try:
            await self.redis.setex(cache_key, _RESULT_CACHE_TTL, result.model_dump_json())
        except Exception as e:
            logger.warning("Failed to cache backtest %s: %s", backtest_id, e)
