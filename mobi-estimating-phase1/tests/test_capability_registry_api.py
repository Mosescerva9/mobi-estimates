"""Read-only capability-registry manifest endpoint tests (audit P0-1).

These prove the system manifest is a truthful, read-only capability surface and
that final customer delivery stays locked/not enabled. Both the unversioned and
the ``/api/v1`` mount are exercised.
"""

from __future__ import annotations

import pytest

from app import capability_registry as cr

ENDPOINTS = ("/capability-registry", "/api/v1/capability-registry")


@pytest.mark.parametrize("path", ENDPOINTS)
def test_capability_registry_endpoint_reports_truthful_locked_posture(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    registry = body["capability_registry"]
    assert registry["schema_version"] == "capability_registry_v1"
    assert registry["all_required_delivery_grade"] is False
    # No capability in this internal engine is delivery-grade.
    for name, entry in registry["capabilities"].items():
        assert entry["delivery_grade"] is False, name
    assert registry["capabilities"]["final_customer_delivery"]["stage"] == "planned"

    lock = body["customer_delivery_lock"]
    assert lock["fail_closed"] is True
    assert lock["final_customer_delivery_enabled"] is False
    assert lock["final_customer_delivery_stage"] == "planned"
    assert lock["all_required_delivery_grade"] is False
    # Fail-closed: no trade lane is accuracy-validated for customer delivery.
    assert lock["supported_customer_delivery_trades"] == []
    # Every required capability is reported as an open gap.
    gap_names = {gap["capability"] for gap in lock["capability_gaps"]}
    assert gap_names == set(cr.REQUIRED_DELIVERY_CAPABILITIES)

    posture = body["release_posture"]
    assert posture["paid_automated_estimating"] == "no_go"
    assert posture["autonomous_final_estimate_delivery"] == "no_go"
    assert posture["broad_multi_trade_accuracy_claims"] == "no_go"
    assert "PAUSE AND REPAIR" in posture["reason"]
    assert posture["final_delivery_requires"] == [
        "complete verified evidence",
        "accuracy-validated supported scope",
        "required internal reviews",
        "explicit owner approval",
    ]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_capability_registry_endpoint_matches_registry_source_of_truth(client, path):
    body = client.get(path).json()
    assert body["capability_registry"] == cr.get_capability_registry()


def test_capability_registry_endpoint_is_read_only(client):
    """A GET must not mutate anything: repeated calls are byte-identical and no
    write verbs are accepted on the manifest path."""
    first = client.get("/capability-registry").json()
    second = client.get("/capability-registry").json()
    assert first == second

    for method in (client.post, client.put, client.patch, client.delete):
        resp = method("/capability-registry")
        assert resp.status_code == 405, f"{method.__name__} should be rejected"


def test_capability_registry_endpoint_leaks_no_secrets(client):
    """The manifest must not expose secrets or configuration internals."""
    text = client.get("/capability-registry").text.lower()
    for forbidden in ("password", "secret", "token", "api_key", "apikey"):
        assert forbidden not in text, forbidden
