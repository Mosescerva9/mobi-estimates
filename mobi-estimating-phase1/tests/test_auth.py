"""Tests for the shared-secret API-key gate (app.auth.ApiKeyAuthMiddleware)."""

from __future__ import annotations

import pytest

from app.config import settings

_KEY = "test-secret-key-123"
_PROTECTED = "/api/v1/cost-books"


@pytest.fixture
def keyed(monkeypatch):
    """Enable the API-key gate for the duration of a test."""
    monkeypatch.setattr(settings, "api_key", _KEY)
    yield


def test_open_when_no_key_configured(client):
    # Default posture (no MOBI_API_KEY): the gate is a no-op.
    assert settings.api_key is None
    assert client.get(_PROTECTED).status_code == 200


def test_health_probes_exempt_even_with_key(client, keyed):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_rejects_request_without_key(client, keyed):
    resp = client.get(_PROTECTED)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_rejects_wrong_key(client, keyed):
    resp = client.get(_PROTECTED, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_accepts_x_api_key(client, keyed):
    resp = client.get(_PROTECTED, headers={"X-API-Key": _KEY})
    assert resp.status_code == 200


def test_accepts_bearer_token(client, keyed):
    resp = client.get(_PROTECTED, headers={"Authorization": f"Bearer {_KEY}"})
    assert resp.status_code == 200
