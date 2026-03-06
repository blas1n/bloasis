"""Tests for backtesting metrics utilities -- pure computation, no mocks needed."""

import pytest

from app.core.backtesting.metrics import MetricsCalculator
from app.core.backtesting.models import PortfolioMetrics, SymbolResult


class TestCalculatePortfolioMetrics:
    def test_valid_results(self):
        """Portfolio metrics should be computed correctly from symbol results."""
        results = [
            SymbolResult(
                symbol="AAPL",
                total_return=0.25,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                max_drawdown=0.15,
                win_rate=0.55,
                profit_factor=1.8,
                total_trades=42,
                avg_trade_duration_days=5.5,
                calmar_ratio=1.67,
                passed=True,
            ),
            SymbolResult(
                symbol="MSFT",
                total_return=0.15,
                sharpe_ratio=1.0,
                sortino_ratio=1.5,
                max_drawdown=0.20,
                win_rate=0.50,
                profit_factor=1.5,
                total_trades=38,
                avg_trade_duration_days=6.0,
                calmar_ratio=0.75,
                passed=True,
            ),
        ]

        metrics = MetricsCalculator.calculate_portfolio_metrics(results)

        assert isinstance(metrics, PortfolioMetrics)
        assert metrics.total_return == pytest.approx(0.20, rel=1e-2)
        assert metrics.sharpe_ratio == pytest.approx(1.25, rel=1e-2)
        assert metrics.max_drawdown == 0.20
        assert metrics.volatility > 0

    def test_empty_results(self):
        """Empty results should return zeroed metrics."""
        metrics = MetricsCalculator.calculate_portfolio_metrics([])

        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.volatility == 0.0

    def test_single_result(self):
        """Single result should have zero volatility."""
        results = [
            SymbolResult(
                symbol="AAPL",
                total_return=0.30,
                sharpe_ratio=2.0,
                sortino_ratio=2.5,
                max_drawdown=0.10,
                win_rate=0.60,
                profit_factor=2.0,
                total_trades=50,
                avg_trade_duration_days=4.0,
                calmar_ratio=3.0,
                passed=True,
            ),
        ]

        metrics = MetricsCalculator.calculate_portfolio_metrics(results)

        assert metrics.total_return == 0.30
        assert metrics.sharpe_ratio == 2.0
        assert metrics.max_drawdown == 0.10
        assert metrics.volatility == 0.0


class TestCalculateSharpeRatio:
    def test_positive_returns(self):
        """Mostly positive returns should produce a positive Sharpe ratio."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns)

        assert isinstance(sharpe, float)
        assert sharpe > 0

    def test_empty_returns(self):
        assert MetricsCalculator.calculate_sharpe_ratio([]) == 0.0

    def test_single_return(self):
        assert MetricsCalculator.calculate_sharpe_ratio([0.01]) == 0.0

    def test_no_annualize(self):
        """Non-annualized Sharpe should be smaller than annualized."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]
        sharpe_no_ann = MetricsCalculator.calculate_sharpe_ratio(returns, annualize=False)
        sharpe_ann = MetricsCalculator.calculate_sharpe_ratio(returns, annualize=True)

        assert abs(sharpe_no_ann) < abs(sharpe_ann)


class TestCalculateSortinoRatio:
    def test_with_negative_returns(self):
        returns = [0.01, 0.02, -0.005, 0.015, -0.008, 0.003]
        sortino = MetricsCalculator.calculate_sortino_ratio(returns)
        assert isinstance(sortino, float)

    def test_no_negative_returns(self):
        """All positive returns should produce 0 Sortino (no downside)."""
        returns = [0.01, 0.02, 0.015, 0.008]
        assert MetricsCalculator.calculate_sortino_ratio(returns) == 0.0

    def test_empty_returns(self):
        assert MetricsCalculator.calculate_sortino_ratio([]) == 0.0


class TestCalculateMaxDrawdown:
    def test_valid_cumulative_returns(self):
        cumulative = [1.0, 1.1, 1.05, 0.95, 1.0, 1.15, 1.1]
        max_dd = MetricsCalculator.calculate_max_drawdown(cumulative)

        assert isinstance(max_dd, float)
        expected_dd = (1.1 - 0.95) / 1.1
        assert max_dd == pytest.approx(expected_dd, rel=0.01)

    def test_empty_returns(self):
        assert MetricsCalculator.calculate_max_drawdown([]) == 0.0

    def test_single_value(self):
        assert MetricsCalculator.calculate_max_drawdown([1.0]) == 0.0


class TestCalculateCalmarRatio:
    def test_normal_case(self):
        assert MetricsCalculator.calculate_calmar_ratio(0.20, 0.10) == 2.0

    def test_zero_drawdown(self):
        assert MetricsCalculator.calculate_calmar_ratio(0.20, 0.0) == 0.0


class TestCalculateWinRate:
    def test_mixed_trades(self):
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
            {"pnl": -30},
            {"pnl": 150},
        ]
        assert MetricsCalculator.calculate_win_rate(trades) == 0.6

    def test_all_winners(self):
        trades = [{"pnl": 100}, {"pnl": 200}, {"pnl": 150}]
        assert MetricsCalculator.calculate_win_rate(trades) == 1.0

    def test_all_losers(self):
        trades = [{"pnl": -100}, {"pnl": -200}]
        assert MetricsCalculator.calculate_win_rate(trades) == 0.0

    def test_empty_trades(self):
        assert MetricsCalculator.calculate_win_rate([]) == 0.0


class TestCalculateProfitFactor:
    def test_normal_case(self):
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
            {"pnl": -100},
            {"pnl": 150},
        ]
        # Gross profit = 450, Gross loss = 150
        assert MetricsCalculator.calculate_profit_factor(trades) == 3.0

    def test_no_losses(self):
        trades = [{"pnl": 100}, {"pnl": 200}]
        assert MetricsCalculator.calculate_profit_factor(trades) == float("inf")

    def test_empty_trades(self):
        assert MetricsCalculator.calculate_profit_factor([]) == 0.0
