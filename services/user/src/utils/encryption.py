"""Fernet encryption for storing broker credentials securely."""

import logging

from cryptography.fernet import Fernet, InvalidToken

from ..config import config

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance from config key.

    Returns:
        Fernet instance for encryption/decryption.

    Raises:
        ValueError: If encryption key is not configured.
    """
    key = config.credential_encryption_key
    if not key:
        raise ValueError(
            "CREDENTIAL_ENCRYPTION_KEY not configured. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: Value to encrypt.

    Returns:
        Encrypted value as string.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string.

    Args:
        ciphertext: Encrypted value to decrypt.

    Returns:
        Decrypted plaintext string.

    Raises:
        ValueError: If decryption fails (invalid key or corrupted data).
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value - invalid encryption key or corrupted data")
        raise ValueError("Failed to decrypt credential - encryption key may have changed")
