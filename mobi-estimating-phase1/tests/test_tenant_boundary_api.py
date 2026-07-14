"""Read-only tenant-boundary manifest endpoint tests (audit P0-2)."""

from __future__ import annotations

import pytest

from app.tenant_boundary import get_tenant_boundary_discovery, get_two_tenant_test_plan

ENDPOINTS = ("/tenant-boundary", "/api/v1/tenant-boundary")


@pytest.mark.parametrize("path", ENDPOINTS)
def test_tenant_boundary_endpoint_reports_truthful_blocked_posture(client, path):
    response = client.get(path)

    assert response.status_code == 200, response.text
    body = response.json()

    discovery = body["tenant_boundary"]
    assert discovery == get_tenant_boundary_discovery()
    assert discovery["schema_version"] == "tenant_boundary_plan_v1"
    assert discovery["tenant_isolation_ready"] is False
    assert discovery["release_start_allowed"] is False
    assert discovery["status"] == "blocked"
    assert discovery["blocked_gap_count"] >= 4

    plan = body["two_tenant_test_plan"]
    assert plan == get_two_tenant_test_plan()
    assert plan["execution_status"] == "planned_not_implemented"
    assert plan["allow_check_count"] >= 1
    assert plan["deny_check_count"] >= 4

    posture = body["release_posture"]
    assert posture == {
        "tenant_isolation_ready": False,
        "release_start_allowed": False,
        "status": "blocked",
        "reason": (
            "GPT-5.6 Sol audit PAUSE AND REPAIR: end-to-end tenant identity, "
            "storage/object isolation, queue/cache isolation, and model-call "
            "tenant context are not fully proven."
        ),
    }


@pytest.mark.parametrize("path", ENDPOINTS)
def test_tenant_boundary_endpoint_is_read_only(client, path):
    first = client.get(path).json()
    second = client.get(path).json()

    assert first == second
    for method in (client.post, client.put, client.patch, client.delete):
        response = method(path)
        assert response.status_code == 405, f"{method.__name__} should be rejected"


def test_tenant_boundary_endpoint_leaks_no_secrets(client):
    text = client.get("/tenant-boundary").text.lower()

    for forbidden in ("password", "secret", "token", "api_key", "apikey"):
        assert forbidden not in text, forbidden
