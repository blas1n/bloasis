"""Repository for broker configuration persistence."""

import logging
from typing import Optional

from shared.utils import PostgresClient
from sqlalchemy import select

from ..models import BrokerConfigRecord
from ..utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class BrokerConfigRepository:
    """Repository for user_data.broker_config table."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        """Initialize the repository with a PostgreSQL client.

        Args:
            postgres_client: PostgreSQL client for database operations.
        """
        self.postgres = postgres_client

    async def get_config(self, key: str) -> Optional[str]:
        """Get a decrypted configuration value by key.

        Args:
            key: Configuration key.

        Returns:
            Decrypted value if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(BrokerConfigRecord).where(BrokerConfigRecord.config_key == key)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                return decrypt_value(record.encrypted_value)
            return None

    async def set_config(self, key: str, value: str) -> None:
        """Set an encrypted configuration value.

        Args:
            key: Configuration key.
            value: Plaintext value to encrypt and store.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        encrypted = encrypt_value(value)

        async with self.postgres.get_session() as session:
            stmt = select(BrokerConfigRecord).where(BrokerConfigRecord.config_key == key)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                record.encrypted_value = encrypted
            else:
                record = BrokerConfigRecord(
                    config_key=key,
                    encrypted_value=encrypted,
                )
                session.add(record)

            await session.commit()

    async def get_all_broker_config(self) -> dict[str, str]:
        """Get all broker configuration values (decrypted).

        Returns:
            Dictionary of key-value pairs.
        """
        if not self.postgres:
            return {}

        async with self.postgres.get_session() as session:
            stmt = select(BrokerConfigRecord)
            result = await session.execute(stmt)
            records = result.scalars().all()

            config_dict: dict[str, str] = {}
            for record in records:
                try:
                    config_dict[record.config_key] = decrypt_value(record.encrypted_value)
                except ValueError:
                    logger.warning(f"Failed to decrypt config key: {record.config_key}")
            return config_dict

    async def is_configured(self) -> bool:
        """Check if broker credentials are configured.

        Returns:
            True if at least alpaca_api_key exists.
        """
        if not self.postgres:
            return False

        async with self.postgres.get_session() as session:
            stmt = select(BrokerConfigRecord).where(
                BrokerConfigRecord.config_key == "alpaca_api_key"
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
