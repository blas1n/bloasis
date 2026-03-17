"""Tests for UserService — auth, preferences, broker config."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.core.models import BrokerAccountInfo, RiskProfile, UserPreferences
from app.services.user import UserService


def _generate_rsa_keypair() -> tuple[str, str]:
    """Generate an RSA key pair for testing JWT signing/verification."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


_TEST_PRIVATE_KEY, _TEST_PUBLIC_KEY = _generate_rsa_keypair()


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
        with (
            patch("bcrypt.checkpw", return_value=True),
            patch.object(type(settings), "jwt_private_key", new=_TEST_PRIVATE_KEY),
        ):
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
        with (
            patch.object(type(settings), "jwt_private_key", new=_TEST_PRIVATE_KEY),
            patch.object(type(settings), "jwt_public_key", new=_TEST_PUBLIC_KEY),
        ):
            token = user_svc._create_access_token("user-1")
            user_id = user_svc.validate_token(token)
        assert user_id == "user-1"

    def test_validate_invalid_token(self, user_svc):
        with patch.object(type(settings), "jwt_public_key", new=_TEST_PUBLIC_KEY):
            user_id = user_svc.validate_token("invalid-token")
        assert user_id is None

    async def test_refresh_token_flow(self, user_svc, mock_redis):
        mock_redis.get.return_value = "user-1"
        with patch.object(type(settings), "jwt_private_key", new=_TEST_PRIVATE_KEY):
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
        assert prefs.risk_profile == RiskProfile.AGGRESSIVE

    async def test_get_preferences_from_db(self, user_svc, mock_redis, mock_user_repo):
        mock_redis.get.return_value = None
        mock_user_repo.get_preferences.return_value = MagicMock(
            risk_profile=RiskProfile.CONSERVATIVE,
            max_portfolio_risk=0.15,
            max_position_size=0.05,
            preferred_sectors=["Technology"],
            enable_notifications=True,
            trading_enabled=False,
        )
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == RiskProfile.CONSERVATIVE
        mock_redis.setex.assert_called_once()

    async def test_get_preferences_defaults(self, user_svc, mock_redis, mock_user_repo):
        mock_redis.get.return_value = None
        mock_user_repo.get_preferences.return_value = None
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == RiskProfile.MODERATE

    async def test_patch_preferences(self, user_svc, mock_redis, mock_user_repo):
        mock_redis.get.return_value = None
        mock_user_repo.patch_preferences = AsyncMock()
        mock_user_repo.get_preferences.return_value = MagicMock(
            risk_profile=RiskProfile.AGGRESSIVE,
            max_portfolio_risk=Decimal("0.20"),
            max_position_size=Decimal("0.10"),
            preferred_sectors=[],
            excluded_sectors=[],
            enable_notifications=True,
            trading_enabled=True,
        )
        result = await user_svc.patch_preferences(
            "user-1", {"risk_profile": RiskProfile.AGGRESSIVE}
        )
        assert result.risk_profile == RiskProfile.AGGRESSIVE
        mock_user_repo.patch_preferences.assert_called_once_with(
            "user-1", {"risk_profile": RiskProfile.AGGRESSIVE}
        )
        mock_redis.delete.assert_called_once()


class TestBrokerConfig:
    async def test_get_broker_status_not_configured_no_broker(self, user_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = []
        result = await user_svc.get_broker_status("user-1")
        assert result["configured"] is False

    async def test_get_broker_status_with_adapter_success(self, user_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_broker = AsyncMock()
        mock_broker.test_connection.return_value = True
        mock_broker.get_account.return_value = BrokerAccountInfo(
            equity=Decimal("100000"), cash=Decimal("50000"), buying_power=Decimal("50000")
        )

        result = await user_svc.get_broker_status("user-1", broker=mock_broker)
        assert result["configured"] is True
        assert result["connected"] is True
        assert result["equity"] == Decimal("100000")

    async def test_get_broker_status_with_adapter_connection_failure(
        self, user_svc, mock_user_repo
    ):
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_broker = AsyncMock()
        mock_broker.test_connection.return_value = False

        result = await user_svc.get_broker_status("user-1", broker=mock_broker)
        assert result["connected"] is False

    async def test_get_broker_status_with_adapter_exception(self, user_svc, mock_user_repo):
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_broker = AsyncMock()
        mock_broker.test_connection.side_effect = Exception("Connection refused")

        result = await user_svc.get_broker_status("user-1", broker=mock_broker)
        assert result["connected"] is False
        assert "connection failed" in result["errorMessage"].lower()


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

    @patch("app.services.user.settings")
    async def test_update_with_portfolio_sync(self, mock_settings, user_svc, mock_user_repo):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        mock_settings.fernet_key = key.decode()
        mock_user_repo.upsert_broker_config = AsyncMock()

        mock_portfolio_svc = AsyncMock()
        mock_portfolio_svc.sync_with_broker.return_value = {
            "success": True,
            "positionsSynced": 5,
        }

        with patch(
            "app.services.brokers.factory.create_broker_adapter", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = AsyncMock()
            result = await user_svc.update_broker_config(
                "user-1", "api-key", "secret-key", True, portfolio_svc=mock_portfolio_svc
            )

        assert result["configured"] is True
        assert result["positionsSynced"] == 5
        mock_portfolio_svc.sync_with_broker.assert_awaited_once()


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
