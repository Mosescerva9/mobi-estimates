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


def test_delivery_source_classification_fails_closed_on_malformed_container():
    """Malformed source collections must block delivery instead of crashing.

    The delivery lock receives provenance from multiple workflow surfaces. If a
    caller accidentally passes ``None``/an object instead of a list, the lock must
    report unverified evidence and stay closed, never throw a TypeError or treat
    missing provenance as a clean source set.
    """
    source_check = cr.classify_delivery_sources(None)

    assert source_check["malformed_source_collection_count"] == 1
    assert source_check["test_only_source_count"] == 1
    assert source_check["no_test_only_delivery_evidence"] is False


def test_delivery_lock_handles_malformed_delivery_sources_without_unlocking():
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval={
            "approved": True,
            "approved_by": "Moses Cervantes",
            "approved_at": "2026-07-10T12:00:00+00:00",
            "approval_scope": "final_customer_delivery",
        },
        delivery_sources=None,  # type: ignore[arg-type]
        supported_scope=True,
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "scope-1"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["scope-1"],
        required_capabilities=(),
    )

    assert lock["delivery_unlocked"] is False
    assert lock["source_check"]["malformed_source_collection_count"] == 1
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert "Estimate relies on test-only or unverified-provenance sources." in lock["reasons"]
