"""Broker credential helpers.

Centralizes broker API credential decryption used by adapter factory.
Falls back to global env settings when per-user credentials are not configured.
"""

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def decrypt_broker_credentials(configs: list[Any]) -> dict[str, str]:
    """Decrypt broker API credentials from broker config records.

    Args:
        configs: List of BrokerConfigRecord with config_key and encrypted_value.

    Returns:
        Dict mapping config_key to decrypted value (e.g. {"api_key": "...", "secret_key": "..."}).
        Falls back to global env settings for Alpaca keys if decryption fails.
    """
    if not settings.fernet_key:
        return {
            "api_key": settings.alpaca_api_key,
            "secret_key": settings.alpaca_secret_key,
        }

    from cryptography.fernet import Fernet, InvalidToken

    f = Fernet(settings.fernet_key.encode())
    creds: dict[str, str] = {}
    for cfg in configs:
        try:
            creds[cfg.config_key] = f.decrypt(cfg.encrypted_value.encode()).decode()
        except (InvalidToken, ValueError):
            logger.warning("Failed to decrypt broker config key: %s", cfg.config_key)

    if "api_key" in creds and "secret_key" in creds:
        return creds

    return {
        "api_key": settings.alpaca_api_key,
        "secret_key": settings.alpaca_secret_key,
    }


def decrypt_alpaca_credentials(configs: list[Any]) -> tuple[str, str]:
    """Decrypt Alpaca API credentials (backward-compatible wrapper).

    Returns:
        Tuple of (api_key, secret_key).
    """
    creds = decrypt_broker_credentials(configs)
    return creds.get("api_key", ""), creds.get("secret_key", "")
