"""Tests for PortfolioRepository — ORM-based data access."""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.portfolio_repository import PortfolioRepository


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
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


class TestGetPositions:
    async def test_returns_positions(self, mock_session):
        pos1 = MagicMock(symbol="AAPL", quantity=Decimal("10"))
        pos2 = MagicMock(symbol="MSFT", quantity=Decimal("5"))
        mock_session.execute.return_value.scalars.return_value.all.return_value = [pos1, pos2]

        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_positions("user-1")

        assert len(result) == 2
        mock_session.execute.assert_awaited_once()

    async def test_returns_empty_list(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_positions("user-1")
        assert result == []


class TestGetCashBalance:
    async def test_returns_balance(self, mock_session):
        record = MagicMock(cash_balance=Decimal("50000"))
        mock_session.execute.return_value.scalar_one_or_none.return_value = record

        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_cash_balance("user-1")
        assert result == Decimal("50000")

    async def test_returns_zero_when_no_record(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_cash_balance("user-1")
        assert result == Decimal("0")


class TestGetPositionBySymbol:
    async def test_returns_position(self, mock_session):
        position = MagicMock(symbol="AAPL", quantity=Decimal("10"))
        mock_session.execute.return_value.scalar_one_or_none.return_value = position

        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_position_by_symbol("user-1", "AAPL")
        assert result.symbol == "AAPL"

    async def test_returns_none_when_not_found(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        result = await repo.get_position_by_symbol("user-1", "UNKNOWN")
        assert result is None


class TestUpsertPosition:
    async def test_creates_new_position(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        await repo.upsert_position("user-1", "AAPL", Decimal("10"), Decimal("150"), Decimal("155"))

        mock_session.add.assert_called_once()

    async def test_updates_existing_position(self, mock_session):
        existing = MagicMock()
        existing.quantity = Decimal("5")
        existing.avg_cost = Decimal("140")
        existing.current_price = Decimal("145")
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        await repo.upsert_position("user-1", "AAPL", Decimal("15"), Decimal("148"), Decimal("155"))

        assert existing.quantity == Decimal("15")
        assert existing.avg_cost == Decimal("148")
        assert existing.current_price == Decimal("155")
        mock_session.add.assert_not_called()


class TestDeletePosition:
    async def test_deletes_position(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        await repo.delete_position("user-1", "AAPL")

        mock_session.execute.assert_awaited_once()


class TestUpdateCashBalance:
    async def test_updates_existing_balance(self, mock_session):
        existing = MagicMock(cash_balance=Decimal("50000"))
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        await repo.update_cash_balance("user-1", Decimal("75000"))

        assert existing.cash_balance == Decimal("75000")
        mock_session.add.assert_not_called()

    async def test_creates_portfolio_if_none(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = PortfolioRepository(postgres=postgres)
        await repo.update_cash_balance("user-1", Decimal("100000"))

        mock_session.add.assert_called_once()
