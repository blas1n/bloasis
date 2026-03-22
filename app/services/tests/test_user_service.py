"""Tests for UserService — Supabase auth proxy, preferences, broker config."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.models import BrokerAccountInfo, RiskProfile
from app.services.user import UserService


@pytest.fixture
def user_svc(mock_redis: AsyncMock, mock_user_repo: AsyncMock) -> UserService:
    return UserService(redis=mock_redis, user_repo=mock_user_repo)


class TestLogin:
    @patch("app.services.user.httpx.AsyncClient")
    async def test_login_success(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "access-tok",
            "refresh_token": "refresh-tok",
            "user": {
                "id": "user-1",
                "user_metadata": {"name": "Test User"},
            },
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.login("test@example.com", "password")

        assert result is not None
        assert result["accessToken"] == "access-tok"
        assert result["refreshToken"] == "refresh-tok"
        assert result["userId"] == "user-1"
        assert result["name"] == "Test User"

    @patch("app.services.user.httpx.AsyncClient")
    async def test_login_invalid_credentials(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "invalid_grant"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.login("test@example.com", "wrong")
        assert result is None


class TestSignup:
    @patch("app.services.user.httpx.AsyncClient")
    async def test_signup_success(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "session": {
                "access_token": "access-tok",
                "refresh_token": "refresh-tok",
            },
            "user": {
                "id": "new-user",
                "user_metadata": {},
            },
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.signup("new@example.com", "password")

        assert result is not None
        assert result["userId"] == "new-user"

    @patch("app.services.user.httpx.AsyncClient")
    async def test_signup_failure(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 422

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.signup("bad@example.com", "short")
        assert result is None


class TestRefreshToken:
    @patch("app.services.user.httpx.AsyncClient")
    async def test_refresh_success(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.refresh_token("old-refresh")
        assert result is not None
        assert result["accessToken"] == "new-access"
        assert result["refreshToken"] == "new-refresh"

    @patch("app.services.user.httpx.AsyncClient")
    async def test_refresh_invalid(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.refresh_token("invalid")
        assert result is None


class TestLogout:
    @patch("app.services.user.httpx.AsyncClient")
    async def test_logout(self, mock_client_cls: MagicMock, user_svc: UserService) -> None:
        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(status_code=204)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await user_svc.logout("access-token")
        mock_client.post.assert_called_once()


class TestGetUserInfo:
    @patch("app.services.user.httpx.AsyncClient")
    async def test_success(self, mock_client_cls: MagicMock, user_svc: UserService) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "user-1",
            "email": "test@example.com",
            "user_metadata": {"name": "Test User"},
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.get_user_info("access-token")
        assert result is not None
        assert result["userId"] == "user-1"
        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"

    @patch("app.services.user.httpx.AsyncClient")
    async def test_invalid_token(
        self, mock_client_cls: MagicMock, user_svc: UserService
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await user_svc.get_user_info("invalid-token")
        assert result is None


class TestPreferences:
    async def test_get_preferences_from_cache(
        self, user_svc: UserService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.get.return_value = {
            "user_id": "user-1",
            "risk_profile": "aggressive",
        }
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == RiskProfile.AGGRESSIVE

    async def test_get_preferences_from_db(
        self, user_svc: UserService, mock_redis: AsyncMock, mock_user_repo: AsyncMock
    ) -> None:
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

    async def test_get_preferences_defaults(
        self, user_svc: UserService, mock_redis: AsyncMock, mock_user_repo: AsyncMock
    ) -> None:
        mock_redis.get.return_value = None
        mock_user_repo.get_preferences.return_value = None
        prefs = await user_svc.get_preferences("user-1")
        assert prefs.risk_profile == RiskProfile.MODERATE

    async def test_patch_preferences(
        self, user_svc: UserService, mock_redis: AsyncMock, mock_user_repo: AsyncMock
    ) -> None:
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
    async def test_get_broker_status_not_configured_no_broker(
        self, user_svc: UserService, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.get_broker_config.return_value = []
        result = await user_svc.get_broker_status("user-1")
        assert result["configured"] is False

    async def test_get_broker_status_with_adapter_success(
        self, user_svc: UserService, mock_user_repo: AsyncMock
    ) -> None:
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
        self, user_svc: UserService, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_broker = AsyncMock()
        mock_broker.test_connection.return_value = False

        result = await user_svc.get_broker_status("user-1", broker=mock_broker)
        assert result["connected"] is False

    async def test_get_broker_status_with_adapter_exception(
        self, user_svc: UserService, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.get_broker_config.return_value = [MagicMock()]

        mock_broker = AsyncMock()
        mock_broker.test_connection.side_effect = Exception("Connection refused")

        result = await user_svc.get_broker_status("user-1", broker=mock_broker)
        assert result["connected"] is False
        assert "connection failed" in result["errorMessage"].lower()


class TestUpdateBrokerConfig:
    @patch("app.services.user.settings")
    async def test_update_success(
        self,
        mock_settings: MagicMock,
        user_svc: UserService,
        mock_user_repo: AsyncMock,
    ) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        mock_settings.fernet_key = key.decode()
        mock_user_repo.upsert_broker_config = AsyncMock()

        result = await user_svc.update_broker_config("user-1", "api-key", "secret-key", True)
        assert result["configured"] is True
        assert mock_user_repo.upsert_broker_config.call_count == 3

    @patch("app.services.user.settings")
    async def test_update_no_fernet_key(
        self, mock_settings: MagicMock, user_svc: UserService
    ) -> None:
        mock_settings.fernet_key = ""
        result = await user_svc.update_broker_config("user-1", "key", "secret", True)
        assert result["configured"] is False

    @patch("app.services.user.settings")
    async def test_update_with_portfolio_sync(
        self,
        mock_settings: MagicMock,
        user_svc: UserService,
        mock_user_repo: AsyncMock,
    ) -> None:
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
