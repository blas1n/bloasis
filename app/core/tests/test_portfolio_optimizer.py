"""Tests for Portfolio Optimizer -- mock riskfolio-lib."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.portfolio_optimizer import _MIN_BARS, PortfolioOptimizer


def _make_bars(n: int, base: float = 100.0, drift: float = 0.001) -> list[dict]:
    """Generate synthetic OHLCV bars with slight drift."""
    bars = []
    price = base
    for i in range(n):
        price = price * (1 + drift + 0.01 * (i % 3 - 1))
        bars.append(
            {
                "open": Decimal(str(round(price * 0.999, 4))),
                "high": Decimal(str(round(price * 1.01, 4))),
                "low": Decimal(str(round(price * 0.99, 4))),
                "close": Decimal(str(round(price, 4))),
                "volume": 1_000_000,
            }
        )
    return bars


@pytest.fixture
def optimizer():
    return PortfolioOptimizer()


@pytest.fixture
def ohlcv_data():
    """OHLCV data for 3 symbols with enough bars."""
    return {
        "AAPL": _make_bars(60, base=150.0, drift=0.001),
        "GOOGL": _make_bars(60, base=100.0, drift=0.0005),
        "MSFT": _make_bars(60, base=300.0, drift=0.0008),
    }


class TestOptimize:
    @patch("app.core.portfolio_optimizer.rp")
    def test_returns_weights_for_all_symbols(self, mock_rp, optimizer, ohlcv_data):
        """Optimizer should return weights for all requested symbols."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port

        weights_df = pd.DataFrame(
            {"weights": [0.4, 0.35, 0.25]},
            index=["AAPL", "GOOGL", "MSFT"],
        )
        mock_port.optimization.return_value = weights_df

        result = optimizer.optimize(["AAPL", "GOOGL", "MSFT"], ohlcv_data)

        assert "AAPL" in result
        assert "GOOGL" in result
        assert "MSFT" in result

    @patch("app.core.portfolio_optimizer.rp")
    def test_weights_are_decimal(self, mock_rp, optimizer, ohlcv_data):
        """All weights should be Decimal values."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port

        weights_df = pd.DataFrame(
            {"weights": [0.5, 0.5]},
            index=["AAPL", "GOOGL"],
        )
        mock_port.optimization.return_value = weights_df

        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        for weight in result.values():
            assert isinstance(weight, Decimal)

    @patch("app.core.portfolio_optimizer.rp")
    def test_weights_non_negative(self, mock_rp, optimizer, ohlcv_data):
        """All weights should be non-negative."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port

        weights_df = pd.DataFrame(
            {"weights": [0.6, 0.3, 0.1]},
            index=["AAPL", "GOOGL", "MSFT"],
        )
        mock_port.optimization.return_value = weights_df

        result = optimizer.optimize(["AAPL", "GOOGL", "MSFT"], ohlcv_data)

        for weight in result.values():
            assert weight >= Decimal("0")

    @patch("app.core.portfolio_optimizer.rp")
    def test_conservative_scales_down(self, mock_rp, optimizer, ohlcv_data):
        """Conservative profile should produce smaller weights than aggressive."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port

        weights_df = pd.DataFrame(
            {"weights": [0.5, 0.5]},
            index=["AAPL", "GOOGL"],
        )
        mock_port.optimization.return_value = weights_df

        conservative = optimizer.optimize(
            ["AAPL", "GOOGL"], ohlcv_data, risk_profile="CONSERVATIVE"
        )
        aggressive = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data, risk_profile="AGGRESSIVE")

        cons_total = sum(conservative.values())
        aggr_total = sum(aggressive.values())
        assert cons_total <= aggr_total

    @patch("app.core.portfolio_optimizer.rp")
    def test_weight_precision(self, mock_rp, optimizer, ohlcv_data):
        """Weights should be quantized to 4 decimal places."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port

        weights_df = pd.DataFrame(
            {"weights": [0.5, 0.5]},
            index=["AAPL", "GOOGL"],
        )
        mock_port.optimization.return_value = weights_df

        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        for weight in result.values():
            assert weight == weight.quantize(Decimal("0.0001"))


class TestEqualWeight:
    def test_two_symbols(self, optimizer):
        result = optimizer._equal_weight(["AAPL", "GOOGL"])
        assert result["AAPL"] == Decimal("0.5000")
        assert result["GOOGL"] == Decimal("0.5000")

    def test_three_symbols(self, optimizer):
        result = optimizer._equal_weight(["AAPL", "GOOGL", "MSFT"])
        for weight in result.values():
            assert abs(weight - Decimal("0.3333")) <= Decimal("0.0001")

    def test_empty(self, optimizer):
        assert optimizer._equal_weight([]) == {}


class TestFallbackBehavior:
    def test_insufficient_data_falls_back(self, optimizer):
        """Short data should trigger equal-weight fallback."""
        short_data = {
            "AAPL": _make_bars(10),
            "GOOGL": _make_bars(10),
        }
        result = optimizer.optimize(["AAPL", "GOOGL"], short_data)

        assert result["AAPL"] == result["GOOGL"]

    def test_single_symbol_falls_back(self, optimizer, ohlcv_data):
        """Single symbol can't be optimized; should fall back."""
        result = optimizer.optimize(["AAPL"], ohlcv_data)

        assert result["AAPL"] == Decimal("1.0000")

    def test_missing_data_falls_back(self, optimizer):
        """Missing OHLCV data should fall back to equal-weight."""
        result = optimizer.optimize(["AAPL", "GOOGL"], {})

        assert result["AAPL"] == Decimal("0.5000")
        assert result["GOOGL"] == Decimal("0.5000")

    @patch("app.core.portfolio_optimizer.rp")
    def test_optimization_failure_falls_back(self, mock_rp, optimizer, ohlcv_data):
        """Failed optimization should fall back to equal-weight."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port
        mock_port.optimization.side_effect = RuntimeError("Optimization failed")

        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        assert result["AAPL"] == result["GOOGL"]

    @patch("app.core.portfolio_optimizer.rp")
    def test_empty_weights_falls_back(self, mock_rp, optimizer, ohlcv_data):
        """Empty optimization result should fall back to equal-weight."""
        mock_port = MagicMock()
        mock_rp.Portfolio.return_value = mock_port
        mock_port.optimization.return_value = pd.DataFrame()

        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        assert result["AAPL"] == result["GOOGL"]


class TestBuildReturns:
    def test_builds_valid_dataframe(self, optimizer, ohlcv_data):
        """Should build a valid returns DataFrame."""
        df = optimizer._build_returns(["AAPL", "GOOGL"], ohlcv_data)

        assert df is not None
        assert "AAPL" in df.columns
        assert "GOOGL" in df.columns
        assert len(df) >= _MIN_BARS - 1

    def test_returns_none_for_insufficient_data(self, optimizer):
        """Should return None when data is too short."""
        short_data = {"AAPL": _make_bars(5), "GOOGL": _make_bars(5)}
        df = optimizer._build_returns(["AAPL", "GOOGL"], short_data)

        assert df is None

    def test_returns_none_for_single_symbol(self, optimizer, ohlcv_data):
        """Should return None when only one symbol has enough data."""
        df = optimizer._build_returns(["AAPL"], ohlcv_data)

        assert df is None
