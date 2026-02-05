"""Tests for metrics utilities."""

import pytest

from src.models import PortfolioMetrics, SymbolResult
from src.utils.metrics import MetricsCalculator


class TestMetricsCalculator:
    """Tests for MetricsCalculator class."""

    def test_calculate_portfolio_metrics_success(self):
        """Test portfolio metrics calculation with valid results."""
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
        assert metrics.max_drawdown == 0.20  # Max of all drawdowns
        assert metrics.volatility > 0

    def test_calculate_portfolio_metrics_empty_results(self):
        """Test portfolio metrics with empty results list."""
        metrics = MetricsCalculator.calculate_portfolio_metrics([])

        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.volatility == 0.0

    def test_calculate_portfolio_metrics_single_result(self):
        """Test portfolio metrics with single result."""
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
        # Single result has no volatility
        assert metrics.volatility == 0.0

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns)

        assert isinstance(sharpe, float)
        # With mostly positive returns, should be positive
        assert sharpe > 0

    def test_calculate_sharpe_ratio_empty(self):
        """Test Sharpe ratio with empty returns."""
        sharpe = MetricsCalculator.calculate_sharpe_ratio([])
        assert sharpe == 0.0

    def test_calculate_sharpe_ratio_single_return(self):
        """Test Sharpe ratio with single return."""
        sharpe = MetricsCalculator.calculate_sharpe_ratio([0.01])
        assert sharpe == 0.0

    def test_calculate_sharpe_ratio_no_annualize(self):
        """Test Sharpe ratio without annualization."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns, annualize=False)

        # Non-annualized should be smaller in absolute terms
        annualized_sharpe = MetricsCalculator.calculate_sharpe_ratio(returns, annualize=True)
        assert abs(sharpe) < abs(annualized_sharpe)

    def test_calculate_sortino_ratio(self):
        """Test Sortino ratio calculation."""
        returns = [0.01, 0.02, -0.005, 0.015, -0.008, 0.003]
        sortino = MetricsCalculator.calculate_sortino_ratio(returns)

        assert isinstance(sortino, float)

    def test_calculate_sortino_ratio_no_negative_returns(self):
        """Test Sortino ratio with no negative returns."""
        returns = [0.01, 0.02, 0.015, 0.008]
        sortino = MetricsCalculator.calculate_sortino_ratio(returns)

        # Should return 0 when no downside
        assert sortino == 0.0

    def test_calculate_sortino_ratio_empty(self):
        """Test Sortino ratio with empty returns."""
        sortino = MetricsCalculator.calculate_sortino_ratio([])
        assert sortino == 0.0

    def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        cumulative = [1.0, 1.1, 1.05, 0.95, 1.0, 1.15, 1.1]
        max_dd = MetricsCalculator.calculate_max_drawdown(cumulative)

        assert isinstance(max_dd, float)
        # Should find the 1.1 to 0.95 drawdown
        expected_dd = (1.1 - 0.95) / 1.1  # approximately 0.136
        assert max_dd == pytest.approx(expected_dd, rel=0.01)

    def test_calculate_max_drawdown_empty(self):
        """Test max drawdown with empty returns."""
        max_dd = MetricsCalculator.calculate_max_drawdown([])
        assert max_dd == 0.0

    def test_calculate_max_drawdown_single(self):
        """Test max drawdown with single value."""
        max_dd = MetricsCalculator.calculate_max_drawdown([1.0])
        assert max_dd == 0.0

    def test_calculate_calmar_ratio(self):
        """Test Calmar ratio calculation."""
        calmar = MetricsCalculator.calculate_calmar_ratio(annual_return=0.20, max_drawdown=0.10)

        assert calmar == 2.0

    def test_calculate_calmar_ratio_zero_drawdown(self):
        """Test Calmar ratio with zero drawdown."""
        calmar = MetricsCalculator.calculate_calmar_ratio(annual_return=0.20, max_drawdown=0.0)

        assert calmar == 0.0

    def test_calculate_win_rate(self):
        """Test win rate calculation."""
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
            {"pnl": -30},
            {"pnl": 150},
        ]
        win_rate = MetricsCalculator.calculate_win_rate(trades)

        assert win_rate == 0.6  # 3 winning out of 5

    def test_calculate_win_rate_all_winners(self):
        """Test win rate with all winning trades."""
        trades = [{"pnl": 100}, {"pnl": 200}, {"pnl": 150}]
        win_rate = MetricsCalculator.calculate_win_rate(trades)

        assert win_rate == 1.0

    def test_calculate_win_rate_all_losers(self):
        """Test win rate with all losing trades."""
        trades = [{"pnl": -100}, {"pnl": -200}, {"pnl": -150}]
        win_rate = MetricsCalculator.calculate_win_rate(trades)

        assert win_rate == 0.0

    def test_calculate_win_rate_empty(self):
        """Test win rate with no trades."""
        win_rate = MetricsCalculator.calculate_win_rate([])
        assert win_rate == 0.0

    def test_calculate_profit_factor(self):
        """Test profit factor calculation."""
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
            {"pnl": -100},
            {"pnl": 150},
        ]
        pf = MetricsCalculator.calculate_profit_factor(trades)

        # Gross profit = 450, Gross loss = 150
        assert pf == 3.0

    def test_calculate_profit_factor_no_losses(self):
        """Test profit factor with no losing trades."""
        trades = [{"pnl": 100}, {"pnl": 200}]
        pf = MetricsCalculator.calculate_profit_factor(trades)

        assert pf == 0.0  # Can't divide by zero

    def test_calculate_profit_factor_empty(self):
        """Test profit factor with no trades."""
        pf = MetricsCalculator.calculate_profit_factor([])
        assert pf == 0.0
