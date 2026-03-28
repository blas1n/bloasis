"""Broker adapter factory — creates the appropriate adapter for a user.

Resolves per-user broker credentials from DB, falls back to global env settings.
"""

import uuid

import structlog

from ...config import settings
from ...core.broker import BrokerAdapter
from ...repositories.user_repository import UserRepository
from ...shared.utils.broker import decrypt_broker_credentials
from .alpaca import AlpacaAdapter
from .mock import MockBrokerAdapter

logger = structlog.get_logger(__name__)


async def create_broker_adapter(
    user_id: uuid.UUID,
    user_repo: UserRepository,
    broker_type: str = "alpaca",
) -> BrokerAdapter:
    """Create a broker adapter for the given user.

    Resolution order:
    1. If MOCK_BROKER_ENABLED → MockBrokerAdapter
    2. DB per-user broker_config → decrypt → adapter
    3. Global env fallback (ALPACA_API_KEY, ALPACA_SECRET_KEY)
    """
    if settings.mock_broker_enabled:
        return MockBrokerAdapter()

    configs = await user_repo.get_broker_config(user_id, broker_type)
    creds = decrypt_broker_credentials(configs)
    api_key = creds.get("api_key", "")
    secret_key = creds.get("secret_key", "")

    if not api_key or not secret_key:
        logger.warning(
            "broker_credentials_not_found", user_id=str(user_id), broker_type=broker_type
        )
        api_key = settings.alpaca_api_key
        secret_key = settings.alpaca_secret_key

    if not api_key or not secret_key:
        raise ValueError(
            f"No broker credentials configured for user {user_id} (broker_type={broker_type})"
        )

    if broker_type == "alpaca":
        return AlpacaAdapter(
            api_key=api_key,
            secret_key=secret_key,
            base_url=settings.alpaca_base_url,
        )

    raise ValueError(f"Unsupported broker type: {broker_type}")
