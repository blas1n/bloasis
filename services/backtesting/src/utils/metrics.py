"""Performance metrics calculation utilities.

Provides functions for calculating portfolio and trading metrics.
"""

import logging

import numpy as np

from ..models import PortfolioMetrics, SymbolResult

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """Calculator for portfolio-level metrics."""

    @staticmethod
    def calculate_portfolio_metrics(results: list[SymbolResult]) -> PortfolioMetrics:
        """Calculate aggregated portfolio metrics from symbol results.

        Args:
            results: List of SymbolResult objects

        Returns:
            PortfolioMetrics with aggregated metrics
        """
        if not results:
            return PortfolioMetrics(
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                volatility=0.0,
            )

        # Extract metrics from results
        returns = [r.total_return for r in results]
        sharpes = [r.sharpe_ratio for r in results]
        drawdowns = [r.max_drawdown for r in results]

        # Calculate averages
        avg_return = np.mean(returns) if returns else 0.0
        avg_sharpe = np.mean(sharpes) if sharpes else 0.0

        # Max drawdown is the worst (maximum) across all symbols
        max_dd = max(drawdowns) if drawdowns else 0.0

        # Volatility is std dev of returns
        volatility = np.std(returns) if len(returns) > 1 else 0.0

        return PortfolioMetrics(
            total_return=float(avg_return),
            sharpe_ratio=float(avg_sharpe),
            max_drawdown=float(max_dd),
            volatility=float(volatility),
        )

    @staticmethod
    def calculate_sharpe_ratio(
        returns: list[float], risk_free_rate: float = 0.0, annualize: bool = True
    ) -> float:
        """Calculate Sharpe ratio from a list of returns.

        Args:
            returns: List of period returns
            risk_free_rate: Risk-free rate (annualized if annualize=True)
            annualize: Whether to annualize the result (assumes daily returns)

        Returns:
            Sharpe ratio
        """
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate / 252

        std = np.std(excess_returns)
        if std == 0:
            return 0.0

        sharpe = np.mean(excess_returns) / std

        if annualize:
            sharpe *= np.sqrt(252)

        return float(sharpe)

    @staticmethod
    def calculate_sortino_ratio(
        returns: list[float], risk_free_rate: float = 0.0, annualize: bool = True
    ) -> float:
        """Calculate Sortino ratio from a list of returns.

        Unlike Sharpe, Sortino only considers downside volatility.

        Args:
            returns: List of period returns
            risk_free_rate: Risk-free rate
            annualize: Whether to annualize the result

        Returns:
            Sortino ratio
        """
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate / 252

        # Calculate downside deviation (only negative returns)
        downside_returns = excess_returns[excess_returns < 0]
        if len(downside_returns) == 0:
            return 0.0

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return 0.0

        sortino = np.mean(excess_returns) / downside_std

        if annualize:
            sortino *= np.sqrt(252)

        return float(sortino)

    @staticmethod
    def calculate_max_drawdown(cumulative_returns: list[float]) -> float:
        """Calculate maximum drawdown from cumulative returns.

        Args:
            cumulative_returns: List of cumulative returns (1.0 = starting value)

        Returns:
            Maximum drawdown as a positive percentage
        """
        if not cumulative_returns or len(cumulative_returns) < 2:
            return 0.0

        cumulative = np.array(cumulative_returns)
        running_max = np.maximum.accumulate(cumulative)

        drawdowns = (cumulative - running_max) / running_max
        max_dd = np.min(drawdowns)

        return float(abs(max_dd))

    @staticmethod
    def calculate_calmar_ratio(annual_return: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio.

        Args:
            annual_return: Annualized return
            max_drawdown: Maximum drawdown (positive percentage)

        Returns:
            Calmar ratio
        """
        if max_drawdown == 0:
            return 0.0

        return float(annual_return / max_drawdown)

    @staticmethod
    def calculate_win_rate(trades: list[dict]) -> float:
        """Calculate win rate from trade list.

        Args:
            trades: List of trade dictionaries with 'pnl' key

        Returns:
            Win rate as percentage (0-1)
        """
        if not trades:
            return 0.0

        winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
        return float(winning_trades / len(trades))

    @staticmethod
    def calculate_profit_factor(trades: list[dict]) -> float:
        """Calculate profit factor from trade list.

        Args:
            trades: List of trade dictionaries with 'pnl' key

        Returns:
            Profit factor (gross profits / gross losses)
        """
        if not trades:
            return 0.0

        gross_profit = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))

        if gross_loss == 0:
            return 0.0

        return float(gross_profit / gross_loss)
