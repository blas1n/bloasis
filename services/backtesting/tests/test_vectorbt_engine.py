"""Tests for VectorBT Engine."""

import pytest

from src.engines.vectorbt_engine import VectorBTEngine
from src.models import BacktestConfig, SymbolResult


class TestVectorBTEngine:
    """Tests for VectorBTEngine class."""

    @pytest.mark.asyncio
    async def test_backtest_ma_crossover_success(
        self, vectorbt_engine: VectorBTEngine, default_backtest_config: BacktestConfig
    ):
        """Test MA Crossover backtest returns valid results."""
        result = await vectorbt_engine.backtest_ma_crossover(
            symbol="AAPL",
            backtest_config=default_backtest_config,
            period="3mo",
            fast_window=10,
            slow_window=50,
        )

        assert isinstance(result, SymbolResult)
        assert result.symbol == "AAPL"
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown, float)
        assert result.max_drawdown >= 0  # Drawdown is absolute value
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_backtest_rsi_success(
        self, vectorbt_engine: VectorBTEngine, default_backtest_config: BacktestConfig
    ):
        """Test RSI backtest returns valid results."""
        result = await vectorbt_engine.backtest_rsi(
            symbol="MSFT",
            backtest_config=default_backtest_config,
            period="3mo",
            rsi_window=14,
            oversold=30,
            overbought=70,
        )

        assert isinstance(result, SymbolResult)
        assert result.symbol == "MSFT"
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)

    @pytest.mark.asyncio
    async def test_backtest_with_stop_loss_take_profit(self, vectorbt_engine: VectorBTEngine):
        """Test backtest with stop loss and take profit configured."""
        config = BacktestConfig(
            initial_cash=50000,
            commission=0.002,
            slippage=0.002,
            stop_loss=0.05,  # 5% stop loss
            take_profit=0.10,  # 10% take profit
        )

        result = await vectorbt_engine.backtest_ma_crossover(
            symbol="AAPL",
            backtest_config=config,
            period="1y",
        )

        assert isinstance(result, SymbolResult)
        assert result.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_backtest_empty_data(
        self, mock_market_data_client, default_backtest_config: BacktestConfig
    ):
        """Test backtest handles empty data gracefully."""
        mock_market_data_client.get_ohlcv.return_value = []
        engine = VectorBTEngine(mock_market_data_client)

        result = await engine.backtest_ma_crossover(
            symbol="EMPTY",
            backtest_config=default_backtest_config,
            period="1y",
        )

        assert result.symbol == "EMPTY"
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.passed is False

    def test_to_dataframe_conversion(self, vectorbt_engine: VectorBTEngine):
        """Test OHLCV data conversion to DataFrame."""
        ohlcv_data = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 1000000,
            },
            {
                "timestamp": "2024-01-02T00:00:00Z",
                "open": 102.0,
                "high": 108.0,
                "low": 101.0,
                "close": 107.0,
                "volume": 1200000,
            },
        ]

        df = vectorbt_engine._to_dataframe(ohlcv_data)

        assert len(df) == 2
        assert "open" in df.columns
        assert "close" in df.columns
        assert df.index.name == "timestamp"

    def test_to_dataframe_empty_list(self, vectorbt_engine: VectorBTEngine):
        """Test DataFrame conversion with empty list."""
        df = vectorbt_engine._to_dataframe([])
        assert df.empty

    def test_check_passed_all_criteria_met(self, vectorbt_engine: VectorBTEngine):
        """Test pass/fail check when all criteria are met."""
        passed = vectorbt_engine._check_passed(
            sharpe=1.0,  # >= 0.5
            max_dd=0.20,  # <= 0.30
            win_rate=0.50,  # >= 0.40
        )
        assert passed is True

    def test_check_passed_sharpe_below_threshold(self, vectorbt_engine: VectorBTEngine):
        """Test pass/fail check when Sharpe is below threshold."""
        passed = vectorbt_engine._check_passed(
            sharpe=0.3,  # Below 0.5 threshold
            max_dd=0.20,
            win_rate=0.50,
        )
        assert passed is False

    def test_check_passed_max_drawdown_exceeds_threshold(self, vectorbt_engine: VectorBTEngine):
        """Test pass/fail check when max drawdown exceeds threshold."""
        passed = vectorbt_engine._check_passed(
            sharpe=1.0,
            max_dd=0.35,  # Exceeds 0.30 threshold
            win_rate=0.50,
        )
        assert passed is False

    def test_check_passed_win_rate_below_threshold(self, vectorbt_engine: VectorBTEngine):
        """Test pass/fail check when win rate is below threshold."""
        passed = vectorbt_engine._check_passed(
            sharpe=1.0,
            max_dd=0.20,
            win_rate=0.35,  # Below 0.40 threshold
        )
        assert passed is False

    def test_create_empty_result(self, vectorbt_engine: VectorBTEngine):
        """Test empty result creation."""
        result = vectorbt_engine._create_empty_result("TEST")

        assert result.symbol == "TEST"
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown == 0.0
        assert result.passed is False

    def test_safe_get_with_valid_value(self, vectorbt_engine: VectorBTEngine):
        """Test safe get with valid value."""
        stats = {"Sharpe Ratio": 1.5}
        value = vectorbt_engine._safe_get(stats, "Sharpe Ratio", 0.0)
        assert value == 1.5

    def test_safe_get_with_missing_key(self, vectorbt_engine: VectorBTEngine):
        """Test safe get with missing key."""
        stats = {"Other Key": 1.5}
        value = vectorbt_engine._safe_get(stats, "Sharpe Ratio", 0.0)
        assert value == 0.0

    def test_safe_get_with_nan_value(self, vectorbt_engine: VectorBTEngine):
        """Test safe get with NaN value."""
        import numpy as np

        stats = {"Sharpe Ratio": np.nan}
        value = vectorbt_engine._safe_get(stats, "Sharpe Ratio", -1.0)
        assert value == -1.0

    def test_safe_get_with_inf_value(self, vectorbt_engine: VectorBTEngine):
        """Test safe get with infinite value."""
        import numpy as np

        stats = {"Sharpe Ratio": np.inf}
        value = vectorbt_engine._safe_get(stats, "Sharpe Ratio", -1.0)
        assert value == -1.0
