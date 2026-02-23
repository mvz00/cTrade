"""Authentication router — login and change-password endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ctrade.api.deps import get_app_settings, get_current_user
from ctrade.api.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    TokenResponse,
)
from ctrade.settings import AppSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    settings: AppSettings = Depends(get_app_settings),
) -> TokenResponse:
    """Authenticate and return a JWT access token.

    When auth is disabled (``CTRADE_AUTH__ENABLED=false``), any credentials
    are accepted — useful for local development.
    """
    auth = settings.auth

    if auth.enabled:
        # Validate username
        if body.username != auth.username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Validate password
        if auth.password_hash:
            from ctrade.security.auth import verify_password

            if not verify_password(body.password, auth.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                )
        else:
            # SECURITY: When auth is enabled but no password_hash is set,
            # reject login instead of silently accepting any password.
            logger.error(
                "Auth is enabled but no password_hash configured for '%s'. "
                "Login rejected. Set CTRADE_AUTH__PASSWORD_HASH (double underscore).",
                auth.username,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Authentication is enabled but no password is configured. "
                    "Set CTRADE_AUTH__PASSWORD_HASH env var (note: double underscore)."
                ),
            )

    from ctrade.security.auth import create_access_token

    token = create_access_token(
        subject=body.username,
        secret_key=auth.secret_key.get_secret_value(),
        algorithm=auth.algorithm,
        expires_minutes=auth.access_token_expire_minutes,
    )

    return TokenResponse(
        access_token=token,
        expires_in_minutes=auth.access_token_expire_minutes,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    settings: AppSettings = Depends(get_app_settings),
    _user: str = Depends(get_current_user),
) -> ChangePasswordResponse:
    """Change password — returns the new bcrypt hash to put in .env."""
    auth = settings.auth

    # Verify current password if hash is set
    if auth.password_hash:
        from ctrade.security.auth import verify_password

        if not verify_password(body.current_password, auth.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )

    from ctrade.security.auth import hash_password

    new_hash = hash_password(body.new_password)

    return ChangePasswordResponse(
        message="Password changed. Update CTRADE_AUTH__PASSWORD_HASH in your .env file.",
        new_password_hash=new_hash,
    )
