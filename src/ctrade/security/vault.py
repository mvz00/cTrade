"""API key encryption and decryption using Fernet symmetric encryption.

Exchange API credentials are encrypted before storage in the database
and decrypted only when needed for API calls.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from ctrade.core.exceptions import EncryptionError

logger = logging.getLogger(__name__)


class Vault:
    """Handles encryption/decryption of sensitive data using Fernet."""

    def __init__(self, encryption_key: str) -> None:
        """Initialize the vault with a Fernet encryption key.

        Args:
            encryption_key: A valid Fernet key (base64-encoded 32-byte key).
                Generate with: Fernet.generate_key().decode()
        """
        if not encryption_key:
            logger.warning("No encryption key provided. Vault operations will fail.")
            self._fernet: Fernet | None = None
            return

        try:
            self._fernet = Fernet(encryption_key.encode())
        except (ValueError, Exception) as e:
            raise EncryptionError(f"Invalid encryption key: {e}") from e

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string and return the ciphertext as bytes."""
        if self._fernet is None:
            raise EncryptionError("Vault not initialized: no encryption key provided")
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt ciphertext bytes back to a string."""
        if self._fernet is None:
            raise EncryptionError("Vault not initialized: no encryption key provided")
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as e:
            raise EncryptionError("Failed to decrypt: invalid token or wrong key") from e

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key."""
        return Fernet.generate_key().decode()
