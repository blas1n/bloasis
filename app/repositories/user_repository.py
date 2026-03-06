"""User repository — ORM-based data access for user_data schema."""

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

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        async with self.postgres.get_session() as session:
            result = await session.execute(select(UserRecord).where(UserRecord.user_id == user_id))
            return result.scalar_one_or_none()

    # --- Preferences ---

    async def get_preferences(self, user_id: str) -> UserPreferenceRecord | None:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def upsert_preferences(
        self,
        user_id: str,
        risk_profile: str,
        max_portfolio_risk: Decimal,
        max_position_size: Decimal,
        preferred_sectors: list[str],
        excluded_sectors: list[str],
        enable_notifications: bool,
        trading_enabled: bool,
    ) -> None:
        async with self.postgres.get_session() as session:
            existing = await session.get(UserPreferenceRecord, user_id)
            if existing:
                existing.risk_profile = risk_profile
                existing.max_portfolio_risk = max_portfolio_risk
                existing.max_position_size = max_position_size
                existing.preferred_sectors = preferred_sectors
                existing.excluded_sectors = excluded_sectors
                existing.enable_notifications = enable_notifications
                existing.trading_enabled = trading_enabled
            else:
                session.add(
                    UserPreferenceRecord(
                        user_id=user_id,
                        risk_profile=risk_profile,
                        max_portfolio_risk=max_portfolio_risk,
                        max_position_size=max_position_size,
                        preferred_sectors=preferred_sectors,
                        excluded_sectors=excluded_sectors,
                        enable_notifications=enable_notifications,
                        trading_enabled=trading_enabled,
                    )
                )

    async def update_trading_enabled(self, user_id: str, enabled: bool) -> None:
        async with self.postgres.get_session() as session:
            existing = await session.get(UserPreferenceRecord, user_id)
            if existing:
                existing.trading_enabled = enabled
            else:
                session.add(UserPreferenceRecord(user_id=user_id, trading_enabled=enabled))

    async def get_trading_enabled(self, user_id: str) -> bool:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord.trading_enabled).where(
                    UserPreferenceRecord.user_id == user_id
                )
            )
            value = result.scalar_one_or_none()
            return bool(value) if value is not None else False

    # --- Broker Config ---

    async def get_broker_config(self, user_id: str) -> list[BrokerConfigRecord]:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(BrokerConfigRecord).where(BrokerConfigRecord.user_id == user_id)
            )
            return list(result.scalars().all())

    async def upsert_broker_config(
        self, user_id: str, config_key: str, encrypted_value: str
    ) -> None:
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(BrokerConfigRecord).where(
                    BrokerConfigRecord.user_id == user_id,
                    BrokerConfigRecord.config_key == config_key,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.encrypted_value = encrypted_value
            else:
                session.add(
                    BrokerConfigRecord(
                        user_id=user_id,
                        config_key=config_key,
                        encrypted_value=encrypted_value,
                    )
                )

    async def get_active_trading_users(self, limit: int = 200) -> list[str]:
        """Get user IDs with trading enabled (for scheduler)."""
        async with self.postgres.get_session() as session:
            result = await session.execute(
                select(UserPreferenceRecord.user_id)
                .where(UserPreferenceRecord.trading_enabled.is_(True))
                .limit(limit)
            )
            return list(result.scalars().all())
