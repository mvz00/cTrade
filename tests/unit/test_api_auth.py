"""Tests for the auth API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(monkeypatch):
    """Create a test FastAPI app with auth disabled."""
    from ctrade.settings import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("CTRADE_AUTH__ENABLED", "false")

    from ctrade.api.app import create_app
    app = create_app()
    yield app

    get_settings.cache_clear()


@pytest.fixture()
def client(app):
    return TestClient(app)


class TestLoginEndpoint:
    def test_login_success_auth_disabled(self, client):
        """When auth is disabled (default for tests), any credentials work."""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "anything",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in_minutes"] > 0

    def test_login_returns_valid_jwt(self, client):
        """The returned token can be used in auth headers."""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "test",
        })
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        # Token should be a valid-looking JWT (3 dot-separated segments)
        assert len(token.split(".")) == 3

    def test_login_empty_body(self, client):
        """Missing fields should return 422."""
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422


class TestTokenResponseShape:
    def test_response_has_required_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "test",
        })
        data = resp.json()
        assert "access_token" in data
        assert "token_type" in data
        assert "expires_in_minutes" in data
