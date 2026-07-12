"""Read-only capability-registry manifest endpoint tests (audit P0-1).

These prove the system manifest is a truthful, read-only capability surface and
that final customer delivery stays locked/not enabled. Both the unversioned and
the ``/api/v1`` mount are exercised.
"""

from __future__ import annotations

from typing import Any

import pytest

from app import capability_registry as cr
from app.main import app
from app.proposals import service as proposal_service
from tests.conftest import prepare_approved_estimate

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


def test_delivery_lock_cannot_omit_canonical_capability_requirements():
    """A caller cannot unlock delivery by passing an empty required_capabilities tuple."""
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval={
            "approved": True,
            "approved_by": "Moses Cervantes",
            "approved_at": "2026-07-10T12:00:00+00:00",
            "approval_scope": "final_customer_delivery",
        },
        delivery_sources=[
            {
                "scope_item_id": "scope-1",
                "kind": "estimate_line_quantity_source",
                "source": "staff_verified_takeoff",
            },
            {
                "scope_item_id": "scope-1",
                "kind": "estimate_line_component_source",
                "source": "verified_cost_component",
            },
        ],
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
    assert lock["requirements"]["capabilities_delivery_grade"] is False
    assert lock["required_capabilities"] == list(cr.REQUIRED_DELIVERY_CAPABILITIES)
    gap_names = {gap["capability"] for gap in lock["capability_gaps"]}
    assert gap_names == set(cr.REQUIRED_DELIVERY_CAPABILITIES)
    assert "Required estimating capabilities are not production/accuracy-validated." in lock["reasons"]


def _customer_deliverable_openapi_operations() -> set[tuple[str, str]]:
    """Return customer-facing delivery/export operations from the live OpenAPI surface.

    This is an intentional regression tripwire: if a future route adds another
    proposal/export surface, the test below must fail until that route is either
    lock-enforced or deliberately classified out of the customer-deliverable set.
    """
    operations: set[tuple[str, str]] = set()
    for path, methods in app.openapi()["paths"].items():
        if (
            "/proposals" not in path
            and not path.endswith(("/export.json", "/export.csv", "/line-items", "/rollup"))
        ):
            continue
        for method in methods:
            if method in {"get", "post", "put", "patch", "delete"}:
                operations.add((method.upper(), path))
    return operations


def _create_locked_proposal_fixture(client, monkeypatch) -> dict[str, str]:
    pid, eid, evid, _final = prepare_approved_estimate(client)
    real_enforcer = proposal_service._enforce_customer_delivery_lock
    monkeypatch.setattr(proposal_service, "_enforce_customer_delivery_lock", lambda *args, **kwargs: None)
    try:
        proposal_resp = client.post(
            f"/api/v1/projects/{pid}/proposals",
            json={"name": "P0 lock fixture", "estimate_id": eid, "client_name": "Acme"},
        )
        assert proposal_resp.status_code == 201, proposal_resp.text
    finally:
        monkeypatch.setattr(proposal_service, "_enforce_customer_delivery_lock", real_enforcer)
    proposal_body = proposal_resp.json()
    return {
        "project_id": pid,
        "estimate_id": eid,
        "estimate_version_id": evid,
        "proposal_id": proposal_body["proposal"]["id"],
        "proposal_version_id": proposal_body["version"]["id"],
    }


def test_pricing_export_lock_preserves_test_only_component_metadata(monkeypatch):
    from app import routers_pricing

    scope_id = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setattr(
        routers_pricing.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [
                    {
                        "source": "verified_cost_component",
                        "component_source": "verified_cost_component",
                        "internal_testing_only": True,
                    }
                ],
                "evidence": [{"source": "reviewed_sheet_region"}],
            }
        ],
    )

    with pytest.raises(Exception) as exc_info:
        routers_pricing._enforce_pricing_export_delivery_lock({"id": "version-1", "status": "approved"})

    assert "test-only" in str(exc_info.value)


def test_pricing_export_lock_preserves_nested_test_only_component_metadata(monkeypatch):
    from app import routers_pricing

    scope_id = "22222222-2222-4222-8222-222222222223"
    monkeypatch.setattr(
        routers_pricing.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "source_metadata": {"synthetic_only": True},
                "components": [
                    {
                        "source": "verified_cost_component",
                        "component_source": "verified_cost_component",
                        "metadata": {"internal_testing_only": True},
                    }
                ],
                "evidence": [{"source": "reviewed_sheet_region"}],
            }
        ],
    )

    with pytest.raises(Exception) as exc_info:
        routers_pricing._enforce_pricing_export_delivery_lock({"id": "version-1", "status": "approved"})

    assert "test-only" in str(exc_info.value)


