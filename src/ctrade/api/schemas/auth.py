"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Credentials for login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    """Change password response — returns the new hash for .env."""

    message: str
    new_password_hash: str
