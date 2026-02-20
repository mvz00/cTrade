"""Tests for security modules (vault and auth)."""

import pytest

from ctrade.core.exceptions import AuthenticationError, EncryptionError
from ctrade.security.auth import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)
from ctrade.security.vault import Vault


class TestVault:
    """Tests for the Vault encryption module."""

    def test_encrypt_decrypt_roundtrip(self):
        """Data should survive encrypt/decrypt cycle."""
        key = Vault.generate_key()
        vault = Vault(key)

        plaintext = "my-secret-api-key-12345"
        ciphertext = vault.encrypt(plaintext)
        result = vault.decrypt(ciphertext)

        assert result == plaintext

    def test_ciphertext_differs_from_plaintext(self):
        """Encrypted data should not contain the original plaintext."""
        key = Vault.generate_key()
        vault = Vault(key)

        plaintext = "my-secret-api-key"
        ciphertext = vault.encrypt(plaintext)

        assert plaintext.encode() not in ciphertext

    def test_wrong_key_fails(self):
        """Decryption with a different key should fail."""
        vault1 = Vault(Vault.generate_key())
        vault2 = Vault(Vault.generate_key())

        ciphertext = vault1.encrypt("secret")

        with pytest.raises(EncryptionError):
            vault2.decrypt(ciphertext)

    def test_empty_key_raises(self):
        """Vault with empty key should raise on operations."""
        vault = Vault("")

        with pytest.raises(EncryptionError):
            vault.encrypt("data")

    def test_generate_key_is_unique(self):
        """Each generated key should be different."""
        key1 = Vault.generate_key()
        key2 = Vault.generate_key()
        assert key1 != key2


class TestAuth:
    """Tests for JWT authentication."""

    def test_password_hash_and_verify(self):
        """Password hashing and verification should work."""
        password = "my-secure-password"
        hashed = hash_password(password)

        assert verify_password(password, hashed)
        assert not verify_password("wrong-password", hashed)

    def test_create_and_verify_token(self):
        """JWT token creation and verification should work."""
        secret = "test-secret-key"
        token = create_access_token("testuser", secret)
        subject = verify_access_token(token, secret)

        assert subject == "testuser"

    def test_invalid_token_raises(self):
        """Invalid token should raise AuthenticationError."""
        with pytest.raises(AuthenticationError):
            verify_access_token("invalid.token.here", "secret")

    def test_wrong_secret_raises(self):
        """Token verified with wrong secret should raise."""
        token = create_access_token("testuser", "correct-secret")

        with pytest.raises(AuthenticationError):
            verify_access_token(token, "wrong-secret")
