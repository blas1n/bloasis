"""VectorBT-based backtesting engine.

Provides vectorized backtesting for technical strategies:
- Moving Average Crossover
- RSI Overbought/Oversold

Pure computation module -- receives OHLCV data directly as list[dict].
No I/O, no service clients.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from .models import BacktestConfig, SymbolResult

# Lazy import: vectorbt is a heavy optional dependency.
# Imported at first use to allow module to load without it installed.
vbt: Any = None


def _get_vbt() -> Any:
    """Lazy-load vectorbt module."""
    global vbt  # noqa: PLW0603
    if vbt is None:
        import vectorbt as _vbt

        vbt = _vbt
    return vbt


logger = logging.getLogger(__name__)


class VectorBTEngine:
    """VectorBT-based backtesting engine.

    Args:
        min_sharpe: Minimum Sharpe ratio for pass/fail.
        max_drawdown: Maximum drawdown threshold for pass/fail.
        min_win_rate: Minimum win rate for pass/fail.
    """

    def __init__(
        self,
        min_sharpe: float = 0.5,
        max_drawdown: float = 0.30,
        min_win_rate: float = 0.40,
    ) -> None:
        self.min_sharpe = min_sharpe
        self.max_drawdown = max_drawdown
        self.min_win_rate = min_win_rate

    def backtest_ma_crossover(
        self,
        symbol: str,
        ohlcv: list[dict],
        backtest_config: BacktestConfig,
        fast_window: int = 10,
        slow_window: int = 50,
    ) -> SymbolResult:
        """Run Moving Average Crossover backtest.

        Entry signal: Fast MA crosses above Slow MA
        Exit signal: Fast MA crosses below Slow MA

        Args:
            symbol: Stock ticker symbol.
            ohlcv: OHLCV bars (keys: timestamp, open, high, low, close, volume).
            backtest_config: Backtest configuration.
            fast_window: Fast moving average window.
            slow_window: Slow moving average window.

        Returns:
            SymbolResult with backtest metrics.
        """
        logger.info("Running MA Crossover backtest for %s", symbol)

        df = self._to_dataframe(ohlcv)
        if df.empty:
            logger.warning("No data available for %s", symbol)
            return self._create_empty_result(symbol)

        close = df["close"]

        _vbt = _get_vbt()
        # Calculate moving averages
        sma_fast = _vbt.MA.run(close, fast_window).ma
        sma_slow = _vbt.MA.run(close, slow_window).ma

        # Generate entry/exit signals
        entries = sma_fast > sma_slow
        exits = sma_fast < sma_slow

        # Run portfolio backtest
        portfolio = self._run_portfolio_backtest(close, entries, exits, backtest_config)
        return self._extract_results(symbol, portfolio)

    def backtest_rsi(
        self,
        symbol: str,
        ohlcv: list[dict],
        backtest_config: BacktestConfig,
        rsi_window: int = 14,
        oversold: int = 30,
        overbought: int = 70,
    ) -> SymbolResult:
        """Run RSI Overbought/Oversold backtest.

        Entry signal: RSI crosses below oversold threshold
        Exit signal: RSI crosses above overbought threshold

        Args:
            symbol: Stock ticker symbol.
            ohlcv: OHLCV bars (keys: timestamp, open, high, low, close, volume).
            backtest_config: Backtest configuration.
            rsi_window: RSI calculation window.
            oversold: Oversold threshold (buy signal).
            overbought: Overbought threshold (sell signal).

        Returns:
            SymbolResult with backtest metrics.
        """
        logger.info("Running RSI backtest for %s", symbol)

        df = self._to_dataframe(ohlcv)
        if df.empty:
            logger.warning("No data available for %s", symbol)
            return self._create_empty_result(symbol)

        close = df["close"]

        _vbt = _get_vbt()
        # Calculate RSI
        rsi = _vbt.RSI.run(close, window=rsi_window).rsi

        # Generate entry/exit signals
        entries = rsi < oversold
        exits = rsi > overbought

        # Run portfolio backtest
        portfolio = self._run_portfolio_backtest(close, entries, exits, backtest_config)
        return self._extract_results(symbol, portfolio)

    def _run_portfolio_backtest(
        self,
        close: pd.Series,
        entries: pd.Series,
        exits: pd.Series,
        backtest_config: BacktestConfig,
    ) -> Any:
        """Run VectorBT portfolio backtest.

        Args:
            close: Close prices series.
            entries: Entry signals series.
            exits: Exit signals series.
            backtest_config: Backtest configuration.

        Returns:
            VectorBT Portfolio object with results.
        """
        sl_stop = backtest_config.stop_loss if backtest_config.stop_loss > 0 else None
        tp_stop = backtest_config.take_profit if backtest_config.take_profit > 0 else None

        _vbt = _get_vbt()
        portfolio = _vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=float(backtest_config.initial_cash),
            fees=backtest_config.commission,
            slippage=backtest_config.slippage,
            sl_stop=sl_stop,
            tp_stop=tp_stop,
            freq="1D",
        )
        return portfolio

    def _extract_results(self, symbol: str, portfolio: Any) -> SymbolResult:
        """Extract backtest results from VectorBT portfolio.

        Args:
            symbol: Stock ticker symbol.
            portfolio: VectorBT Portfolio object.

        Returns:
            SymbolResult with all metrics.
        """
        stats = portfolio.stats()

        total_return = self._safe_get(stats, "Total Return [%]", 0) / 100
        sharpe = self._safe_get(stats, "Sharpe Ratio", 0)
        sortino = self._safe_get(stats, "Sortino Ratio", 0)
        max_dd = abs(self._safe_get(stats, "Max Drawdown [%]", 0)) / 100
        win_rate = self._safe_get(stats, "Win Rate [%]", 0) / 100
        profit_factor = self._safe_get(stats, "Profit Factor", 0)
        total_trades = int(self._safe_get(stats, "Total Trades", 0))
        calmar = self._safe_get(stats, "Calmar Ratio", 0)

        avg_duration = self._calc_avg_duration(stats)
        passed = self._check_passed(sharpe, max_dd, win_rate)

        return SymbolResult(
            symbol=symbol,
            total_return=float(total_return),
            sharpe_ratio=float(sharpe),
            sortino_ratio=float(sortino),
            max_drawdown=float(max_dd),
            win_rate=float(win_rate),
            profit_factor=float(profit_factor) if not np.isinf(profit_factor) else 0.0,
            total_trades=total_trades,
            avg_trade_duration_days=avg_duration,
            calmar_ratio=float(calmar) if not np.isinf(calmar) else 0.0,
            passed=passed,
        )

    def _safe_get(self, stats: dict, key: str, default: float) -> float:
        """Safely get value from stats dict.

        Args:
            stats: Stats dictionary.
            key: Key to look up.
            default: Default value if key not found or value is NaN.

        Returns:
            Float value.
        """
        value = stats.get(key, default)
        if pd.isna(value) or np.isinf(value):
            return default
        return float(value)

    def _calc_avg_duration(self, stats: dict) -> float:
        """Calculate average trade duration in days.

        Args:
            stats: VectorBT stats dictionary.

        Returns:
            Average duration in days.
        """
        duration = stats.get("Avg Winning Trade Duration", pd.Timedelta(0))
        if isinstance(duration, pd.Timedelta):
            return duration.total_seconds() / 86400
        return 0.0

    def _check_passed(self, sharpe: float, max_dd: float, win_rate: float) -> bool:
        """Check if strategy passes minimum criteria.

        Args:
            sharpe: Sharpe ratio.
            max_dd: Maximum drawdown.
            win_rate: Win rate.

        Returns:
            True if all criteria are met.
        """
        return (
            sharpe >= self.min_sharpe
            and max_dd <= self.max_drawdown
            and win_rate >= self.min_win_rate
        )

    def _create_empty_result(self, symbol: str) -> SymbolResult:
        """Create empty result for cases with no data.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            SymbolResult with zero values.
        """
        return SymbolResult(
            symbol=symbol,
            total_return=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            avg_trade_duration_days=0.0,
            calmar_ratio=0.0,
            passed=False,
        )

    def _to_dataframe(self, ohlcv: list[dict]) -> pd.DataFrame:
        """Convert OHLCV data to DataFrame.

        Converts Decimal values to float for numpy/vectorbt compatibility.

        Args:
            ohlcv: List of OHLCV bar dictionaries with keys:
                   timestamp, open, high, low, close, volume.

        Returns:
            pandas DataFrame with timestamp index and float columns.
        """
        if not ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(ohlcv)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df = df.sort_index()

        # Convert Decimal values to float for numpy/vectorbt
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = df[col].astype(float)

        return df
