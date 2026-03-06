"""Tests for UserService — auth, preferences, broker config."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.models import UserPreferences
from app.services.user import UserService


@pytest.fixture
def user_svc(mock_redis, mock_user_repo):
    return UserService(redis=mock_redis, user_repo=mock_user_repo)


class TestLogin:
    async def test_login_success(self, user_svc, mock_user_repo):
        mock_user_repo.find_by_email.return_value = MagicMock(
            user_id="user-1",
            password_hash="$2b$12$hashed",
            name="Test User",
        )
        with patch("bcrypt.checkpw", return_value=True):
            result = await user_svc.login("test@example.com", "password")

        assert result is not None
        assert result["userId"] == "user-1"
        assert "accessToken" in result
        assert "refreshToken" in result

    async def test_login_user_not_found(self, user_svc, mock_user_repo):
        mock_user_repo.find_by_email.return_value = None
        result = await user_svc.login("unknown@example.com", "password")
        assert result is None

    async def test_login_wrong_password(self, user_svc, mock_user_repo):
        mock_user_repo.find_by_email.return_value = MagicMock(
            user_id="user-1",
            password_hash="hash",
            name="Test",
        )
        with patch("bcrypt.checkpw", return_value=False):
            result = await user_svc.login("test@example.com", "wrong")
        assert result is None


class TestTokenValidation:
    def test_validate_valid_token(self, user_svc):
        token = user_svc._create_access_token("user-1")
        user_id = user_svc.validate_token(token)
        assert user_id == "user-1"

    def test_validate_invalid_token(self, user_svc):
        user_id = user_svc.validate_token("invalid-token")
        assert user_id is None

    async def test_refresh_token_flow(self, user_svc, mock_redis):
        mock_redis.get.return_value = "user-1"
        result = await user_svc.refresh_token("valid-refresh-token")
        assert result is not None
        assert "accessToken" in result

    async def test_refresh_token_invalid(self, user_svc, mock_redis):
        mock_redis.get.return_value = None
        result = await user_svc.refresh_token("invalid-refresh-token")
        assert result is None

    async def test_logout(self, user_svc, mock_redis):
        await user_svc.logout("some-refresh-token")
        mock_redis.delete.assert_called_once_with("refresh:some-refresh-token")


class TestPreferences:
    async def test_get_preferences_from_cache(self, user_svc, mock_redis):
        mock_redis.get.return_value = {
            "user_id": "user-1",
            "risk_profile": "aggressive",
        }
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == "aggressive"

    async def test_get_preferences_from_db(self, user_svc, mock_redis, mock_user_repo):
        mock_redis.get.return_value = None
        mock_user_repo.get_preferences.return_value = MagicMock(
            risk_profile="conservative",
            max_portfolio_risk=0.15,
            max_position_size=0.05,
            preferred_sectors=["Technology"],
            enable_notifications=True,
            trading_enabled=False,
        )
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == "conservative"
        mock_redis.setex.assert_called_once()

    async def test_get_preferences_defaults(self, user_svc, mock_redis, mock_user_repo):
        mock_redis.get.return_value = None
        mock_user_repo.get_preferences.return_value = None
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == "moderate"

    async def test_update_preferences(self, user_svc, mock_redis, mock_user_repo):
        prefs = UserPreferences(user_id="user-1", risk_profile="aggressive")
        result = await user_svc.update_preferences("user-1", prefs)
        assert result.risk_profile == "aggressive"
        mock_user_repo.upsert_preferences.assert_called_once()
        mock_redis.delete.assert_called_once()


class TestBrokerConfig:
    async def test_get_broker_status_configured(self, user_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = [MagicMock()]
        result = await user_svc.get_broker_status("user-1")
        assert result["configured"] is True

    async def test_get_broker_status_not_configured(self, user_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = []
        result = await user_svc.get_broker_status("user-1")
        assert result["configured"] is False

    @patch("app.shared.utils.broker.settings")
    @patch("app.services.user.settings")
    async def test_get_broker_status_decrypt_failure(
        self, mock_svc_settings, mock_broker_settings, user_svc, mock_user_repo
    ):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        for s in (mock_svc_settings, mock_broker_settings):
            s.fernet_key = key.decode()
            s.alpaca_api_key = ""
            s.alpaca_secret_key = ""
            s.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = [
            MagicMock(config_key="api_key", encrypted_value="junk"),
            MagicMock(config_key="secret_key", encrypted_value="junk"),
        ]
        result = await user_svc.get_broker_status("user-1")
        assert result["configured"] is True
        assert result["connected"] is False

    @patch("app.shared.utils.broker.settings")
    @patch("app.services.user.settings")
    async def test_get_broker_status_alpaca_success(
        self, mock_svc_settings, mock_broker_settings, user_svc, mock_user_repo
    ):
        for s in (mock_svc_settings, mock_broker_settings):
            s.fernet_key = ""
            s.alpaca_api_key = "key"
            s.alpaca_secret_key = "secret"
            s.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"equity": "100000", "cash": "50000"}

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await user_svc.get_broker_status("user-1")

        assert result["configured"] is True
        assert result["connected"] is True
        assert result["equity"] == Decimal("100000")

    @patch("app.shared.utils.broker.settings")
    @patch("app.services.user.settings")
    async def test_get_broker_status_alpaca_auth_failure(
        self, mock_svc_settings, mock_broker_settings, user_svc, mock_user_repo
    ):
        for s in (mock_svc_settings, mock_broker_settings):
            s.fernet_key = ""
            s.alpaca_api_key = "key"
            s.alpaca_secret_key = "secret"
            s.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await user_svc.get_broker_status("user-1")

        assert result["connected"] is False
        assert "401" in result["errorMessage"]

    @patch("app.shared.utils.broker.settings")
    @patch("app.services.user.settings")
    async def test_get_broker_status_connection_error(
        self, mock_svc_settings, mock_broker_settings, user_svc, mock_user_repo
    ):
        for s in (mock_svc_settings, mock_broker_settings):
            s.fernet_key = ""
            s.alpaca_api_key = "key"
            s.alpaca_secret_key = "secret"
            s.alpaca_base_url = "https://paper-api.alpaca.markets"
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.HTTPError("Connection refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await user_svc.get_broker_status("user-1")

        assert result["connected"] is False
        assert "connection failed" in result["errorMessage"].lower()


class TestDecryptBrokerCredentials:
    @patch("app.shared.utils.broker.settings")
    def test_no_fernet_key_returns_global(self, mock_settings, user_svc):
        mock_settings.fernet_key = ""
        mock_settings.alpaca_api_key = "global-key"
        mock_settings.alpaca_secret_key = "global-secret"
        api_key, secret_key = user_svc._decrypt_broker_credentials([])
        assert api_key == "global-key"
        assert secret_key == "global-secret"

    @patch("app.shared.utils.broker.settings")
    def test_decrypt_success(self, mock_settings, user_svc):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        mock_settings.fernet_key = key.decode()
        f = Fernet(key)

        configs = [
            MagicMock(config_key="api_key", encrypted_value=f.encrypt(b"my-api-key").decode()),
            MagicMock(config_key="secret_key", encrypted_value=f.encrypt(b"my-secret").decode()),
        ]
        api_key, secret_key = user_svc._decrypt_broker_credentials(configs)
        assert api_key == "my-api-key"
        assert secret_key == "my-secret"

    @patch("app.shared.utils.broker.settings")
    def test_decrypt_failure_returns_global(self, mock_settings, user_svc):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        mock_settings.fernet_key = key.decode()
        mock_settings.alpaca_api_key = "fallback-key"
        mock_settings.alpaca_secret_key = "fallback-secret"

        configs = [
            MagicMock(config_key="api_key", encrypted_value="invalid-encrypted-data"),
            MagicMock(config_key="secret_key", encrypted_value="invalid-encrypted-data"),
        ]
        api_key, secret_key = user_svc._decrypt_broker_credentials(configs)
        assert api_key == "fallback-key"
        assert secret_key == "fallback-secret"


class TestUpdateBrokerConfig:
    @patch("app.services.user.settings")
    async def test_update_success(self, mock_settings, user_svc, mock_user_repo):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        mock_settings.fernet_key = key.decode()
        mock_user_repo.upsert_broker_config = AsyncMock()

        result = await user_svc.update_broker_config("user-1", "api-key", "secret-key", True)
        assert result["configured"] is True
        assert mock_user_repo.upsert_broker_config.call_count == 3

    @patch("app.services.user.settings")
    async def test_update_no_fernet_key(self, mock_settings, user_svc):
        mock_settings.fernet_key = ""
        result = await user_svc.update_broker_config("user-1", "key", "secret", True)
        assert result["configured"] is False


class TestGetUserInfo:
    async def test_success(self, user_svc, mock_user_repo):
        user_row = MagicMock()
        user_row.user_id = "user-1"
        user_row.name = "Test User"
        user_row.email = "test@example.com"
        mock_user_repo.find_by_id.return_value = user_row
        result = await user_svc.get_user_info("user-1")
        assert result["userId"] == "user-1"
        assert result["name"] == "Test User"

    async def test_not_found(self, user_svc, mock_user_repo):
        mock_user_repo.find_by_id.return_value = None
        result = await user_svc.get_user_info("nonexistent")
        assert result is None
