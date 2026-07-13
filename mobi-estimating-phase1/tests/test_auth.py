"""Tests for the shared-secret API-key gate (app.auth.ApiKeyAuthMiddleware)."""

from __future__ import annotations

import pytest

from app.config import settings

_KEY = "test-secret-key-123"
_PROTECTED = "/api/v1/cost-books"
_TENANT_HEADERS = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}


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


def test_rejects_blank_key_even_when_tenant_identity_is_present(client, keyed):
    resp = client.get(_PROTECTED, headers={"X-API-Key": "   ", **_TENANT_HEADERS})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_accepts_x_api_key_with_tenant_identity(client, keyed):
    resp = client.get(_PROTECTED, headers={"X-API-Key": _KEY, **_TENANT_HEADERS})
    assert resp.status_code == 200


def test_rejects_keyed_request_without_tenant_identity(client, keyed):
    resp = client.get(_PROTECTED, headers={"X-API-Key": _KEY})
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "tenant_identity_required"
    assert "tenant_project_context_required" in body["error"]["details"]["reason"]


@pytest.mark.parametrize(
    "headers,missing_field",
    [
        ({"X-Mobi-Tenant-Id": "tenant_a"}, "company_id"),
        ({"X-Mobi-Company-Id": "company_a"}, "tenant_id"),
    ],
)
def test_rejects_keyed_request_with_partial_tenant_identity(client, keyed, headers, missing_field):
    resp = client.get(_PROTECTED, headers={"X-API-Key": _KEY, **headers})
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "tenant_identity_required"
    assert f"tenant_project_context_required:{missing_field}" in body["error"]["details"]["reason"]


def test_rejects_keyed_request_with_malformed_tenant_identity(client, keyed):
    resp = client.get(
        _PROTECTED,
        headers={
            "X-API-Key": _KEY,
            "X-Mobi-Tenant-Id": "undefined",
            "X-Mobi-Company-Id": "company_a",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "tenant_identity_required"


def test_accepts_bearer_token_with_tenant_identity(client, keyed):
    resp = client.get(_PROTECTED, headers={"Authorization": f"Bearer {_KEY}", **_TENANT_HEADERS})
    assert resp.status_code == 200
