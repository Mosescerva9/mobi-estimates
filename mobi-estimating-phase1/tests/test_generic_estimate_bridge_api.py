"""Generic estimate draft bridge tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tests.test_generic_pricing_prep_api import _prepare_generic_scope


def _apply_quantity_and_pricing_for_trade(client, pid: str, trade_code: str, amount: str = "125.50") -> str:
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    reqs = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()["items"]
    req = next(row for row in reqs if row["trade_code"] == trade_code)
    client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{req['id']}/apply",
        json={"quantity": "4", "unit": "EA", "source": "staff_verified_takeoff"},
    )
    scope_item_id = req["scope_item_id"]
    resp = client.post(
        f"/api/v1/projects/{pid}/pricing/generic-inputs/{scope_item_id}/apply",
        json={
            "pricing_method": "unit_rate_needed",
            "amount": amount,
            "source": "verified_internal_unit_rate",
            "actor": "estimator-1",
            "note": "Verified unit rate for bridge fixture.",
        },
    )
    assert resp.status_code == 200
    return scope_item_id


def test_generic_estimate_bridge_creates_internal_draft_for_ready_scope(client):
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")

    resp = client.post(
        f"/api/v1/projects/{pid}/estimates/generic-draft",
        json={"name": "Bridge Draft"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 1
    assert body["summary"]["blocked_scope_item_count"] > 0
    assert body["summary"]["line_item_count"] == 1
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["summary"]["final_estimate_approved"] is False
    assert body["summary"]["external_messages"] is False
    assert body["summary"]["payments"] is False
    assert body["estimate"]["name"] == "Bridge Draft"
    assert body["version"]["status"] == "draft"
    assert body["version"]["approved_at"] is None
    assert body["version"]["config"]["source"] == "generic_estimate_bridge_v1"
    assert body["version"]["config"]["customer_delivery_ready"] is False
    assert body["line_items"][0]["scope_item_id"] == ready_scope_item_id
    assert body["line_items"][0]["status"] == "generic_pricing_basis"
    assert Decimal(body["line_items"][0]["direct_cost_total"]) == Decimal("502.00")
    assert Decimal(body["line_items"][0]["other_direct_cost"]) == Decimal("502.00")
    assert body["line_items"][0]["subcontract_cost"] == "0.00"
    assert body["line_items"][0]["components"][0]["source"] == "verified_internal_unit_rate"
    plumbing_blocked = next(row for row in body["blocked_scope_items"] if row["trade_code"] == "plumbing")
    blocked_codes = {b["code"] for b in plumbing_blocked["blockers"]}
    assert {"missing_quantity", "missing_unit_rate"} <= blocked_codes

    estimates = client.get(f"/api/v1/projects/{pid}/estimates").json()["items"]
    assert any(row["id"] == body["estimate"]["id"] for row in estimates)


def test_generic_estimate_bridge_blocks_malformed_ready_pricing_basis_without_error(client):
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        trade_data={
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {},
        },
        blocking_issues=[],
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    malformed = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in malformed["blockers"]} == {"invalid_amount"}
    assert body["version"]["status"] == "draft"
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_all_unready_creates_empty_safe_draft(client):
    pid = _prepare_generic_scope(client)
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["blocked_scope_item_count"] > 0
    assert body["summary"]["line_item_count"] == 0
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["line_items"] == []
    assert body["version"]["status"] == "draft"
    assert body["version"]["approved_at"] is None
    assert all(row["blockers"] for row in body["blocked_scope_items"])


def test_generic_estimate_bridge_unknown_project_404(client):
    resp = client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/estimates/generic-draft", json={})
    assert resp.status_code == 404
