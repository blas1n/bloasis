"""Tests for broker adapter factory."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.brokers.alpaca import AlpacaAdapter
from app.services.brokers.factory import create_broker_adapter
from app.services.brokers.mock import MockBrokerAdapter

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def mock_user_repo():
    return AsyncMock()


class TestCreateBrokerAdapter:
    @patch("app.services.brokers.factory.settings")
    async def test_mock_broker_when_enabled(self, mock_settings, mock_user_repo):
        mock_settings.mock_broker_enabled = True
        adapter = await create_broker_adapter(TEST_USER_ID, mock_user_repo)
        assert isinstance(adapter, MockBrokerAdapter)

    @patch("app.services.brokers.factory.settings")
    @patch("app.services.brokers.factory.decrypt_broker_credentials")
    async def test_uses_db_credentials(self, mock_decrypt, mock_settings, mock_user_repo):
        mock_settings.mock_broker_enabled = False
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = [MagicMock()]
        mock_decrypt.return_value = {
            "api_key": "db-key",
            "secret_key": "db-secret",
        }

        adapter = await create_broker_adapter(TEST_USER_ID, mock_user_repo)

        assert isinstance(adapter, AlpacaAdapter)
        assert adapter.api_key == "db-key"
        assert adapter.secret_key == "db-secret"

    @patch("app.services.brokers.factory.settings")
    @patch("app.services.brokers.factory.decrypt_broker_credentials")
    async def test_falls_back_to_global_env(self, mock_decrypt, mock_settings, mock_user_repo):
        mock_settings.mock_broker_enabled = False
        mock_settings.alpaca_api_key = "global-key"
        mock_settings.alpaca_secret_key = "global-secret"
        mock_settings.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = []
        mock_decrypt.return_value = {}

        adapter = await create_broker_adapter(TEST_USER_ID, mock_user_repo)

        assert isinstance(adapter, AlpacaAdapter)
        assert adapter.api_key == "global-key"

    @patch("app.services.brokers.factory.settings")
    @patch("app.services.brokers.factory.decrypt_broker_credentials")
    async def test_raises_when_no_credentials(self, mock_decrypt, mock_settings, mock_user_repo):
        mock_settings.mock_broker_enabled = False
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_user_repo.get_broker_config.return_value = []
        mock_decrypt.return_value = {}

        with pytest.raises(ValueError, match="No broker credentials"):
            await create_broker_adapter(TEST_USER_ID, mock_user_repo)

    @patch("app.services.brokers.factory.settings")
    @patch("app.services.brokers.factory.decrypt_broker_credentials")
    async def test_unsupported_broker_type(self, mock_decrypt, mock_settings, mock_user_repo):
        mock_settings.mock_broker_enabled = False
        mock_settings.alpaca_api_key = ""
        mock_settings.alpaca_secret_key = ""
        mock_user_repo.get_broker_config.return_value = [MagicMock()]
        mock_decrypt.return_value = {
            "api_key": "key",
            "secret_key": "secret",
        }

        with pytest.raises(ValueError, match="Unsupported broker type"):
            await create_broker_adapter(TEST_USER_ID, mock_user_repo, broker_type="kraken")
