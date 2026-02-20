"""Dashboard authentication using JWT tokens."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from ctrade.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    subject: str,
    secret_key: str,
    algorithm: str = "HS256",
    expires_minutes: int = 1440,
) -> str:
    """Create a JWT access token.

    Args:
        subject: The token subject (typically username).
        secret_key: Secret key for signing.
        algorithm: JWT algorithm.
        expires_minutes: Token expiration in minutes.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def verify_access_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> str:
    """Verify a JWT access token and return the subject.

    Args:
        token: The JWT token string.
        secret_key: Secret key used for signing.
        algorithm: JWT algorithm.

    Returns:
        The token subject (username).

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        subject: str | None = payload.get("sub")
        if subject is None:
            raise AuthenticationError("Token has no subject")
        return subject
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {e}") from e
