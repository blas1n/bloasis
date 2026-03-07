"""Tests for VectorBT Engine -- pure computation, mock vectorbt."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core.backtesting.models import BacktestConfig, SymbolResult
from app.core.backtesting.vectorbt_engine import VectorBTEngine


@pytest.fixture
def engine():
    return VectorBTEngine(min_sharpe=0.5, max_drawdown=0.30, min_win_rate=0.40)


@pytest.fixture
def default_config():
    return BacktestConfig(
        initial_cash=Decimal("100000.00"),
        commission=0.001,
        slippage=0.001,
    )


@pytest.fixture
def sample_ohlcv():
    """Generate sample OHLCV data with enough bars for testing."""
    bars = []
    price = 100.0
    for i in range(60):
        price = price * (1 + 0.001 + 0.01 * (i % 3 - 1))
        bars.append(
            {
                "timestamp": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
                "open": Decimal(str(round(price * 0.999, 2))),
                "high": Decimal(str(round(price * 1.01, 2))),
                "low": Decimal(str(round(price * 0.99, 2))),
                "close": Decimal(str(round(price, 2))),
                "volume": 1_000_000,
            }
        )
    return bars


def _make_mock_portfolio():
    """Create a mock VectorBT Portfolio object."""
    mock_portfolio = MagicMock()
    mock_portfolio.stats.return_value = {
        "Total Return [%]": 15.0,
        "Sharpe Ratio": 1.2,
        "Sortino Ratio": 1.5,
        "Max Drawdown [%]": -12.0,
        "Win Rate [%]": 55.0,
        "Profit Factor": 1.8,
        "Total Trades": 42,
        "Calmar Ratio": 1.25,
        "Avg Winning Trade Duration": pd.Timedelta(days=5),
    }
    return mock_portfolio


class TestBacktestMACrossover:
    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_returns_valid_symbol_result(self, mock_vbt, engine, sample_ohlcv, default_config):
        """MA Crossover backtest should return a valid SymbolResult."""
        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        result = engine.backtest_ma_crossover(
            symbol="AAPL",
            ohlcv=sample_ohlcv,
            backtest_config=default_config,
        )

        assert isinstance(result, SymbolResult)
        assert result.symbol == "AAPL"
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.passed, bool)

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_custom_windows(self, mock_vbt, engine, sample_ohlcv, default_config):
        """MA Crossover should accept custom window parameters."""
        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        result = engine.backtest_ma_crossover(
            symbol="AAPL",
            ohlcv=sample_ohlcv,
            backtest_config=default_config,
            fast_window=5,
            slow_window=20,
        )

        assert result.symbol == "AAPL"
        assert mock_vbt.MA.run.call_count == 2


class TestBacktestRSI:
    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_returns_valid_symbol_result(self, mock_vbt, engine, sample_ohlcv, default_config):
        """RSI backtest should return a valid SymbolResult."""
        mock_rsi = MagicMock()
        mock_rsi.rsi = pd.Series([50.0] * 60)
        mock_vbt.RSI.run.return_value = mock_rsi
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        result = engine.backtest_rsi(
            symbol="MSFT",
            ohlcv=sample_ohlcv,
            backtest_config=default_config,
        )

        assert isinstance(result, SymbolResult)
        assert result.symbol == "MSFT"

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_custom_rsi_params(self, mock_vbt, engine, sample_ohlcv, default_config):
        """RSI backtest should accept custom RSI parameters."""
        mock_rsi = MagicMock()
        mock_rsi.rsi = pd.Series([50.0] * 60)
        mock_vbt.RSI.run.return_value = mock_rsi
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        result = engine.backtest_rsi(
            symbol="MSFT",
            ohlcv=sample_ohlcv,
            backtest_config=default_config,
            rsi_window=21,
            oversold=25,
            overbought=75,
        )

        assert result.symbol == "MSFT"


class TestEmptyData:
    def test_ma_crossover_empty_data(self, engine, default_config):
        """MA Crossover should handle empty OHLCV data gracefully."""
        result = engine.backtest_ma_crossover(
            symbol="EMPTY",
            ohlcv=[],
            backtest_config=default_config,
        )

        assert result.symbol == "EMPTY"
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.passed is False

    def test_rsi_empty_data(self, engine, default_config):
        """RSI should handle empty OHLCV data gracefully."""
        result = engine.backtest_rsi(
            symbol="EMPTY",
            ohlcv=[],
            backtest_config=default_config,
        )

        assert result.symbol == "EMPTY"
        assert result.total_return == 0.0
        assert result.passed is False


class TestStopLossTakeProfit:
    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_with_stop_loss_take_profit(self, mock_vbt, engine, sample_ohlcv):
        """Backtest should pass stop loss/take profit to Portfolio.from_signals."""
        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        config = BacktestConfig(
            initial_cash=Decimal("50000"),
            commission=0.002,
            slippage=0.002,
            stop_loss=0.05,
            take_profit=0.10,
        )

        engine.backtest_ma_crossover(
            symbol="AAPL",
            ohlcv=sample_ohlcv,
            backtest_config=config,
        )

        call_kwargs = mock_vbt.Portfolio.from_signals.call_args[1]
        assert call_kwargs["sl_stop"] == 0.05
        assert call_kwargs["tp_stop"] == 0.10

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    def test_disabled_stop_loss_take_profit(self, mock_vbt, engine, sample_ohlcv, default_config):
        """Zero stop loss/take profit should be passed as None."""
        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma
        mock_vbt.Portfolio.from_signals.return_value = _make_mock_portfolio()

        engine.backtest_ma_crossover(
            symbol="AAPL",
            ohlcv=sample_ohlcv,
            backtest_config=default_config,
        )

        call_kwargs = mock_vbt.Portfolio.from_signals.call_args[1]
        assert call_kwargs["sl_stop"] is None
        assert call_kwargs["tp_stop"] is None


class TestToDataframe:
    def test_converts_ohlcv_to_dataframe(self, engine):
        """Should convert OHLCV data to DataFrame with timestamp index."""
        ohlcv = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": Decimal("100.0"),
                "high": Decimal("105.0"),
                "low": Decimal("98.0"),
                "close": Decimal("102.0"),
                "volume": 1_000_000,
            },
            {
                "timestamp": "2024-01-02T00:00:00Z",
                "open": Decimal("102.0"),
                "high": Decimal("108.0"),
                "low": Decimal("101.0"),
                "close": Decimal("107.0"),
                "volume": 1_200_000,
            },
        ]

        df = engine._to_dataframe(ohlcv)

        assert len(df) == 2
        assert "open" in df.columns
        assert "close" in df.columns
        assert df.index.name == "timestamp"
        # Verify Decimal -> float conversion
        assert df["close"].dtype == np.float64

    def test_empty_list_returns_empty_dataframe(self, engine):
        """Empty OHLCV list should return empty DataFrame."""
        df = engine._to_dataframe([])
        assert df.empty


class TestCheckPassed:
    def test_all_criteria_met(self, engine):
        """Should pass when all criteria are met."""
        assert engine._check_passed(sharpe=1.0, max_dd=0.20, win_rate=0.50) is True

    def test_sharpe_below_threshold(self, engine):
        """Should fail when Sharpe is below threshold."""
        assert engine._check_passed(sharpe=0.3, max_dd=0.20, win_rate=0.50) is False

    def test_max_drawdown_exceeds_threshold(self, engine):
        """Should fail when max drawdown exceeds threshold."""
        assert engine._check_passed(sharpe=1.0, max_dd=0.35, win_rate=0.50) is False

    def test_win_rate_below_threshold(self, engine):
        """Should fail when win rate is below threshold."""
        assert engine._check_passed(sharpe=1.0, max_dd=0.20, win_rate=0.35) is False


class TestCreateEmptyResult:
    def test_creates_zeroed_result(self, engine):
        """Should create result with all zero values and passed=False."""
        result = engine._create_empty_result("TEST")

        assert result.symbol == "TEST"
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown == 0.0
        assert result.passed is False


class TestSafeGet:
    def test_valid_value(self, engine):
        stats = {"Sharpe Ratio": 1.5}
        assert engine._safe_get(stats, "Sharpe Ratio", 0.0) == 1.5

    def test_missing_key(self, engine):
        stats = {"Other Key": 1.5}
        assert engine._safe_get(stats, "Sharpe Ratio", 0.0) == 0.0

    def test_nan_value(self, engine):
        stats = {"Sharpe Ratio": np.nan}
        assert engine._safe_get(stats, "Sharpe Ratio", -1.0) == -1.0

    def test_inf_value(self, engine):
        stats = {"Sharpe Ratio": np.inf}
        assert engine._safe_get(stats, "Sharpe Ratio", -1.0) == -1.0
