"""Tests for BacktestingService -- mock VectorBT engine and market data."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.backtesting.models import (
    BacktestResult,
    PortfolioMetrics,
    SymbolResult,
)
from app.services.backtesting import BacktestingService


def _make_symbol_result(symbol: str = "AAPL", sharpe: float = 1.5) -> SymbolResult:
    return SymbolResult(
        symbol=symbol,
        total_return=0.25,
        sharpe_ratio=sharpe,
        sortino_ratio=2.0,
        max_drawdown=0.15,
        win_rate=0.55,
        profit_factor=1.8,
        total_trades=42,
        avg_trade_duration_days=5.5,
        calmar_ratio=1.67,
        passed=True,
    )


def _make_ohlcv_bars(n: int = 60) -> list[dict]:
    """Generate n valid OHLCV bars with sequential business dates."""
    import pandas as pd

    dates = pd.bdate_range("2024-01-02", periods=n, freq="B")
    return [
        {
            "timestamp": d.isoformat(),
            "open": Decimal("100"),
            "high": Decimal("105"),
            "low": Decimal("98"),
            "close": Decimal("102"),
            "volume": 1_000_000,
        }
        for d in dates
    ]


@pytest.fixture
def mock_market_data_svc():
    svc = AsyncMock()
    svc.get_ohlcv.return_value = _make_ohlcv_bars(60)
    return svc


@pytest.fixture
def backtesting_svc(mock_redis, mock_market_data_svc):
    with patch("app.services.backtesting.settings") as mock_settings:
        mock_settings.backtest_min_sharpe = 0.5
        mock_settings.backtest_max_drawdown = 0.30
        mock_settings.backtest_min_win_rate = 0.40
        mock_settings.backtest_default_cash = Decimal("100000.00")

        return BacktestingService(redis=mock_redis, market_data_svc=mock_market_data_svc)


class TestRunBacktest:
    @patch("app.core.backtesting.vectorbt_engine.vbt")
    async def test_ma_crossover_success(self, mock_vbt, backtesting_svc, mock_market_data_svc):
        """RunBacktest with ma_crossover should return results for all symbols."""
        import pandas as pd

        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma

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
        mock_vbt.Portfolio.from_signals.return_value = mock_portfolio

        result = await backtesting_svc.run_backtest(
            symbols=["AAPL", "MSFT"],
            strategy_type="ma_crossover",
            period="3mo",
        )

        assert isinstance(result, BacktestResult)
        assert result.backtest_id.startswith("backtest_")
        assert len(result.results) == 2
        assert result.created_at
        assert result.strategy_type == "ma_crossover"

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    async def test_rsi_success(self, mock_vbt, backtesting_svc):
        """RunBacktest with RSI strategy should work."""
        import pandas as pd

        mock_rsi = MagicMock()
        mock_rsi.rsi = pd.Series([50.0] * 60)
        mock_vbt.RSI.run.return_value = mock_rsi

        mock_portfolio = MagicMock()
        mock_portfolio.stats.return_value = {
            "Total Return [%]": 10.0,
            "Sharpe Ratio": 0.8,
            "Sortino Ratio": 1.0,
            "Max Drawdown [%]": -8.0,
            "Win Rate [%]": 50.0,
            "Profit Factor": 1.5,
            "Total Trades": 30,
            "Calmar Ratio": 1.0,
            "Avg Winning Trade Duration": pd.Timedelta(days=3),
        }
        mock_vbt.Portfolio.from_signals.return_value = mock_portfolio

        result = await backtesting_svc.run_backtest(
            symbols=["AAPL"],
            strategy_type="rsi",
        )

        assert len(result.results) == 1
        assert result.results[0].symbol == "AAPL"
        assert result.strategy_type == "rsi"

    async def test_empty_symbols_raises(self, backtesting_svc):
        """Empty symbols list should raise ValueError."""
        with pytest.raises(ValueError, match="At least one symbol"):
            await backtesting_svc.run_backtest(symbols=[], strategy_type="ma_crossover")

    async def test_invalid_strategy_raises(self, backtesting_svc):
        """Invalid strategy type should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid strategy_type"):
            await backtesting_svc.run_backtest(symbols=["AAPL"], strategy_type="invalid")

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    async def test_caches_result(self, mock_vbt, backtesting_svc, mock_redis):
        """Backtest results should be cached in Redis."""
        import pandas as pd

        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma

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
        mock_vbt.Portfolio.from_signals.return_value = mock_portfolio

        result = await backtesting_svc.run_backtest(
            symbols=["AAPL"],
            strategy_type="ma_crossover",
        )

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert f"backtest:result::{result.backtest_id}" == call_args[0][0]

    @patch("app.core.backtesting.vectorbt_engine.vbt")
    async def test_failed_symbol_continues(self, mock_vbt, backtesting_svc, mock_market_data_svc):
        """If one symbol fails, the rest should still be processed."""
        import pandas as pd

        # First call (AAPL) raises, second call (MSFT) succeeds
        call_count = 0

        async def get_ohlcv_side_effect(symbol, period="1y"):
            nonlocal call_count
            call_count += 1
            if symbol == "AAPL":
                raise RuntimeError("Data fetch failed")
            return _make_ohlcv_bars(60)

        mock_market_data_svc.get_ohlcv.side_effect = get_ohlcv_side_effect

        mock_ma = MagicMock()
        mock_ma.ma = pd.Series([100.0] * 60)
        mock_vbt.MA.run.return_value = mock_ma

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
        mock_vbt.Portfolio.from_signals.return_value = mock_portfolio

        result = await backtesting_svc.run_backtest(
            symbols=["AAPL", "MSFT"],
            strategy_type="ma_crossover",
        )

        # Only MSFT should have results
        assert len(result.results) == 1
        assert result.results[0].symbol == "MSFT"


