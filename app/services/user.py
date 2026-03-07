"""User Service — Account management, preferences, JWT.

Replaces: services/user/ + services/auth/ (794 + 341 = 1135 lines → ~130 lines)
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import bcrypt
import jwt

from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.models import RiskProfile, UserPreferences
from ..repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    """User management, authentication, and preferences."""

    def __init__(self, redis: RedisClient, user_repo: UserRepository) -> None:
        self.redis = redis
        self.user_repo = user_repo

    # --- Authentication ---

    async def login(self, email: str, password: str) -> dict[str, Any] | None:
        """Authenticate user and return tokens."""
        row = await self.user_repo.find_by_email(email)
        if not row:
            return None

        if not bcrypt.checkpw(password.encode(), row.password_hash.encode()):
            return None

        user_id = str(row.user_id)
        access_token = self._create_access_token(user_id)
        refresh_token = self._create_refresh_token(user_id)

        await self.redis.setex(
            f"refresh:{refresh_token}",
            settings.jwt_refresh_token_expire_days * 86400,
            user_id,
        )

        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "userId": user_id,
            "name": row.name,
        }

    async def refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh access token using refresh token."""
        user_id = await self.redis.get(f"refresh:{refresh_token}")
        if not user_id:
            return None

        access_token = self._create_access_token(str(user_id))
        return {"accessToken": access_token}

    async def logout(self, refresh_token: str) -> None:
        """Invalidate refresh token."""
        await self.redis.delete(f"refresh:{refresh_token}")

    async def get_user_info(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Get basic user info by ID. Returns None if not found."""
        row = await self.user_repo.find_by_id(user_id)
        if not row:
            return None
        return {"userId": str(row.user_id), "name": row.name or "", "email": row.email}

    def validate_token(self, token: str) -> str | None:
        """Validate JWT access token. Returns user_id or None."""
        from ..config import decode_jwt_user_id

        return decode_jwt_user_id(token)

    def _create_access_token(self, user_id: str) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        return jwt.encode(
            {"sub": user_id, "exp": expire, "type": "access"},
            settings.jwt_private_key,
            algorithm=settings.jwt_algorithm,
        )

    def _create_refresh_token(self, user_id: str) -> str:
        expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
        return jwt.encode(
            {"sub": user_id, "exp": expire, "type": "refresh", "jti": str(uuid.uuid4())},
            settings.jwt_private_key,
            algorithm=settings.jwt_algorithm,
        )

    # --- Preferences ---

    async def get_preferences(self, user_id: uuid.UUID) -> UserPreferences:
        """Get user preferences (cached)."""
        cache_key = f"user:{user_id}:preferences"
        cached = await self.redis.get(cache_key)
        if cached and isinstance(cached, dict):
            return UserPreferences(**cached)

        row = await self.user_repo.get_preferences(user_id)

        uid_str = str(user_id)
        if row:
            prefs = UserPreferences(
                user_id=uid_str,
                risk_profile=RiskProfile(row.risk_profile),
                max_portfolio_risk=row.max_portfolio_risk,
                max_position_size=row.max_position_size,
                preferred_sectors=list(row.preferred_sectors) if row.preferred_sectors else [],
                excluded_sectors=list(row.excluded_sectors) if row.excluded_sectors else [],
                enable_notifications=row.enable_notifications,
                trading_enabled=row.trading_enabled,
            )
        else:
            prefs = UserPreferences(user_id=uid_str)

        await self.redis.setex(cache_key, settings.cache_user_preferences_ttl, prefs.model_dump())
        return prefs

    async def update_preferences(
        self, user_id: uuid.UUID, prefs: UserPreferences
    ) -> UserPreferences:
        """Update user preferences."""
        await self.user_repo.upsert_preferences(
            user_id=user_id,
            risk_profile=prefs.risk_profile,
            max_portfolio_risk=prefs.max_portfolio_risk,
            max_position_size=prefs.max_position_size,
            preferred_sectors=prefs.preferred_sectors,
            excluded_sectors=prefs.excluded_sectors,
            enable_notifications=prefs.enable_notifications,
            trading_enabled=prefs.trading_enabled,
        )
        await self.redis.delete(f"user:{user_id}:preferences")
        return prefs

    # --- Broker ---

    async def get_broker_status(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get broker connection status by testing Alpaca API connectivity."""
        configs = await self.user_repo.get_broker_config(user_id)
        configured = len(configs) > 0

        if not configured:
            return {
                "configured": False,
                "connected": False,
                "equity": 0,
                "cash": 0,
                "errorMessage": "",
            }

        api_key, secret_key = self._decrypt_broker_credentials(configs)
        if not api_key or not secret_key:
            return {
                "configured": True,
                "connected": False,
                "equity": 0,
                "cash": 0,
                "errorMessage": "Failed to decrypt credentials",
            }

        import httpx

        try:
            headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
            async with httpx.AsyncClient(base_url=settings.alpaca_base_url) as client:
                resp = await client.get("/v2/account", headers=headers, timeout=10)

            if resp.status_code != 200:
                return {
                    "configured": True,
                    "connected": False,
                    "equity": 0,
                    "cash": 0,
                    "errorMessage": f"Alpaca authentication failed ({resp.status_code})",
                }

            acct = resp.json()
            return {
                "configured": True,
                "connected": True,
                "equity": Decimal(acct.get("equity", "0")),
                "cash": Decimal(acct.get("cash", "0")),
                "errorMessage": "",
            }
        except httpx.HTTPError:
            return {
                "configured": True,
                "connected": False,
                "equity": 0,
                "cash": 0,
                "errorMessage": "Alpaca API connection failed",
            }

    @staticmethod
    def _decrypt_broker_credentials(configs: list[Any]) -> tuple[str, str]:
        """Decrypt broker credentials from stored config."""
        from ..shared.utils.broker import decrypt_alpaca_credentials

        return decrypt_alpaca_credentials(configs)

    async def update_broker_config(
        self, user_id: uuid.UUID, api_key: str, secret_key: str, paper: bool
    ) -> dict[str, Any]:
        """Update broker configuration for a specific user."""
        from cryptography.fernet import Fernet

        if not settings.fernet_key:
            return {"configured": False, "errorMessage": "Encryption key not configured"}

        f = Fernet(settings.fernet_key.encode())

        for key, value in [
            ("api_key", api_key),
            ("secret_key", secret_key),
            ("paper", str(paper)),
        ]:
            encrypted = f.encrypt(value.encode()).decode()
            await self.user_repo.upsert_broker_config(user_id, key, encrypted)

        return {"configured": True, "connected": True}
