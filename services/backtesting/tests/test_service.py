"""Tests for Backtesting Service."""

from decimal import Decimal

import pytest

from shared.generated import backtesting_pb2
from src.models import BacktestConfig, BacktestResponse, PortfolioMetrics, SymbolResult
from src.service import BacktestingServicer


class TestBacktestingServicer:
    """Tests for BacktestingServicer class."""

    @pytest.mark.asyncio
    async def test_run_backtest_ma_crossover_success(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunBacktest with MA Crossover strategy."""
        request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL", "MSFT"],
            strategy_type="ma_crossover",
            config=backtesting_pb2.BacktestConfig(
                initial_cash=100000.0,
                commission=0.001,
                slippage=0.001,
            ),
            period="3mo",
        )

        response = await backtesting_servicer.RunBacktest(request, mock_grpc_context)

        assert response.backtest_id.startswith("backtest_")
        assert len(response.results) == 2
        assert response.created_at
        mock_grpc_context.set_code.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_backtest_rsi_success(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunBacktest with RSI strategy."""
        request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="rsi",
            config=backtesting_pb2.BacktestConfig(
                initial_cash=50000.0,
                commission=0.002,
            ),
            period="1y",
        )

        response = await backtesting_servicer.RunBacktest(request, mock_grpc_context)

        assert response.backtest_id.startswith("backtest_")
        assert len(response.results) == 1
        assert response.results[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_run_backtest_empty_symbols(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunBacktest fails with empty symbols."""
        request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=[],
            strategy_type="ma_crossover",
        )

        await backtesting_servicer.RunBacktest(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_run_backtest_invalid_strategy(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunBacktest fails with invalid strategy type."""
        request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="invalid_strategy",
        )

        await backtesting_servicer.RunBacktest(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_run_rl_backtest_ppo_success(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunRLBacktest with PPO algorithm."""
        request = backtesting_pb2.RLBacktestRequest(
            user_id="test_user",
            symbols=["AAPL", "MSFT"],
            rl_algorithm="ppo",
            config=backtesting_pb2.BacktestConfig(
                initial_cash=100000.0,
                commission=0.001,
            ),
            train_timesteps=1000,
            period="6mo",
        )

        response = await backtesting_servicer.RunRLBacktest(request, mock_grpc_context)

        assert response.backtest_id.startswith("rl_backtest_")
        assert len(response.results) == 2
        mock_grpc_context.set_code.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_rl_backtest_invalid_algorithm(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunRLBacktest fails with invalid algorithm."""
        request = backtesting_pb2.RLBacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            rl_algorithm="invalid_algo",
        )

        await backtesting_servicer.RunRLBacktest(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_run_rl_backtest_empty_symbols(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test RunRLBacktest fails with empty symbols."""
        request = backtesting_pb2.RLBacktestRequest(
            user_id="test_user",
            symbols=[],
            rl_algorithm="ppo",
        )

        await backtesting_servicer.RunRLBacktest(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_backtest_results_success(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test GetBacktestResults retrieves cached result."""
        # First run a backtest
        run_request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="ma_crossover",
            period="3mo",
        )
        run_response = await backtesting_servicer.RunBacktest(run_request, mock_grpc_context)
        backtest_id = run_response.backtest_id

        # Then retrieve results
        get_request = backtesting_pb2.GetResultsRequest(backtest_id=backtest_id)
        get_response = await backtesting_servicer.GetBacktestResults(get_request, mock_grpc_context)

        assert get_response.results.backtest_id == backtest_id
        assert len(get_response.results.results) == 1

    @pytest.mark.asyncio
    async def test_get_backtest_results_not_found(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test GetBacktestResults returns error for unknown ID."""
        request = backtesting_pb2.GetResultsRequest(backtest_id="unknown_id")

        await backtesting_servicer.GetBacktestResults(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_backtest_results_empty_id(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test GetBacktestResults fails with empty ID."""
        request = backtesting_pb2.GetResultsRequest(backtest_id="")

        await backtesting_servicer.GetBacktestResults(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_compare_strategies_success(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test CompareStrategies compares multiple backtests."""
        # Run two backtests
        request1 = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="ma_crossover",
            period="3mo",
        )
        response1 = await backtesting_servicer.RunBacktest(request1, mock_grpc_context)

        request2 = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="rsi",
            period="3mo",
        )
        response2 = await backtesting_servicer.RunBacktest(request2, mock_grpc_context)

        # Compare them
        compare_request = backtesting_pb2.CompareRequest(
            backtest_ids=[response1.backtest_id, response2.backtest_id]
        )
        compare_response = await backtesting_servicer.CompareStrategies(
            compare_request, mock_grpc_context
        )

        assert len(compare_response.comparisons) == 2
        assert compare_response.best_strategy_id
        # Verify ranking
        assert compare_response.comparisons[0].rank == 1
        assert compare_response.comparisons[1].rank == 2

    @pytest.mark.asyncio
    async def test_compare_strategies_single_backtest(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test CompareStrategies fails with single backtest."""
        request = backtesting_pb2.CompareRequest(backtest_ids=["single_id"])

        await backtesting_servicer.CompareStrategies(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_compare_strategies_no_valid_backtests(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test CompareStrategies fails when no valid backtests found."""
        request = backtesting_pb2.CompareRequest(backtest_ids=["unknown_id_1", "unknown_id_2"])

        await backtesting_servicer.CompareStrategies(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    def test_proto_config_to_model(self, backtesting_servicer: BacktestingServicer):
        """Test proto config conversion to Pydantic model."""
        proto_config = backtesting_pb2.BacktestConfig(
            initial_cash=50000.0,
            commission=0.002,
            slippage=0.001,
            stop_loss=0.05,
            take_profit=0.10,
        )

        model = backtesting_servicer._proto_config_to_model(proto_config)

        assert isinstance(model, BacktestConfig)
        assert model.initial_cash == Decimal("50000.0")
        assert model.commission == 0.002
        assert model.slippage == 0.001
        assert model.stop_loss == 0.05
        assert model.take_profit == 0.10

    def test_proto_config_to_model_defaults(self, backtesting_servicer: BacktestingServicer):
        """Test proto config uses defaults for zero values."""
        proto_config = backtesting_pb2.BacktestConfig(
            initial_cash=0.0,  # Zero - should use default
            commission=0.0,  # Zero - should use default
        )

        model = backtesting_servicer._proto_config_to_model(proto_config)

        assert model.initial_cash == Decimal("100000.00")
        assert model.commission == 0.001

    def test_model_to_proto_symbol_result(
        self, backtesting_servicer: BacktestingServicer, sample_symbol_result: SymbolResult
    ):
        """Test SymbolResult model conversion to proto."""
        proto = backtesting_servicer._model_to_proto_symbol_result(sample_symbol_result)

        assert proto.symbol == "AAPL"
        assert proto.total_return == 0.25
        assert proto.sharpe_ratio == 1.5
        assert proto.max_drawdown == 0.15
        assert proto.passed is True

    def test_model_to_proto_portfolio_metrics(
        self, backtesting_servicer: BacktestingServicer, sample_portfolio_metrics: PortfolioMetrics
    ):
        """Test PortfolioMetrics model conversion to proto."""
        proto = backtesting_servicer._model_to_proto_portfolio_metrics(sample_portfolio_metrics)

        assert proto.total_return == 0.20
        assert proto.sharpe_ratio == 1.2
        assert proto.max_drawdown == 0.18
        assert proto.volatility == 0.05


class TestResultsCaching:
    """Tests for results caching functionality."""

    @pytest.mark.asyncio
    async def test_results_cached_after_backtest(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test that backtest results are cached."""
        request = backtesting_pb2.BacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            strategy_type="ma_crossover",
            period="3mo",
        )

        response = await backtesting_servicer.RunBacktest(request, mock_grpc_context)
        backtest_id = response.backtest_id

        # Verify cached
        assert backtest_id in backtesting_servicer.results_cache
        cached = backtesting_servicer.results_cache[backtest_id]
        assert isinstance(cached, BacktestResponse)
        assert cached.backtest_id == backtest_id

    @pytest.mark.asyncio
    async def test_rl_results_cached_after_backtest(
        self, backtesting_servicer: BacktestingServicer, mock_grpc_context
    ):
        """Test that RL backtest results are cached."""
        request = backtesting_pb2.RLBacktestRequest(
            user_id="test_user",
            symbols=["AAPL"],
            rl_algorithm="ppo",
            train_timesteps=1000,
            period="3mo",
        )

        response = await backtesting_servicer.RunRLBacktest(request, mock_grpc_context)
        backtest_id = response.backtest_id

        # Verify cached
        assert backtest_id in backtesting_servicer.results_cache
        cached = backtesting_servicer.results_cache[backtest_id]
        assert cached.strategy_type == "rl_ppo"
