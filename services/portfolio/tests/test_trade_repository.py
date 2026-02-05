"""Tests for TradeRepository."""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import Trade, TradeRecord
from src.repositories.trade_repository import TradeRepository


class TestTradeRepository:
    """Tests for TradeRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create a TradeRepository with mock session."""
        return TradeRepository(mock_session)

    @pytest.fixture
    def sample_trade_record(self):
        """Create a sample trade record."""
        record = MagicMock(spec=TradeRecord)
        record.id = uuid.uuid4()
        record.user_id = uuid.uuid4()
        record.order_id = "order-123"
        record.symbol = "AAPL"
        record.action = "BUY"
        record.quantity = 10
        record.price = Decimal("150.00")
        record.total_value = Decimal("1500.00")
        record.commission = Decimal("1.00")
        record.realized_pnl = Decimal("0.00")
        record.executed_at = datetime(2026, 2, 5, 12, 0, 0)
        return record

    @pytest.mark.asyncio
    async def test_save_trade(self, repository, mock_session):
        """Test saving a new trade."""
        user_id = str(uuid.uuid4())
        order_id = "order-123"
        symbol = "AAPL"
        side = "buy"
        qty = Decimal("10")
        price = Decimal("150.00")

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        await repository.save_trade(
            user_id=user_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_trade_with_commission(self, repository, mock_session):
        """Test saving a trade with commission and realized P&L."""
        user_id = str(uuid.uuid4())

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        await repository.save_trade(
            user_id=user_id,
            order_id="order-456",
            symbol="GOOGL",
            side="sell",
            qty=Decimal("5"),
            price=Decimal("200.00"),
            commission=Decimal("2.50"),
            realized_pnl=Decimal("50.00"),
            executed_at=datetime(2026, 2, 5, 14, 0, 0),
        )

        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_trade_by_order_id_found(self, repository, mock_session, sample_trade_record):
        """Test getting a trade by order ID when found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_trade_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        trade = await repository.get_trade_by_order_id("order-123")

        assert trade is not None
        assert trade.order_id == "order-123"
        assert trade.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_trade_by_order_id_not_found(self, repository, mock_session):
        """Test getting a trade by order ID when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        trade = await repository.get_trade_by_order_id("nonexistent")

        assert trade is None

    @pytest.mark.asyncio
    async def test_get_trades_basic(self, repository, mock_session, sample_trade_record):
        """Test getting trade history for a user."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trade_record]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        trades = await repository.get_trades(user_id)

        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_trades_with_symbol_filter(
        self, repository, mock_session, sample_trade_record
    ):
        """Test getting trade history with symbol filter."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trade_record]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        trades = await repository.get_trades(user_id, symbol="AAPL")

        assert len(trades) == 1
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_trades_with_date_filters(
        self, repository, mock_session, sample_trade_record
    ):
        """Test getting trade history with date filters."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trade_record]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        start_date = datetime(2026, 2, 1)
        end_date = datetime(2026, 2, 28)

        trades = await repository.get_trades(user_id, start_date=start_date, end_date=end_date)

        assert len(trades) == 1
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_trades_empty(self, repository, mock_session):
        """Test getting trade history when no trades exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        trades = await repository.get_trades(user_id)

        assert len(trades) == 0

    @pytest.mark.asyncio
    async def test_get_realized_pnl(self, repository, mock_session):
        """Test calculating total realized P&L."""
        # Create mock trade records with different P&L values
        trade1 = MagicMock(spec=TradeRecord)
        trade1.id = uuid.uuid4()
        trade1.user_id = uuid.uuid4()
        trade1.order_id = "order-1"
        trade1.symbol = "AAPL"
        trade1.action = "SELL"
        trade1.quantity = 10
        trade1.price = Decimal("175.00")
        trade1.total_value = Decimal("1750.00")
        trade1.commission = Decimal("1.00")
        trade1.realized_pnl = Decimal("245.00")
        trade1.executed_at = datetime(2026, 2, 5)

        trade2 = MagicMock(spec=TradeRecord)
        trade2.id = uuid.uuid4()
        trade2.user_id = trade1.user_id
        trade2.order_id = "order-2"
        trade2.symbol = "GOOGL"
        trade2.action = "SELL"
        trade2.quantity = 5
        trade2.price = Decimal("180.00")
        trade2.total_value = Decimal("900.00")
        trade2.commission = Decimal("1.00")
        trade2.realized_pnl = Decimal("-105.00")
        trade2.executed_at = datetime(2026, 2, 5)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [trade1, trade2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        total_pnl = await repository.get_realized_pnl(user_id)

        # 245 + (-105) = 140
        assert total_pnl == Decimal("140.00")

    @pytest.mark.asyncio
    async def test_get_realized_pnl_with_filters(self, repository, mock_session):
        """Test calculating realized P&L with symbol and date filters."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        total_pnl = await repository.get_realized_pnl(
            user_id,
            symbol="AAPL",
            start_date=datetime(2026, 2, 1),
            end_date=datetime(2026, 2, 28),
        )

        assert total_pnl == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_trades_for_symbol(self, repository, mock_session, sample_trade_record):
        """Test getting all trades for a specific symbol."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trade_record]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        user_id = str(uuid.uuid4())
        trades = await repository.get_trades_for_symbol(user_id, "AAPL")

        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"


class TestTrade:
    """Tests for Trade domain object."""

    def test_trade_from_record(self):
        """Test creating Trade from TradeRecord."""
        record = MagicMock(spec=TradeRecord)
        record.id = uuid.uuid4()
        record.user_id = uuid.uuid4()
        record.order_id = "order-123"
        record.symbol = "AAPL"
        record.action = "BUY"
        record.quantity = 10
        record.price = Decimal("150.00")
        record.total_value = Decimal("1500.00")
        record.commission = Decimal("1.00")
        record.realized_pnl = Decimal("0.00")
        record.executed_at = datetime(2026, 2, 5, 12, 0, 0)

        trade = Trade.from_record(record)

        assert trade.order_id == "order-123"
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.qty == Decimal("10")
        assert trade.price == Decimal("150.00")
        assert trade.commission == Decimal("1.00")
        assert trade.realized_pnl == Decimal("0.00")

    def test_trade_from_record_sell(self):
        """Test creating Trade from sell TradeRecord."""
        record = MagicMock(spec=TradeRecord)
        record.id = uuid.uuid4()
        record.user_id = uuid.uuid4()
        record.order_id = "order-456"
        record.symbol = "GOOGL"
        record.action = "SELL"
        record.quantity = 5
        record.price = Decimal("200.00")
        record.total_value = Decimal("1000.00")
        record.commission = Decimal("2.50")
        record.realized_pnl = Decimal("50.00")
        record.executed_at = datetime(2026, 2, 5, 14, 0, 0)

        trade = Trade.from_record(record)

        assert trade.side == "sell"
        assert trade.qty == Decimal("5")
        assert trade.realized_pnl == Decimal("50.00")
