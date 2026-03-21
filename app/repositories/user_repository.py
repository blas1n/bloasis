"""User repository — ORM-based data access for user_data schema."""

import uuid as uuid_mod
from decimal import Decimal

from sqlalchemy import select

from shared.utils.postgres_client import PostgresClient

from .models import BrokerConfigRecord, UserPreferenceRecord, UserRecord


class UserRepository:
    def __init__(self, postgres: PostgresClient) -> None:
        self.postgres = postgres

    async def find_by_email(self, email: str) -> UserRecord | None:
        async with self.postgres.get_session() as session:
            result = await session.execute(select(UserRecord).where(UserRecord.email == email))
            return result.scalar_one_or_none()

    async def find_by_id(self, user_id: uuid_mod.UUID) -> UserRecord | None:
        async with self.postgres.get_session() as session:
            result = await session.execute(select(UserRecord).where(UserRecord.user_id == user_id))
            return result.scalar_one_or_none()

    # --- Preferences ---

    async def get_preferences(self, user_id: uuid_mod.UUID) -> UserPreferenceRecord | None:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def patch_preferences(
        self,
        user_id: uuid_mod.UUID,
        updates: dict[str, object],
    ) -> None:
        """Update only the provided preference fields. Creates record if missing."""
        allowed = {
            "risk_profile",
            "max_portfolio_risk",
            "max_position_size",
            "preferred_sectors",
            "excluded_sectors",
            "enable_notifications",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return

        async with self.postgres.get_session() as session:
            existing = await session.get(UserPreferenceRecord, user_id)
            if existing:
                for key, value in filtered.items():
                    setattr(existing, key, value)
            else:
                defaults: dict[str, object] = {
                    "risk_profile": "moderate",
                    "max_portfolio_risk": Decimal("0.20"),
                    "max_position_size": Decimal("0.10"),
                    "preferred_sectors": [],
                    "excluded_sectors": [],
                    "enable_notifications": True,
                }
                defaults.update(filtered)
                session.add(UserPreferenceRecord(user_id=user_id, **defaults))

    async def update_trading_enabled(self, user_id: uuid_mod.UUID, enabled: bool) -> None:
        async with self.postgres.get_session() as session:
            existing = await session.get(UserPreferenceRecord, user_id)
            if existing:
                existing.trading_enabled = enabled
            else:
                session.add(UserPreferenceRecord(user_id=user_id, trading_enabled=enabled))

    async def get_trading_enabled(self, user_id: uuid_mod.UUID) -> bool:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord.trading_enabled).where(
                    UserPreferenceRecord.user_id == user_id
                )
            )
            value = result.scalar_one_or_none()
            return bool(value) if value is not None else False

    # --- Broker Config (per-user, per-broker key-value) ---

    async def get_broker_config(
        self, user_id: uuid_mod.UUID, broker_type: str = "alpaca"
    ) -> list[BrokerConfigRecord]:
        """Get broker config entries for a specific user and broker type."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(BrokerConfigRecord).where(
                    BrokerConfigRecord.user_id == user_id,
                    BrokerConfigRecord.broker_type == broker_type,
                )
            )
            return list(result.scalars().all())

    async def upsert_broker_config(
        self,
        user_id: uuid_mod.UUID,
        config_key: str,
        encrypted_value: str,
        broker_type: str = "alpaca",
    ) -> None:
        async with self.postgres.get_session() as session:
            existing = await session.get(BrokerConfigRecord, (user_id, broker_type, config_key))
            if existing:
                existing.encrypted_value = encrypted_value
            else:
                session.add(
                    BrokerConfigRecord(
                        user_id=user_id,
                        broker_type=broker_type,
                        config_key=config_key,
                        encrypted_value=encrypted_value,
                    )
                )

    async def get_active_trading_users(self, limit: int = 200) -> list[uuid_mod.UUID]:
        """Get user IDs with trading enabled (for scheduler)."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord.user_id)
                .where(UserPreferenceRecord.trading_enabled.is_(True))
                .limit(limit)
            )
            return list(result.scalars().all())
