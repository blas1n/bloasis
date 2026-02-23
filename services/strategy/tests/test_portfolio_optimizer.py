"""Unit tests for Portfolio Optimizer (Riskfolio-Lib integration)."""

from decimal import Decimal

import pytest

from src.portfolio_optimizer import _MIN_BARS, PortfolioOptimizer


def _make_bars(n: int, base: float = 100.0, drift: float = 0.001) -> list[dict]:
    """Generate synthetic OHLCV bars with slight drift."""
    bars = []
    price = base
    for i in range(n):
        price = price * (1 + drift + 0.01 * (i % 3 - 1))
        bars.append({
            "open": price * 0.999,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1_000_000,
        })
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
    """Tests for optimize()."""

    def test_returns_weights_for_all_symbols(self, optimizer, ohlcv_data):
        """Optimizer should return weights for all symbols."""
        result = optimizer.optimize(["AAPL", "GOOGL", "MSFT"], ohlcv_data)

        assert "AAPL" in result
        assert "GOOGL" in result
        assert "MSFT" in result

    def test_weights_are_decimal(self, optimizer, ohlcv_data):
        """All weights should be Decimal values."""
        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        for weight in result.values():
            assert isinstance(weight, Decimal)

    def test_weights_non_negative(self, optimizer, ohlcv_data):
        """All weights should be non-negative."""
        result = optimizer.optimize(["AAPL", "GOOGL", "MSFT"], ohlcv_data)

        for weight in result.values():
            assert weight >= Decimal("0")

    def test_conservative_scales_down(self, optimizer, ohlcv_data):
        """Conservative profile should produce smaller weights than aggressive."""
        conservative = optimizer.optimize(
            ["AAPL", "GOOGL"], ohlcv_data, risk_profile="CONSERVATIVE"
        )
        aggressive = optimizer.optimize(
            ["AAPL", "GOOGL"], ohlcv_data, risk_profile="AGGRESSIVE"
        )

        cons_total = sum(conservative.values())
        aggr_total = sum(aggressive.values())
        assert cons_total <= aggr_total

    def test_weight_precision(self, optimizer, ohlcv_data):
        """Weights should be quantized to 4 decimal places."""
        result = optimizer.optimize(["AAPL", "GOOGL"], ohlcv_data)

        for weight in result.values():
            assert weight == weight.quantize(Decimal("0.0001"))


class TestEqualWeight:
    """Tests for _equal_weight fallback."""

    def test_equal_weight_two_symbols(self, optimizer):
        """Two symbols should get 0.5 each."""
        result = optimizer._equal_weight(["AAPL", "GOOGL"])
        assert result["AAPL"] == Decimal("0.5000")
        assert result["GOOGL"] == Decimal("0.5000")

    def test_equal_weight_three_symbols(self, optimizer):
        """Three symbols should get ~0.3333 each."""
        result = optimizer._equal_weight(["AAPL", "GOOGL", "MSFT"])
        for weight in result.values():
            assert abs(weight - Decimal("0.3333")) <= Decimal("0.0001")

    def test_equal_weight_empty(self, optimizer):
        """Empty symbols list should return empty dict."""
        result = optimizer._equal_weight([])
        assert result == {}


class TestFallbackBehavior:
    """Tests for fallback to equal-weight."""

    def test_insufficient_data_falls_back(self, optimizer):
        """Should fall back to equal-weight when data is too short."""
        short_data = {
            "AAPL": _make_bars(10),
            "GOOGL": _make_bars(10),
        }
        result = optimizer.optimize(["AAPL", "GOOGL"], short_data)

        # Should be equal-weight
        assert result["AAPL"] == result["GOOGL"]

    def test_single_symbol_falls_back(self, optimizer, ohlcv_data):
        """Single symbol can't be optimized, should fall back."""
        result = optimizer.optimize(["AAPL"], ohlcv_data)

        assert result["AAPL"] == Decimal("1.0000")

    def test_missing_data_falls_back(self, optimizer):
        """Missing OHLCV data should fall back to equal-weight."""
        result = optimizer.optimize(["AAPL", "GOOGL"], {})

        assert result["AAPL"] == Decimal("0.5000")
        assert result["GOOGL"] == Decimal("0.5000")


class TestBuildReturns:
    """Tests for _build_returns."""

    def test_builds_valid_dataframe(self, optimizer, ohlcv_data):
        """Should build a valid returns DataFrame."""
        df = optimizer._build_returns(["AAPL", "GOOGL"], ohlcv_data)

        assert df is not None
        assert "AAPL" in df.columns
        assert "GOOGL" in df.columns
        assert len(df) >= _MIN_BARS - 1

    def test_returns_none_for_insufficient_data(self, optimizer):
        """Should return None when data is insufficient."""
        short_data = {"AAPL": _make_bars(5), "GOOGL": _make_bars(5)}
        df = optimizer._build_returns(["AAPL", "GOOGL"], short_data)

        assert df is None

    def test_returns_none_for_single_symbol(self, optimizer, ohlcv_data):
        """Should return None when only one symbol has enough data."""
        df = optimizer._build_returns(["AAPL"], ohlcv_data)

        assert df is None
