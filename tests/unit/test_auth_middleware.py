"""Tests for auth middleware."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_auth_enabled(monkeypatch):
    """Create a test app with auth enabled."""
    # Clear the cached settings so new env vars take effect
    from ctrade.settings import get_settings
    get_settings.cache_clear()

    monkeypatch.setenv("CTRADE_AUTH__ENABLED", "true")
    monkeypatch.setenv("CTRADE_AUTH__SECRET_KEY", "test-secret-key-for-testing")
    monkeypatch.setenv("CTRADE_AUTH__PASSWORD_HASH", "")  # no hash = accept any password

    from ctrade.api.app import create_app
    app = create_app()
    yield app

    get_settings.cache_clear()


@pytest.fixture()
def auth_client(app_auth_enabled):
    return TestClient(app_auth_enabled)


class TestPublicPaths:
    def test_health_always_public(self, auth_client):
        resp = auth_client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_login_always_public(self, auth_client):
        resp = auth_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "test",
        })
        assert resp.status_code == 200

    def test_docs_always_public(self, auth_client):
        resp = auth_client.get("/api/docs")
        assert resp.status_code == 200


class TestProtectedPaths:
    def test_protected_route_returns_401_without_token(self, auth_client):
        resp = auth_client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 401
        assert "Missing authentication token" in resp.json()["detail"]

    def test_protected_route_returns_401_with_invalid_token(self, auth_client):
        resp = auth_client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert resp.status_code == 401

    def test_protected_route_succeeds_with_valid_token(self, auth_client):
        # First get a valid token
        login_resp = auth_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "test",
        })
        token = login_resp.json()["access_token"]

        # Use it to access protected endpoint
        resp = auth_client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
