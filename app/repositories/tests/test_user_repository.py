"""Tests for UserRepository — ORM-based data access."""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.user_repository import UserRepository


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
    session.get = AsyncMock(return_value=None)
    return session


class TestFindByEmail:
    async def test_returns_user(self, mock_session):
        user = MagicMock(email="test@example.com", user_id="user-1")
        mock_session.execute.return_value.scalar_one_or_none.return_value = user

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.find_by_email("test@example.com")
        assert result.user_id == "user-1"

    async def test_returns_none(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.find_by_email("unknown@example.com")
        assert result is None


class TestFindById:
    async def test_returns_user(self, mock_session):
        user = MagicMock()
        user.user_id = "user-1"
        user.name = "Test"
        mock_session.execute.return_value.scalar_one_or_none.return_value = user

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.find_by_id("user-1")
        assert result.user_id == "user-1"

    async def test_returns_none(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.find_by_id("nonexistent")
        assert result is None


class TestGetPreferences:
    async def test_returns_preferences(self, mock_session):
        prefs = MagicMock(risk_profile="aggressive")
        mock_session.execute.return_value.scalar_one_or_none.return_value = prefs

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_preferences("user-1")
        assert result.risk_profile == "aggressive"

    async def test_returns_none(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_preferences("user-1")
        assert result is None


class TestUpsertPreferences:
    async def test_creates_new(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.upsert_preferences(
            user_id="user-1",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.20"),
            max_position_size=Decimal("0.10"),
            preferred_sectors=["Technology"],
            excluded_sectors=["Energy"],
            enable_notifications=True,
            trading_enabled=True,
        )
        mock_session.add.assert_called_once()

    async def test_updates_existing(self, mock_session):
        existing = MagicMock()
        mock_session.get = AsyncMock(return_value=existing)

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.upsert_preferences(
            user_id="user-1",
            risk_profile="conservative",
            max_portfolio_risk=Decimal("0.10"),
            max_position_size=Decimal("0.05"),
            preferred_sectors=["Healthcare"],
            excluded_sectors=[],
            enable_notifications=False,
            trading_enabled=False,
        )
        assert existing.risk_profile == "conservative"
        assert existing.max_portfolio_risk == Decimal("0.10")
        mock_session.add.assert_not_called()


class TestUpdateTradingEnabled:
    async def test_updates_existing(self, mock_session):
        existing = MagicMock(trading_enabled=False)
        mock_session.get = AsyncMock(return_value=existing)

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.update_trading_enabled("user-1", True)
        assert existing.trading_enabled is True

    async def test_creates_if_not_exists(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.update_trading_enabled("user-1", True)
        mock_session.add.assert_called_once()


class TestGetTradingEnabled:
    async def test_returns_true(self, mock_session):
        mock_session.execute.return_value.scalar_one_or_none.return_value = True

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_trading_enabled("user-1")
        assert result is True

    async def test_returns_false_when_none(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_trading_enabled("user-1")
        assert result is False


class TestGetBrokerConfig:
    async def test_returns_configs(self, mock_session):
        cfg1 = MagicMock(config_key="api_key")
        cfg2 = MagicMock(config_key="secret_key")
        mock_session.execute.return_value.scalars.return_value.all.return_value = [cfg1, cfg2]

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_broker_config("user-1")
        assert len(result) == 2

    async def test_returns_empty(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        result = await repo.get_broker_config("user-1")
        assert result == []


class TestUpsertBrokerConfig:
    async def test_creates_new(self, mock_session):
        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.upsert_broker_config("user-1", "api_key", "encrypted_value")
        mock_session.add.assert_called_once()

    async def test_updates_existing(self, mock_session):
        existing = MagicMock(encrypted_value="old_value")
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        postgres = _make_mock_postgres(mock_session)
        repo = UserRepository(postgres=postgres)
        await repo.upsert_broker_config("user-1", "api_key", "new_encrypted_value")
        assert existing.encrypted_value == "new_encrypted_value"
        mock_session.add.assert_not_called()
