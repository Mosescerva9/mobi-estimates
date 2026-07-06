"""Project Quantity Backbone v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def _prepare_quantity_backbone(client) -> str:
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    return pid


def test_quantity_requirements_draft_from_missing_quantity_scope(client):
    pid = _prepare_quantity_backbone(client)

    resp = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] > 0
    electrical = next(item for item in body["items"] if item["trade_code"] == "electrical")
    assert electrical["requirement_type"] == "quantity_needed"
    assert electrical["suggested_method"] == "takeoff_or_schedule_count"
    assert electrical["suggested_unit"] == "EA"
    assert electrical["payload"]["pricing_method"] == "unit_rate_needed"

    listed = client.get(f"/api/v1/projects/{pid}/quantity-requirements").json()
    assert listed["total"] == body["created_count"]


def test_quantity_requirements_draft_is_idempotent(client):
    pid = _prepare_quantity_backbone(client)
    first = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()
    second = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()
    assert first["created_count"] > 0
    assert second["created_count"] == 0
    assert second["skipped_count"] == first["created_count"]
    assert {row["reason"] for row in second["skipped"]} == {"requirement_exists"}


def test_quantity_requirement_apply_updates_scope_and_resolves_requirement(client):
    pid = _prepare_quantity_backbone(client)
    draft = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()
    electrical = next(item for item in draft["items"] if item["trade_code"] == "electrical")

    resp = client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{electrical['id']}/apply",
        json={
            "quantity": "42",
            "unit": "EA",
            "quantity_basis": "manual_reviewer_entry",
            "source": "staff_verified_takeoff",
            "actor": "estimator-1",
            "note": "Counted fixtures from verified schedule.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requirement"]["status"] == "resolved"
    assert body["requirement"]["payload"]["applied_quantity"]["quantity"] == "42"
    item = body["scope_item"]
    assert item["quantity"] == "42"
    assert item["unit"] == "EA"
    assert item["quantity_basis"] == "manual_reviewer_entry"
    blocker_codes = {b["code"] for b in item["blocking_issues"]}
    assert "missing_quantity" not in blocker_codes
    assert "missing_unit_rate" in blocker_codes
    assert item["review_status"] == "blocked"

    again = client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{electrical['id']}/apply",
        json={"quantity": "43", "unit": "EA"},
    )
    assert again.status_code == 409


def test_quantity_requirement_apply_rejects_invalid_quantity(client):
    pid = _prepare_quantity_backbone(client)
    req = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()["items"][0]
    resp = client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{req['id']}/apply",
        json={"quantity": "0", "unit": "EA"},
    )
    assert resp.status_code == 422


def test_quantity_requirements_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/quantity-requirements").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").status_code == 404
