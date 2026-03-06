"""Tests for TradeRepository — trade recording with row-level locking."""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.trade_repository import TradeRepository


def _make_mock_postgres(session):
    """Create a mock PostgresClient with get_session returning a context manager."""
    postgres = MagicMock()

    @asynccontextmanager
    async def mock_get_session():
        yield session

    postgres.get_session = mock_get_session
    return postgres


@pytest.fixture
def mock_session():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    return session


class TestRecordTradeAndUpdatePosition:
    async def test_buy_creates_new_position(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = TradeRepository(postgres=postgres)

        await repo.record_trade_and_update_position(
            user_id="user-1",
            order_id="order-1",
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            price=Decimal("150"),
        )

        # Should add both a TradeRecord and a PositionRecord
        assert mock_session.add.call_count == 2

    async def test_buy_updates_existing_position(self, mock_session):
        existing_position = MagicMock()
        existing_position.quantity = Decimal("10")
        existing_position.avg_cost = Decimal("140")
        existing_position.current_price = Decimal("145")

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_position
        mock_session.execute = AsyncMock(return_value=result)

        postgres = _make_mock_postgres(mock_session)
        repo = TradeRepository(postgres=postgres)

        await repo.record_trade_and_update_position(
            user_id="user-1",
            order_id="order-2",
            symbol="AAPL",
            side="buy",
            qty=Decimal("5"),
            price=Decimal("160"),
        )

        # Weighted average: (10*140 + 5*160) / 15
        assert existing_position.quantity == Decimal("15")
        expected_avg = (Decimal("10") * Decimal("140") + Decimal("5") * Decimal("160")) / Decimal(
            "15"
        )
        assert existing_position.avg_cost == expected_avg
        assert existing_position.current_price == Decimal("160")

    async def test_sell_reduces_position(self, mock_session):
        existing_position = MagicMock()
        existing_position.quantity = Decimal("10")
        existing_position.avg_cost = Decimal("140")

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_position
        mock_session.execute = AsyncMock(return_value=result)

        postgres = _make_mock_postgres(mock_session)
        repo = TradeRepository(postgres=postgres)

        await repo.record_trade_and_update_position(
            user_id="user-1",
            order_id="order-3",
            symbol="AAPL",
            side="sell",
            qty=Decimal("3"),
            price=Decimal("160"),
        )

        assert existing_position.quantity == Decimal("7")

    async def test_sell_does_not_go_negative(self, mock_session):
        existing_position = MagicMock()
        existing_position.quantity = Decimal("5")

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_position
        mock_session.execute = AsyncMock(return_value=result)

        postgres = _make_mock_postgres(mock_session)
        repo = TradeRepository(postgres=postgres)

        await repo.record_trade_and_update_position(
            user_id="user-1",
            order_id="order-4",
            symbol="AAPL",
            side="sell",
            qty=Decimal("10"),
            price=Decimal("160"),
        )

        assert existing_position.quantity == Decimal("0")