class TestGetResults:
    async def test_returns_cached_result(self, backtesting_svc, mock_redis):
        """Should deserialize cached backtest result from Redis."""
        cached = BacktestResult(
            backtest_id="backtest_abc",
            results=[_make_symbol_result()],
            portfolio_metrics=PortfolioMetrics(
                total_return=0.25,
                sharpe_ratio=1.5,
                max_drawdown=0.15,
                volatility=0.05,
            ),
            created_at="2024-01-01T00:00:00Z",
            strategy_type="ma_crossover",
        )
        mock_redis.get.return_value = cached.model_dump_json()

        result = await backtesting_svc.get_results("backtest_abc")

        assert result is not None
        assert result.backtest_id == "backtest_abc"
        assert len(result.results) == 1

    async def test_returns_none_for_missing(self, backtesting_svc, mock_redis):
        """Should return None when backtest is not cached."""
        mock_redis.get.return_value = None

        result = await backtesting_svc.get_results("unknown_id")
        assert result is None

    async def test_returns_none_for_empty_id(self, backtesting_svc):
        """Should return None for empty backtest_id."""
        result = await backtesting_svc.get_results("")
        assert result is None

    async def test_handles_corrupt_cache(self, backtesting_svc, mock_redis):
        """Should return None for corrupt cached data."""
        mock_redis.get.return_value = "not valid json {"

        result = await backtesting_svc.get_results("backtest_corrupt")
        assert result is None


class TestCompareStrategies:
    async def test_compare_two_backtests(self, backtesting_svc, mock_redis):
        """Should rank two backtests by Sharpe ratio."""
        bt1 = BacktestResult(
            backtest_id="bt_1",
            results=[_make_symbol_result("AAPL", sharpe=1.5)],
            portfolio_metrics=PortfolioMetrics(sharpe_ratio=1.5),
            created_at="2024-01-01T00:00:00Z",
            strategy_type="ma_crossover",
        )
        bt2 = BacktestResult(
            backtest_id="bt_2",
            results=[_make_symbol_result("AAPL", sharpe=2.0)],
            portfolio_metrics=PortfolioMetrics(sharpe_ratio=2.0),
            created_at="2024-01-01T00:00:00Z",
            strategy_type="rsi",
        )

        async def mock_get(key):
            if "bt_1" in key:
                return bt1.model_dump_json()
            elif "bt_2" in key:
                return bt2.model_dump_json()
            return None

        mock_redis.get.side_effect = mock_get

        result = await backtesting_svc.compare_strategies(["bt_1", "bt_2"])

        assert len(result["comparisons"]) == 2
        assert result["best_strategy_id"] == "bt_2"
        # bt_2 has higher Sharpe, so rank 1
        assert result["comparisons"][0]["rank"] == 1
        assert result["comparisons"][0]["backtest_id"] == "bt_2"

    async def test_fewer_than_two_ids_raises(self, backtesting_svc):
        """Should raise ValueError for fewer than 2 IDs."""
        with pytest.raises(ValueError, match="At least 2"):
            await backtesting_svc.compare_strategies(["single_id"])

    async def test_no_valid_backtests_raises(self, backtesting_svc, mock_redis):
        """Should raise ValueError when no backtests are found."""
        mock_redis.get.return_value = None

        with pytest.raises(ValueError, match="No valid backtests"):
            await backtesting_svc.compare_strategies(["unknown_1", "unknown_2"])
