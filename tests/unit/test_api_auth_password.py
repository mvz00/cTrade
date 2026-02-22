"""Tests for the change-password auth endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_no_auth(monkeypatch):
    """Create a test app with auth disabled and no password hash."""
    from ctrade.settings import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("CTRADE_AUTH__ENABLED", "false")
    monkeypatch.setenv("CTRADE_AUTH__PASSWORD_HASH", "")

    from ctrade.api.app import create_app
    app = create_app()
    yield app

    get_settings.cache_clear()


@pytest.fixture()
def client_no_auth(app_no_auth):
    return TestClient(app_no_auth)


@pytest.fixture()
def app_auth_enabled(monkeypatch):
    """Create a test app with auth enabled and a known password hash."""
    from ctrade.settings import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("CTRADE_AUTH__ENABLED", "true")
    monkeypatch.setenv("CTRADE_AUTH__SECRET_KEY", "test-secret-key-for-testing")
    # Hash of "testpass123" — generate fresh each run
    from ctrade.security.auth import hash_password
    test_hash = hash_password("testpass123")
    monkeypatch.setenv("CTRADE_AUTH__PASSWORD_HASH", test_hash)

    from ctrade.api.app import create_app
    app = create_app()
    yield app

    get_settings.cache_clear()


@pytest.fixture()
def auth_client(app_auth_enabled):
    return TestClient(app_auth_enabled)


def _get_token(client: TestClient, username: str = "admin", password: str = "testpass123") -> str:
    """Helper to get a JWT token."""
    resp = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestChangePasswordAuthDisabled:
    """When auth is disabled, change-password still works (no token needed)."""

    def test_change_password_returns_new_hash(self, client_no_auth):
        resp = client_no_auth.post("/api/v1/auth/change-password", json={
            "current_password": "anything",
            "new_password": "newsecret",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "new_password_hash" in data
        assert data["new_password_hash"].startswith("$2b$")
        assert "message" in data

    def test_change_password_hash_is_valid_bcrypt(self, client_no_auth):
        resp = client_no_auth.post("/api/v1/auth/change-password", json={
            "current_password": "anything",
            "new_password": "mynewpassword",
        })
        data = resp.json()

        # Verify the returned hash actually matches the new password
        from ctrade.security.auth import verify_password
        assert verify_password("mynewpassword", data["new_password_hash"])


class TestChangePasswordAuthEnabled:
    """When auth is enabled, change-password requires valid auth."""

    def test_change_password_returns_401_without_token(self, auth_client):
        resp = auth_client.post("/api/v1/auth/change-password", json={
            "current_password": "testpass123",
            "new_password": "newpassword",
        })
        assert resp.status_code == 401

    def test_change_password_returns_401_with_wrong_current_password(self, auth_client):
        token = _get_token(auth_client)
        resp = auth_client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "wrongpassword",
                "new_password": "newpassword",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "Current password is incorrect" in resp.json()["detail"]

    def test_change_password_success_with_valid_credentials(self, auth_client):
        token = _get_token(auth_client)
        resp = auth_client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "brandnewpassword",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "new_password_hash" in data
        assert data["new_password_hash"].startswith("$2b$")

        # The returned hash should match the new password
        from ctrade.security.auth import verify_password
        assert verify_password("brandnewpassword", data["new_password_hash"])

    def test_change_password_missing_fields_returns_422(self, auth_client):
        token = _get_token(auth_client)
        resp = auth_client.post(
            "/api/v1/auth/change-password",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