def test_pricing_export_lock_rejects_test_only_evidence_rows(monkeypatch):
    from app import routers_pricing

    scope_id = "22222222-2222-4222-8222-222222222224"
    monkeypatch.setattr(
        routers_pricing.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [{"source": "verified_cost_component"}],
                "evidence": [
                    {
                        "source": "reviewed_sheet_region",
                        "provenance_metadata": {"test_only": True},
                    }
                ],
            }
        ],
    )

    with pytest.raises(Exception) as exc_info:
        routers_pricing._enforce_pricing_export_delivery_lock({"id": "version-1", "status": "approved"})

    assert "Complete verified evidence" in str(exc_info.value)


def test_pricing_export_lock_rejects_evidence_without_source(monkeypatch):
    from app import routers_pricing

    scope_id = "22222222-2222-4222-8222-222222222225"
    monkeypatch.setattr(
        routers_pricing.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [{"source": "verified_cost_component"}],
                "evidence": [{"metadata": {"reviewed": True}}],
            }
        ],
    )

    with pytest.raises(Exception) as exc_info:
        routers_pricing._enforce_pricing_export_delivery_lock({"id": "version-1", "status": "approved"})

    assert "Complete verified evidence" in str(exc_info.value)


@pytest.mark.uses_real_delivery_lock
def test_every_customer_deliverable_route_is_delivery_lock_enforced(client, monkeypatch):
    ids = _create_locked_proposal_fixture(client, monkeypatch)

    route_cases: dict[tuple[str, str], tuple[str, dict[str, Any] | None]] = {
        (
            "GET",
            "/api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/export.json",
        ): (
            f"/api/v1/projects/{ids['project_id']}/estimates/{ids['estimate_id']}"
            f"/versions/{ids['estimate_version_id']}/export.json",
            None,
        ),
        (
            "GET",
            "/api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/export.csv",
        ): (
            f"/api/v1/projects/{ids['project_id']}/estimates/{ids['estimate_id']}"
            f"/versions/{ids['estimate_version_id']}/export.csv",
            None,
        ),
        (
            "GET",
            "/api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/line-items",
        ): (
            f"/api/v1/projects/{ids['project_id']}/estimates/{ids['estimate_id']}"
            f"/versions/{ids['estimate_version_id']}/line-items",
            None,
        ),
        (
            "GET",
            "/api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/rollup",
        ): (
            f"/api/v1/projects/{ids['project_id']}/estimates/{ids['estimate_id']}"
            f"/versions/{ids['estimate_version_id']}/rollup",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals"): (
            f"/api/v1/projects/{ids['project_id']}/proposals",
            None,
        ),
        ("POST", "/api/v1/projects/{project_id}/proposals"): (
            f"/api/v1/projects/{ids['project_id']}/proposals",
            {"name": "Blocked proposal", "estimate_id": ids["estimate_id"], "client_name": "Acme"},
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}/versions",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}",
            None,
        ),
        ("POST", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/issue"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/issue",
            {"actor": "tester"},
        ),
        ("POST", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/accept"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/accept",
            {"actor": "tester", "notes": "blocked"},
        ),
        ("POST", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/decline"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/decline",
            {"actor": "tester", "reason": "blocked"},
        ),
        ("POST", "/api/v1/projects/{project_id}/proposals/{proposal_id}/regenerate"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}/regenerate",
            {"actor": "tester"},
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/review-events"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/review-events",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.json"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/export.json",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.md"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/export.md",
            None,
        ),
        ("GET", "/api/v1/projects/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.html"): (
            f"/api/v1/projects/{ids['project_id']}/proposals/{ids['proposal_id']}"
            f"/versions/{ids['proposal_version_id']}/export.html",
            None,
        ),
    }

    discovered = _customer_deliverable_openapi_operations()
    assert discovered == set(route_cases), (
        "Customer-deliverable route surface changed; classify and gate any new route before exposing it.",
        sorted(discovered - set(route_cases)),
        sorted(set(route_cases) - discovered),
    )

    for (method, route_template), (url, json_body) in sorted(route_cases.items()):
        response = client.request(method, url, json=json_body)
        assert response.status_code == 409, (method, route_template, response.status_code, response.text)
        assert "final delivery gate" in response.text or "delivery gate" in response.text, (
            method,
            route_template,
            response.text,
        )
