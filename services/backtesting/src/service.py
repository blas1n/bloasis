"""Backtesting Service - gRPC Servicer Implementation.

Implements backtesting capabilities:
- VectorBT backtesting (MA Crossover, RSI)
- FinRL backtesting (PPO, A2C, SAC)
- Performance metrics calculation
- Strategy comparison
"""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import grpc

from shared.generated import backtesting_pb2, backtesting_pb2_grpc

from .clients.market_data_client import MarketDataClient
from .engines.finrl_engine import FinRLEngine
from .engines.vectorbt_engine import VectorBTEngine
from .models import BacktestComparison, BacktestConfig, BacktestResponse, PortfolioMetrics
from .utils.metrics import MetricsCalculator

logger = logging.getLogger(__name__)


class BacktestingServicer(backtesting_pb2_grpc.BacktestingServiceServicer):
    """gRPC servicer implementing Backtesting Service."""

    def __init__(self, market_data_client: MarketDataClient):
        """Initialize Backtesting servicer.

        Args:
            market_data_client: Market Data Service gRPC client
        """
        self.market_data = market_data_client
        self.vectorbt_engine = VectorBTEngine(market_data_client)
        self.finrl_engine = FinRLEngine(market_data_client)
        self.metrics_calculator = MetricsCalculator()

        # In-memory results cache (in production, use Redis or database)
        self.results_cache: dict[str, BacktestResponse] = {}

        logger.info("Backtesting servicer initialized")

    def _proto_config_to_model(
        self, proto_config: backtesting_pb2.BacktestConfig
    ) -> BacktestConfig:
        """Convert proto BacktestConfig to Pydantic model.

        Args:
            proto_config: Proto config message

        Returns:
            BacktestConfig Pydantic model
        """
        return BacktestConfig(
            initial_cash=Decimal(str(proto_config.initial_cash))
            if proto_config.initial_cash > 0
            else Decimal("100000.00"),
            commission=proto_config.commission if proto_config.commission > 0 else 0.001,
            slippage=proto_config.slippage if proto_config.slippage > 0 else 0.001,
            stop_loss=proto_config.stop_loss,
            take_profit=proto_config.take_profit,
        )

    def _model_to_proto_symbol_result(self, result) -> backtesting_pb2.SymbolResult:
        """Convert Pydantic SymbolResult to proto message.

        Args:
            result: SymbolResult Pydantic model

        Returns:
            Proto SymbolResult message
        """
        return backtesting_pb2.SymbolResult(
            symbol=result.symbol,
            total_return=result.total_return,
            sharpe_ratio=result.sharpe_ratio,
            sortino_ratio=result.sortino_ratio,
            max_drawdown=result.max_drawdown,
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            total_trades=result.total_trades,
            avg_trade_duration_days=result.avg_trade_duration_days,
            calmar_ratio=result.calmar_ratio,
            passed=result.passed,
        )

    def _model_to_proto_portfolio_metrics(
        self, metrics: PortfolioMetrics
    ) -> backtesting_pb2.PortfolioMetrics:
        """Convert Pydantic PortfolioMetrics to proto message.

        Args:
            metrics: PortfolioMetrics Pydantic model

        Returns:
            Proto PortfolioMetrics message
        """
        return backtesting_pb2.PortfolioMetrics(
            total_return=metrics.total_return,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown,
            volatility=metrics.volatility,
        )

    async def RunBacktest(  # noqa: N802
        self,
        request: backtesting_pb2.BacktestRequest,
        context: grpc.aio.ServicerContext,
    ) -> backtesting_pb2.BacktestResponse:
        """Run VectorBT backtest for technical strategies.

        Args:
            request: BacktestRequest with symbols, strategy_type, config, period
            context: gRPC context

        Returns:
            BacktestResponse with results
        """
        try:
            user_id = request.user_id
            symbols = list(request.symbols)
            strategy_type = request.strategy_type.lower()
            period = request.period or "1y"

            if not symbols:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("At least one symbol is required")
                return backtesting_pb2.BacktestResponse()

            if strategy_type not in ["ma_crossover", "rsi", "custom"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(
                    f"Invalid strategy_type: {strategy_type}. Supported: ma_crossover, rsi, custom"
                )
                return backtesting_pb2.BacktestResponse()

            logger.info(
                f"RunBacktest: user={user_id}, symbols={symbols}, "
                f"strategy={strategy_type}, period={period}"
            )

            # Convert config
            backtest_config = self._proto_config_to_model(request.config)

            # Run backtest for each symbol
            results = []
            for symbol in symbols:
                try:
                    if strategy_type == "ma_crossover":
                        result = await self.vectorbt_engine.backtest_ma_crossover(
                            symbol=symbol,
                            backtest_config=backtest_config,
                            period=period,
                        )
                    elif strategy_type == "rsi":
                        result = await self.vectorbt_engine.backtest_rsi(
                            symbol=symbol,
                            backtest_config=backtest_config,
                            period=period,
                        )
                    else:
                        # Custom strategy - default to MA crossover for now
                        result = await self.vectorbt_engine.backtest_ma_crossover(
                            symbol=symbol,
                            backtest_config=backtest_config,
                            period=period,
                        )

                    results.append(result)

                except Exception as e:
                    logger.error(f"Backtest failed for {symbol}: {e}")
                    # Skip failed symbols, continue with others
                    continue

            # Calculate portfolio metrics
            portfolio_metrics = self.metrics_calculator.calculate_portfolio_metrics(results)

            # Generate backtest ID and timestamp
            backtest_id = f"backtest_{uuid4()}"
            created_at = datetime.utcnow().isoformat() + "Z"

            # Create response
            response = BacktestResponse(
                backtest_id=backtest_id,
                results=results,
                portfolio_metrics=portfolio_metrics,
                created_at=created_at,
                strategy_type=strategy_type,
            )

            # Cache result
            self.results_cache[backtest_id] = response

            # Convert to proto
            proto_results = [self._model_to_proto_symbol_result(r) for r in results]
            proto_metrics = self._model_to_proto_portfolio_metrics(portfolio_metrics)

            logger.info(
                f"RunBacktest completed: backtest_id={backtest_id}, "
                f"results={len(results)}, avg_sharpe={portfolio_metrics.sharpe_ratio:.2f}"
            )

            return backtesting_pb2.BacktestResponse(
                backtest_id=backtest_id,
                results=proto_results,
                portfolio_metrics=proto_metrics,
                created_at=created_at,
            )

        except ConnectionError as e:
            logger.error(f"Service unavailable: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Market Data Service unavailable")
            return backtesting_pb2.BacktestResponse()

        except TimeoutError as e:
            logger.error(f"Service timeout: {e}")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Market Data Service request timed out")
            return backtesting_pb2.BacktestResponse()

        except Exception as e:
            logger.error(f"RunBacktest error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return backtesting_pb2.BacktestResponse()

    async def RunRLBacktest(  # noqa: N802
        self,
        request: backtesting_pb2.RLBacktestRequest,
        context: grpc.aio.ServicerContext,
    ) -> backtesting_pb2.BacktestResponse:
        """Run FinRL reinforcement learning backtest.

        Args:
            request: RLBacktestRequest with symbols, algorithm, config, timesteps
            context: gRPC context

        Returns:
            BacktestResponse with results
        """
        try:
            user_id = request.user_id
            symbols = list(request.symbols)
            algorithm = request.rl_algorithm.lower()
            period = request.period or "1y"
            train_timesteps = request.train_timesteps or 50000

            if not symbols:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("At least one symbol is required")
                return backtesting_pb2.BacktestResponse()

            if algorithm not in ["ppo", "a2c", "sac"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(f"Invalid rl_algorithm: {algorithm}. Supported: ppo, a2c, sac")
                return backtesting_pb2.BacktestResponse()

            logger.info(
                f"RunRLBacktest: user={user_id}, symbols={symbols}, "
                f"algorithm={algorithm}, timesteps={train_timesteps}"
            )

            # Convert config
            backtest_config = self._proto_config_to_model(request.config)

            # Run RL backtest
            results = await self.finrl_engine.backtest_rl(
                symbols=symbols,
                backtest_config=backtest_config,
                algorithm=algorithm,
                period=period,
                train_timesteps=train_timesteps,
            )

            # Calculate portfolio metrics
            portfolio_metrics = self.metrics_calculator.calculate_portfolio_metrics(results)

            # Generate backtest ID and timestamp
            backtest_id = f"rl_backtest_{uuid4()}"
            created_at = datetime.utcnow().isoformat() + "Z"

            # Create response
            response = BacktestResponse(
                backtest_id=backtest_id,
                results=results,
                portfolio_metrics=portfolio_metrics,
                created_at=created_at,
                strategy_type=f"rl_{algorithm}",
            )

            # Cache result
            self.results_cache[backtest_id] = response

            # Convert to proto
            proto_results = [self._model_to_proto_symbol_result(r) for r in results]
            proto_metrics = self._model_to_proto_portfolio_metrics(portfolio_metrics)

            logger.info(
                f"RunRLBacktest completed: backtest_id={backtest_id}, "
                f"results={len(results)}, avg_sharpe={portfolio_metrics.sharpe_ratio:.2f}"
            )

            return backtesting_pb2.BacktestResponse(
                backtest_id=backtest_id,
                results=proto_results,
                portfolio_metrics=proto_metrics,
                created_at=created_at,
            )

        except ConnectionError as e:
            logger.error(f"Service unavailable: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Market Data Service unavailable")
            return backtesting_pb2.BacktestResponse()

        except TimeoutError as e:
            logger.error(f"Service timeout: {e}")
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Market Data Service request timed out")
            return backtesting_pb2.BacktestResponse()

        except ValueError as e:
            logger.error(f"Invalid parameter: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return backtesting_pb2.BacktestResponse()

        except Exception as e:
            logger.error(f"RunRLBacktest error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return backtesting_pb2.BacktestResponse()

    async def GetBacktestResults(  # noqa: N802
        self,
        request: backtesting_pb2.GetResultsRequest,
        context: grpc.aio.ServicerContext,
    ) -> backtesting_pb2.GetResultsResponse:
        """Retrieve results of a completed backtest.

        Args:
            request: GetResultsRequest with backtest_id
            context: gRPC context

        Returns:
            GetResultsResponse with backtest results
        """
        try:
            backtest_id = request.backtest_id

            if not backtest_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("backtest_id is required")
                return backtesting_pb2.GetResultsResponse()

            logger.info(f"GetBacktestResults: backtest_id={backtest_id}")

            # Look up cached result
            cached_result = self.results_cache.get(backtest_id)

            if not cached_result:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Backtest not found: {backtest_id}")
                return backtesting_pb2.GetResultsResponse()

            # Convert to proto
            proto_results = [self._model_to_proto_symbol_result(r) for r in cached_result.results]
            proto_metrics = self._model_to_proto_portfolio_metrics(cached_result.portfolio_metrics)

            backtest_response = backtesting_pb2.BacktestResponse(
                backtest_id=cached_result.backtest_id,
                results=proto_results,
                portfolio_metrics=proto_metrics,
                created_at=cached_result.created_at,
            )

            return backtesting_pb2.GetResultsResponse(results=backtest_response)

        except Exception as e:
            logger.error(f"GetBacktestResults error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return backtesting_pb2.GetResultsResponse()

    async def CompareStrategies(  # noqa: N802
        self,
        request: backtesting_pb2.CompareRequest,
        context: grpc.aio.ServicerContext,
    ) -> backtesting_pb2.CompareResponse:
        """Compare multiple backtest results.

        Ranks strategies by Sharpe ratio and identifies the best performer.

        Args:
            request: CompareRequest with backtest_ids
            context: gRPC context

        Returns:
            CompareResponse with ranked comparisons
        """
        try:
            backtest_ids = list(request.backtest_ids)

            if len(backtest_ids) < 2:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("At least 2 backtest_ids required for comparison")
                return backtesting_pb2.CompareResponse()

            logger.info(f"CompareStrategies: backtest_ids={backtest_ids}")

            # Gather comparison data
            comparisons: list[BacktestComparison] = []

            for backtest_id in backtest_ids:
                cached_result = self.results_cache.get(backtest_id)
                if cached_result:
                    comparisons.append(
                        BacktestComparison(
                            backtest_id=backtest_id,
                            strategy_name=cached_result.strategy_type or "unknown",
                            metrics=cached_result.portfolio_metrics,
                            rank=0,  # Will be set after sorting
                        )
                    )

            if not comparisons:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("No valid backtests found for comparison")
                return backtesting_pb2.CompareResponse()

            # Sort by Sharpe ratio (descending)
            comparisons.sort(key=lambda x: x.metrics.sharpe_ratio, reverse=True)

            # Assign ranks
            for i, comparison in enumerate(comparisons):
                comparison.rank = i + 1

            # Best strategy is rank 1
            best_strategy_id = comparisons[0].backtest_id

            # Convert to proto
            proto_comparisons = [
                backtesting_pb2.BacktestComparison(
                    backtest_id=c.backtest_id,
                    strategy_name=c.strategy_name,
                    metrics=self._model_to_proto_portfolio_metrics(c.metrics),
                    rank=c.rank,
                )
                for c in comparisons
            ]

            logger.info(
                f"CompareStrategies completed: {len(comparisons)} strategies compared, "
                f"best={best_strategy_id}"
            )

            return backtesting_pb2.CompareResponse(
                comparisons=proto_comparisons,
                best_strategy_id=best_strategy_id,
            )

        except Exception as e:
            logger.error(f"CompareStrategies error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return backtesting_pb2.CompareResponse()
