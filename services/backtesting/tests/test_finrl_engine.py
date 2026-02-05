"""Tests for FinRL Engine."""

import numpy as np
import pandas as pd
import pytest

from src.engines.finrl_engine import FinRLEngine
from src.models import BacktestConfig, SymbolResult


class TestFinRLEngine:
    """Tests for FinRLEngine class."""

    @pytest.mark.asyncio
    async def test_backtest_rl_ppo_success(
        self, finrl_engine: FinRLEngine, default_backtest_config: BacktestConfig
    ):
        """Test PPO backtest returns valid results."""
        results = await finrl_engine.backtest_rl(
            symbols=["AAPL", "MSFT"],
            backtest_config=default_backtest_config,
            algorithm="ppo",
            period="6mo",
            train_timesteps=1000,  # Low for testing
        )

        assert isinstance(results, list)
        assert len(results) == 2
        for result in results:
            assert isinstance(result, SymbolResult)
            assert result.symbol in ["AAPL", "MSFT"]

    @pytest.mark.asyncio
    async def test_backtest_rl_a2c_success(
        self, finrl_engine: FinRLEngine, default_backtest_config: BacktestConfig
    ):
        """Test A2C backtest returns valid results."""
        results = await finrl_engine.backtest_rl(
            symbols=["AAPL"],
            backtest_config=default_backtest_config,
            algorithm="a2c",
            period="3mo",
            train_timesteps=1000,
        )

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_backtest_rl_sac_success(
        self, finrl_engine: FinRLEngine, default_backtest_config: BacktestConfig
    ):
        """Test SAC backtest returns valid results."""
        results = await finrl_engine.backtest_rl(
            symbols=["MSFT"],
            backtest_config=default_backtest_config,
            algorithm="sac",
            period="3mo",
            train_timesteps=1000,
        )

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].symbol == "MSFT"

    @pytest.mark.asyncio
    async def test_backtest_rl_unsupported_algorithm(
        self, finrl_engine: FinRLEngine, default_backtest_config: BacktestConfig
    ):
        """Test backtest raises error for unsupported algorithm."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            await finrl_engine.backtest_rl(
                symbols=["AAPL"],
                backtest_config=default_backtest_config,
                algorithm="invalid_algo",
                period="3mo",
            )

    @pytest.mark.asyncio
    async def test_backtest_rl_empty_data(
        self, mock_market_data_client, default_backtest_config: BacktestConfig
    ):
        """Test backtest handles empty data gracefully."""
        mock_market_data_client.get_ohlcv.return_value = []
        engine = FinRLEngine(mock_market_data_client)

        results = await engine.backtest_rl(
            symbols=["EMPTY"],
            backtest_config=default_backtest_config,
            algorithm="ppo",
        )

        assert len(results) == 1
        assert results[0].symbol == "EMPTY"
        assert results[0].total_return == 0.0
        assert results[0].passed is False

    def test_calculate_macd(self, finrl_engine: FinRLEngine):
        """Test MACD calculation."""
        close = pd.Series([100, 102, 104, 103, 105, 107, 106, 108, 110, 109])
        macd = finrl_engine._calculate_macd(close, fast=3, slow=5)

        assert isinstance(macd, pd.Series)
        assert len(macd) == len(close)

    def test_calculate_rsi(self, finrl_engine: FinRLEngine):
        """Test RSI calculation."""
        close = pd.Series([100, 102, 101, 103, 102, 104, 105, 103, 106, 107])
        rsi = finrl_engine._calculate_rsi(close, window=5)

        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(close)
        # RSI should be between 0 and 100
        assert all(0 <= v <= 100 for v in rsi.dropna())

    def test_calculate_cci(self, finrl_engine: FinRLEngine):
        """Test CCI calculation."""
        df = pd.DataFrame(
            {
                "high": [102, 104, 103, 105, 106, 108, 107, 109, 110, 112],
                "low": [98, 100, 99, 101, 102, 104, 103, 105, 106, 108],
                "close": [100, 102, 101, 103, 104, 106, 105, 107, 108, 110],
            }
        )
        cci = finrl_engine._calculate_cci(df, window=5)

        assert isinstance(cci, pd.Series)
        assert len(cci) == len(df)

    def test_calculate_dx(self, finrl_engine: FinRLEngine):
        """Test DX calculation."""
        df = pd.DataFrame(
            {
                "high": [102, 104, 103, 105, 106, 108, 107, 109, 110, 112],
                "low": [98, 100, 99, 101, 102, 104, 103, 105, 106, 108],
                "close": [100, 102, 101, 103, 104, 106, 105, 107, 108, 110],
            }
        )
        dx = finrl_engine._calculate_dx(df, window=5)

        assert isinstance(dx, pd.Series)
        assert len(dx) == len(df)

    def test_calculate_sharpe_positive_returns(self, finrl_engine: FinRLEngine):
        """Test Sharpe ratio calculation with positive returns."""
        returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.008])
        sharpe = finrl_engine._calculate_sharpe(returns)

        assert isinstance(sharpe, float)
        # With mostly positive returns, Sharpe should be positive
        assert sharpe > 0

    def test_calculate_sharpe_empty_returns(self, finrl_engine: FinRLEngine):
        """Test Sharpe ratio with empty returns."""
        returns = pd.Series([], dtype=float)
        sharpe = finrl_engine._calculate_sharpe(returns)

        assert sharpe == 0.0

    def test_calculate_sharpe_zero_std(self, finrl_engine: FinRLEngine):
        """Test Sharpe ratio with zero standard deviation."""
        returns = pd.Series([0.01, 0.01, 0.01, 0.01])
        sharpe = finrl_engine._calculate_sharpe(returns)

        # Zero std should return 0
        assert sharpe == 0.0

    def test_calculate_max_drawdown(self, finrl_engine: FinRLEngine):
        """Test max drawdown calculation."""
        returns = pd.Series([0.01, -0.02, -0.01, 0.03, -0.05, 0.02])
        max_dd = finrl_engine._calculate_max_drawdown(returns)

        assert isinstance(max_dd, float)
        assert max_dd <= 0  # Drawdown should be negative

    def test_calculate_max_drawdown_empty(self, finrl_engine: FinRLEngine):
        """Test max drawdown with empty returns."""
        returns = pd.Series([], dtype=float)
        max_dd = finrl_engine._calculate_max_drawdown(returns)

        assert max_dd == 0.0

    def test_create_empty_result(self, finrl_engine: FinRLEngine):
        """Test empty result creation."""
        result = finrl_engine._create_empty_result("TEST")

        assert result.symbol == "TEST"
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.passed is False

    def test_add_technical_indicators(self, finrl_engine: FinRLEngine):
        """Test adding technical indicators to DataFrame."""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=50, freq="D"),
                "tic": ["AAPL"] * 50,
                "open": np.random.uniform(100, 110, 50),
                "high": np.random.uniform(110, 120, 50),
                "low": np.random.uniform(90, 100, 50),
                "close": np.random.uniform(100, 110, 50),
                "volume": np.random.randint(1000000, 2000000, 50),
            }
        )

        result = finrl_engine._add_technical_indicators(df)

        assert "macd" in result.columns
        assert "rsi_30" in result.columns
        assert "cci_30" in result.columns
        assert "dx_30" in result.columns

    @pytest.mark.asyncio
    async def test_prepare_data(self, finrl_engine: FinRLEngine):
        """Test data preparation for FinRL format."""
        df = await finrl_engine._prepare_data(["AAPL"], "3mo")

        assert isinstance(df, pd.DataFrame)
        assert "date" in df.columns
        assert "tic" in df.columns
        assert "close" in df.columns
        # Technical indicators should be added
        assert "macd" in df.columns

    @pytest.mark.asyncio
    async def test_algorithm_case_insensitive(
        self, finrl_engine: FinRLEngine, default_backtest_config: BacktestConfig
    ):
        """Test algorithm name is case insensitive."""
        results = await finrl_engine.backtest_rl(
            symbols=["AAPL"],
            backtest_config=default_backtest_config,
            algorithm="PPO",  # Uppercase
            period="3mo",
            train_timesteps=1000,
        )

        assert len(results) == 1
        assert results[0].symbol == "AAPL"
