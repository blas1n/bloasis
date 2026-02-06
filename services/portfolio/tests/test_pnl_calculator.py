"""Tests for P&L Calculator."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pnl_calculator import PnLCalculator, PortfolioPnL, PositionPnL


class TestPositionPnL:
    """Tests for PositionPnL dataclass."""

    def test_position_pnl_attributes(self):
        """Test PositionPnL has all required attributes."""
        pnl = PositionPnL(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
            market_value=Decimal("1750.00"),
            cost_basis=Decimal("1500.00"),
            unrealized_pnl=Decimal("250.00"),
            unrealized_pnl_pct=Decimal("16.67"),
            daily_pnl=Decimal("50.00"),
            daily_pnl_pct=Decimal("2.94"),
        )

        assert pnl.symbol == "AAPL"
        assert pnl.qty == Decimal("10")
        assert pnl.market_value == Decimal("1750.00")
        assert pnl.unrealized_pnl == Decimal("250.00")


class TestPortfolioPnL:
    """Tests for PortfolioPnL dataclass."""

    def test_portfolio_pnl_attributes(self):
        """Test PortfolioPnL has all required attributes."""
        position_pnl = PositionPnL(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
            market_value=Decimal("1750.00"),
            cost_basis=Decimal("1500.00"),
            unrealized_pnl=Decimal("250.00"),
            unrealized_pnl_pct=Decimal("16.67"),
            daily_pnl=Decimal("50.00"),
            daily_pnl_pct=Decimal("2.94"),
        )

        portfolio_pnl = PortfolioPnL(
            total_market_value=Decimal("1750.00"),
            total_cost_basis=Decimal("1500.00"),
            total_unrealized_pnl=Decimal("250.00"),
            total_unrealized_pnl_pct=Decimal("16.67"),
            total_realized_pnl=Decimal("100.00"),
            total_daily_pnl=Decimal("50.00"),
            total_daily_pnl_pct=Decimal("2.94"),
            positions=[position_pnl],
        )

        assert portfolio_pnl.total_market_value == Decimal("1750.00")
        assert portfolio_pnl.total_unrealized_pnl == Decimal("250.00")
        assert len(portfolio_pnl.positions) == 1


class TestPnLCalculator:
    """Tests for PnLCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create a PnLCalculator without market data client."""
        return PnLCalculator()

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_profit(self, calculator):
        """Test P&L calculation for a profitable position."""
        pnl = await calculator.calculate_position_pnl(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
        )

        assert pnl.symbol == "AAPL"
        assert pnl.qty == Decimal("10")
        assert pnl.avg_cost == Decimal("150.00")
        assert pnl.current_price == Decimal("175.00")
        assert pnl.market_value == Decimal("1750.00")
        assert pnl.cost_basis == Decimal("1500.00")
        assert pnl.unrealized_pnl == Decimal("250.00")
        # 250 / 1500 * 100 = 16.666...%
        assert pnl.unrealized_pnl_pct > Decimal("16")
        assert pnl.unrealized_pnl_pct < Decimal("17")

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_loss(self, calculator):
        """Test P&L calculation for a losing position."""
        pnl = await calculator.calculate_position_pnl(
            symbol="GOOGL",
            qty=Decimal("5"),
            avg_cost=Decimal("200.00"),
            current_price=Decimal("180.00"),
        )

        assert pnl.market_value == Decimal("900.00")
        assert pnl.cost_basis == Decimal("1000.00")
        assert pnl.unrealized_pnl == Decimal("-100.00")
        assert pnl.unrealized_pnl_pct < Decimal("0")

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_zero_cost(self, calculator):
        """Test P&L calculation with zero cost basis."""
        pnl = await calculator.calculate_position_pnl(
            symbol="FREE",
            qty=Decimal("100"),
            avg_cost=Decimal("0"),
            current_price=Decimal("10.00"),
        )

        assert pnl.cost_basis == Decimal("0")
        assert pnl.unrealized_pnl_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_with_daily_pnl(self, calculator):
        """Test P&L calculation with daily P&L from previous close."""
        pnl = await calculator.calculate_position_pnl(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
            previous_close=Decimal("170.00"),
        )

        # Daily P&L: (175 - 170) * 10 = 50
        assert pnl.daily_pnl == Decimal("50.00")
        # Daily P&L %: (5 / 170) * 100 ≈ 2.94%
        assert pnl.daily_pnl_pct > Decimal("2.9")
        assert pnl.daily_pnl_pct < Decimal("3.0")

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_no_previous_close(self, calculator):
        """Test P&L calculation without previous close."""
        pnl = await calculator.calculate_position_pnl(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("175.00"),
        )

        # No previous close, so daily P&L should be 0
        assert pnl.daily_pnl == Decimal("0")
        assert pnl.daily_pnl_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_calculate_portfolio_pnl_single_position(self, calculator):
        """Test portfolio P&L with single position."""
        positions = [
            {
                "symbol": "AAPL",
                "qty": 10,
                "avg_cost": "150.00",
                "current_price": "175.00",
            }
        ]

        portfolio_pnl = await calculator.calculate_portfolio_pnl(positions)

        assert portfolio_pnl.total_market_value == Decimal("1750.00")
        assert portfolio_pnl.total_cost_basis == Decimal("1500.00")
        assert portfolio_pnl.total_unrealized_pnl == Decimal("250.00")
        assert len(portfolio_pnl.positions) == 1

    @pytest.mark.asyncio
    async def test_calculate_portfolio_pnl_multiple_positions(self, calculator):
        """Test portfolio P&L with multiple positions."""
        positions = [
            {
                "symbol": "AAPL",
                "qty": 10,
                "avg_cost": "150.00",
                "current_price": "175.00",
            },
            {
                "symbol": "GOOGL",
                "qty": 5,
                "avg_cost": "200.00",
                "current_price": "220.00",
            },
        ]

        portfolio_pnl = await calculator.calculate_portfolio_pnl(positions)

        # AAPL: 10 * 175 = 1750, GOOGL: 5 * 220 = 1100
        assert portfolio_pnl.total_market_value == Decimal("2850.00")
        # AAPL: 10 * 150 = 1500, GOOGL: 5 * 200 = 1000
        assert portfolio_pnl.total_cost_basis == Decimal("2500.00")
        # 2850 - 2500 = 350
        assert portfolio_pnl.total_unrealized_pnl == Decimal("350.00")
        assert len(portfolio_pnl.positions) == 2

    @pytest.mark.asyncio
    async def test_calculate_portfolio_pnl_with_realized(self, calculator):
        """Test portfolio P&L with realized P&L included."""
        positions = [
            {
                "symbol": "AAPL",
                "qty": 10,
                "avg_cost": "150.00",
                "current_price": "175.00",
            }
        ]

        portfolio_pnl = await calculator.calculate_portfolio_pnl(
            positions, realized_pnl=Decimal("500.00")
        )

        assert portfolio_pnl.total_realized_pnl == Decimal("500.00")
        assert portfolio_pnl.total_unrealized_pnl == Decimal("250.00")

    @pytest.mark.asyncio
    async def test_calculate_portfolio_pnl_empty(self, calculator):
        """Test portfolio P&L with no positions."""
        portfolio_pnl = await calculator.calculate_portfolio_pnl([])

        assert portfolio_pnl.total_market_value == Decimal("0")
        assert portfolio_pnl.total_cost_basis == Decimal("0")
        assert portfolio_pnl.total_unrealized_pnl == Decimal("0")
        assert portfolio_pnl.total_unrealized_pnl_pct == Decimal("0")
        assert len(portfolio_pnl.positions) == 0

    def test_calculate_trade_pnl_sell_profit(self, calculator):
        """Test realized P&L calculation for profitable sell."""
        realized_pnl = calculator.calculate_trade_pnl(
            side="sell",
            qty=Decimal("10"),
            price=Decimal("175.00"),
            avg_cost=Decimal("150.00"),
            commission=Decimal("5.00"),
        )

        # (175 - 150) * 10 - 5 = 250 - 5 = 245
        assert realized_pnl == Decimal("245.00")

    def test_calculate_trade_pnl_sell_loss(self, calculator):
        """Test realized P&L calculation for losing sell."""
        realized_pnl = calculator.calculate_trade_pnl(
            side="sell",
            qty=Decimal("10"),
            price=Decimal("140.00"),
            avg_cost=Decimal("150.00"),
            commission=Decimal("5.00"),
        )

        # (140 - 150) * 10 - 5 = -100 - 5 = -105
        assert realized_pnl == Decimal("-105.00")

    def test_calculate_trade_pnl_buy(self, calculator):
        """Test realized P&L calculation for buy trade."""
        realized_pnl = calculator.calculate_trade_pnl(
            side="buy",
            qty=Decimal("10"),
            price=Decimal("150.00"),
            avg_cost=Decimal("0"),
            commission=Decimal("5.00"),
        )

        # Buy trades only deduct commission
        assert realized_pnl == Decimal("-5.00")

    def test_calculate_trade_pnl_no_commission(self, calculator):
        """Test realized P&L calculation without commission."""
        realized_pnl = calculator.calculate_trade_pnl(
            side="sell",
            qty=Decimal("10"),
            price=Decimal("175.00"),
            avg_cost=Decimal("150.00"),
        )

        # (175 - 150) * 10 = 250
        assert realized_pnl == Decimal("250.00")

    @pytest.mark.asyncio
    async def test_get_current_price_no_client(self, calculator):
        """Test price fetch without market data client."""
        price = await calculator._get_current_price("AAPL")
        assert price == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_previous_close_no_client(self, calculator):
        """Test previous close fetch without market data client."""
        previous_close = await calculator._get_previous_close("AAPL")
        assert previous_close is None


class TestPnLCalculatorWithMarketData:
    """Tests for PnLCalculator with mocked Market Data client."""

    @pytest.fixture
    def mock_market_data_client(self):
        """Create a mock Market Data client."""
        mock_client = MagicMock()
        mock_client.get_current_price = AsyncMock(return_value=Decimal("175.50"))
        mock_client.get_previous_close = AsyncMock(return_value=Decimal("170.00"))
        return mock_client

    @pytest.fixture
    def calculator_with_client(self, mock_market_data_client):
        """Create a PnLCalculator with mocked market data client."""
        return PnLCalculator(market_data_client=mock_market_data_client)

    @pytest.mark.asyncio
    async def test_get_current_price_with_client(
        self, calculator_with_client, mock_market_data_client
    ):
        """Test price fetch with market data client."""
        price = await calculator_with_client._get_current_price("AAPL")
        assert price == Decimal("175.50")
        mock_market_data_client.get_current_price.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_get_previous_close_with_client(
        self, calculator_with_client, mock_market_data_client
    ):
        """Test previous close fetch with market data client."""
        previous_close = await calculator_with_client._get_previous_close("AAPL")
        assert previous_close == Decimal("170.00")
        mock_market_data_client.get_previous_close.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_get_current_price_client_error(self, mock_market_data_client):
        """Test price fetch handles client errors gracefully."""
        mock_market_data_client.get_current_price = AsyncMock(
            side_effect=Exception("Connection error")
        )
        calculator = PnLCalculator(market_data_client=mock_market_data_client)

        price = await calculator._get_current_price("AAPL")
        assert price == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_previous_close_client_error(self, mock_market_data_client):
        """Test previous close fetch handles client errors gracefully."""
        mock_market_data_client.get_previous_close = AsyncMock(
            side_effect=Exception("Connection error")
        )
        calculator = PnLCalculator(market_data_client=mock_market_data_client)

        previous_close = await calculator._get_previous_close("AAPL")
        assert previous_close is None

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_fetches_price(
        self, calculator_with_client, mock_market_data_client
    ):
        """Test position P&L calculation fetches price from market data."""
        pnl = await calculator_with_client.calculate_position_pnl(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
        )

        # Price fetched from mock: 175.50
        assert pnl.current_price == Decimal("175.50")
        assert pnl.market_value == Decimal("1755.00")
        # Cost basis: 10 * 150 = 1500
        assert pnl.cost_basis == Decimal("1500.00")
        # Unrealized P&L: 1755 - 1500 = 255
        assert pnl.unrealized_pnl == Decimal("255.00")

        # Daily P&L: previous close 170, current 175.50
        # (175.50 - 170) * 10 = 55
        assert pnl.daily_pnl == Decimal("55.00")

        mock_market_data_client.get_current_price.assert_called_once_with("AAPL")
        mock_market_data_client.get_previous_close.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_calculate_position_pnl_provided_price_skips_fetch(
        self, calculator_with_client, mock_market_data_client
    ):
        """Test position P&L uses provided price and skips fetch."""
        pnl = await calculator_with_client.calculate_position_pnl(
            symbol="AAPL",
            qty=Decimal("10"),
            avg_cost=Decimal("150.00"),
            current_price=Decimal("180.00"),
            previous_close=Decimal("175.00"),
        )

        # Uses provided prices
        assert pnl.current_price == Decimal("180.00")
        assert pnl.daily_pnl == Decimal("50.00")  # (180-175) * 10

        # Should not call market data client when prices are provided
        mock_market_data_client.get_current_price.assert_not_called()
        mock_market_data_client.get_previous_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_calculate_portfolio_pnl_with_market_data(
        self, calculator_with_client, mock_market_data_client
    ):
        """Test portfolio P&L fetches prices from market data."""
        # Configure mock to return different prices for different symbols
        async def mock_get_price(symbol: str) -> Decimal:
            prices = {"AAPL": Decimal("175.50"), "GOOGL": Decimal("220.00")}
            return prices.get(symbol, Decimal("0"))

        async def mock_get_prev_close(symbol: str) -> Decimal | None:
            prices = {"AAPL": Decimal("170.00"), "GOOGL": Decimal("215.00")}
            return prices.get(symbol)

        mock_market_data_client.get_current_price = AsyncMock(side_effect=mock_get_price)
        mock_market_data_client.get_previous_close = AsyncMock(
            side_effect=mock_get_prev_close
        )

        positions = [
            {"symbol": "AAPL", "qty": 10, "avg_cost": "150.00"},
            {"symbol": "GOOGL", "qty": 5, "avg_cost": "200.00"},
        ]

        portfolio_pnl = await calculator_with_client.calculate_portfolio_pnl(positions)

        # AAPL: 10 * 175.50 = 1755, GOOGL: 5 * 220 = 1100
        assert portfolio_pnl.total_market_value == Decimal("2855.00")
        # AAPL: 10 * 150 = 1500, GOOGL: 5 * 200 = 1000
        assert portfolio_pnl.total_cost_basis == Decimal("2500.00")
        # 2855 - 2500 = 355
        assert portfolio_pnl.total_unrealized_pnl == Decimal("355.00")

        # Verify positions have correct prices
        assert len(portfolio_pnl.positions) == 2
        aapl_pos = next(p for p in portfolio_pnl.positions if p.symbol == "AAPL")
        assert aapl_pos.current_price == Decimal("175.50")

    @pytest.mark.asyncio
    async def test_get_current_price_returns_zero_on_no_data(
        self, mock_market_data_client
    ):
        """Test that zero is returned when market data returns zero."""
        mock_market_data_client.get_current_price = AsyncMock(return_value=Decimal("0"))
        calculator = PnLCalculator(market_data_client=mock_market_data_client)

        price = await calculator._get_current_price("INVALID")
        assert price == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_previous_close_returns_none_on_no_data(
        self, mock_market_data_client
    ):
        """Test that None is returned when market data returns None."""
        mock_market_data_client.get_previous_close = AsyncMock(return_value=None)
        calculator = PnLCalculator(market_data_client=mock_market_data_client)

        previous_close = await calculator._get_previous_close("INVALID")
        assert previous_close is None
