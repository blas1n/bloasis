"""Broker credential helpers.

Centralizes Alpaca API credential decryption used by UserService and PortfolioService.
Falls back to global env settings when per-user credentials are not configured.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def decrypt_alpaca_credentials(configs: list) -> tuple[str, str]:
    """Decrypt Alpaca API credentials from broker config records.

    Args:
        configs: List of BrokerConfigRecord with config_key and encrypted_value.

    Returns:
        Tuple of (api_key, secret_key). Falls back to global env settings.
    """
    if not settings.fernet_key:
        return settings.alpaca_api_key, settings.alpaca_secret_key

    from cryptography.fernet import Fernet

    f = Fernet(settings.fernet_key.encode())
    creds: dict[str, str] = {}
    for cfg in configs:
        try:
            creds[cfg.config_key] = f.decrypt(cfg.encrypted_value.encode()).decode()
        except Exception:
            logger.warning("Failed to decrypt broker config key: %s", cfg.config_key)

    if "api_key" in creds and "secret_key" in creds:
        return creds["api_key"], creds["secret_key"]

    return settings.alpaca_api_key, settings.alpaca_secret_key
