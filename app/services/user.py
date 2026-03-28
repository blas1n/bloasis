"""User Service — Supabase Auth proxy, preferences, broker config.

Auth operations (signup, login, refresh, logout) proxy to Supabase Auth REST API.
Preferences and broker config remain local (PostgreSQL).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from shared.utils.redis_client import RedisClient

if TYPE_CHECKING:
    from ..core.broker import BrokerAdapter
    from .portfolio import PortfolioService

from ..config import settings
from ..core.models import RiskProfile, UserPreferences
from ..repositories.user_repository import UserRepository

logger = structlog.get_logger(__name__)


class UserService:
    """User management via Supabase Auth, preferences, and broker config."""

    def __init__(self, redis: RedisClient, user_repo: UserRepository) -> None:
        self.redis = redis
        self.user_repo = user_repo

    # --- Supabase Auth Proxy ---

    async def signup(self, email: str, password: str) -> dict[str, Any] | None:
        """Register a new user via Supabase Auth."""
        url = f"{settings.supabase_url}/auth/v1/signup"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"email": email, "password": password},
                headers=headers,
                timeout=30,
            )
        if resp.status_code >= 400:
            return None

        data = resp.json()
        session = data.get("session")
        user = data.get("user", {})
        if not session:
            return None

        user_metadata = user.get("user_metadata", {})
        return {
            "accessToken": session["access_token"],
            "refreshToken": session["refresh_token"],
            "userId": user.get("id", ""),
            "name": user_metadata.get("name", ""),
        }

    async def login(self, email: str, password: str) -> dict[str, Any] | None:
        """Authenticate user via Supabase Auth."""
        url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"email": email, "password": password},
                headers=headers,
                timeout=30,
            )
        if resp.status_code >= 400:
            return None

        data = resp.json()
        user = data.get("user", {})
        user_metadata = user.get("user_metadata", {})

        return {
            "accessToken": data["access_token"],
            "refreshToken": data["refresh_token"],
            "userId": user.get("id", ""),
            "name": user_metadata.get("name", ""),
        }

    async def refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh access token via Supabase Auth."""
        url = f"{settings.supabase_url}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"refresh_token": refresh_token},
                headers=headers,
                timeout=30,
            )
        if resp.status_code >= 400:
            return None

        data = resp.json()
        return {
            "accessToken": data["access_token"],
            "refreshToken": data["refresh_token"],
        }

    async def logout(self, access_token: str) -> None:
        """Logout user via Supabase Auth."""
        url = f"{settings.supabase_url}/auth/v1/logout"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        }
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, timeout=30)

    async def get_user_info(self, access_token: str) -> dict[str, Any] | None:
        """Get user info from Supabase Auth."""
        url = f"{settings.supabase_url}/auth/v1/user"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=30)
        if resp.status_code >= 400:
            return None

        data = resp.json()
        user_metadata = data.get("user_metadata", {})
        return {
            "userId": data.get("id", ""),
            "name": user_metadata.get("name", ""),
            "email": data.get("email", ""),
        }

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

    async def patch_preferences(
        self, user_id: uuid.UUID, updates: dict[str, Any]
    ) -> UserPreferences:
        """Partially update user preferences. Only provided fields are changed."""
        await self.user_repo.patch_preferences(user_id, updates)
        await self.redis.delete(f"user:{user_id}:preferences")
        return await self.get_preferences(user_id)

    # --- Broker ---

    async def get_broker_status(
        self, user_id: uuid.UUID, broker: BrokerAdapter | None = None
    ) -> dict[str, Any]:
        """Get broker connection status using adapter."""
        configs = await self.user_repo.get_broker_config(user_id)
        configured = len(configs) > 0

        if not configured and not broker:
            return {
                "configured": False,
                "connected": False,
                "equity": 0,
                "cash": 0,
                "errorMessage": "",
            }

        if broker:
            try:
                connected = await broker.test_connection()
                if not connected:
                    return {
                        "configured": configured,
                        "connected": False,
                        "equity": 0,
                        "cash": 0,
                        "errorMessage": "Broker authentication failed",
                    }
                account = await broker.get_account()
                return {
                    "configured": True,
                    "connected": True,
                    "equity": account.equity,
                    "cash": account.cash,
                    "errorMessage": "",
                }
            except Exception:
                return {
                    "configured": configured,
                    "connected": False,
                    "equity": 0,
                    "cash": 0,
                    "errorMessage": "Broker API connection failed",
                }

        return {
            "configured": configured,
            "connected": False,
            "equity": 0,
            "cash": 0,
            "errorMessage": "Broker adapter not available",
        }

    async def update_broker_config(
        self,
        user_id: uuid.UUID,
        api_key: str,
        secret_key: str,
        paper: bool,
        broker_type: str = "alpaca",
        portfolio_svc: PortfolioService | None = None,
    ) -> dict[str, Any]:
        """Update broker configuration and optionally sync positions."""
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
            await self.user_repo.upsert_broker_config(user_id, key, encrypted, broker_type)

        result: dict[str, Any] = {"configured": True, "connected": True}

        if portfolio_svc:
            try:
                from .brokers.factory import create_broker_adapter

                broker = await create_broker_adapter(user_id, self.user_repo)
                sync_result = await portfolio_svc.sync_with_broker(user_id, broker)
                result["positionsSynced"] = sync_result.get("positionsSynced", 0)
            except ValueError:
                result["positionsSynced"] = 0

        return result
