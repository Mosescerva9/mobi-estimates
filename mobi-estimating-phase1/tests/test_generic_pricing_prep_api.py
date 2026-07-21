"""Generic lane pricing-prep v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def _prepare_generic_scope(client) -> str:
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    return pid


def test_generic_pricing_method_assignment_updates_scope_metadata(client):
    pid = _prepare_generic_scope(client)

    resp = client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_count"] > 0
    assert body["method_counts"]["unit_rate_needed"] > 0

    electrical_items = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=electrical"
    ).json()["items"]
    assert len(electrical_items) == 1
    created = next(row for row in body["items"] if row["trade_code"] == "electrical")
    assert created["trade_data"]["pricing_method"] == "unit_rate_needed"
    assert created["trade_data"]["delivery_ready"] is False
    assert {b["code"] for b in created["blocking_issues"]} == {
        "missing_quantity", "missing_unit_rate"}


def test_generic_pricing_method_assignment_is_idempotent(client):
    pid = _prepare_generic_scope(client)
    first = client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={}).json()
    second = client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={}).json()
    assert second["updated_count"] == first["updated_count"]
    assert second["method_counts"] == first["method_counts"]


def test_generic_pricing_preserves_explicit_source_quantity_method(client):
    from tests.conftest import make_sheet_pdf

    pdf = make_sheet_pdf([{
        "number": "A001",
        "title": "SITE PLAN - EXISTING & TEMPORARY CONTROLS",
        "body": (
            "TEMPORARY FENCE ENCLOSURE WITH MESH SCREEN. "
            "PROVIDE GATES FOR PEDESTRIAN AND VEHICLE ACCESS.\n"
            "4 FT. EMERGENCY EGRESS GATE"
        ),
    }])
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Explicit Gate Pricing Prep"},
        files={"plan": ("gate-plan.pdf", pdf, "application/pdf")},
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process").status_code == 202
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    assert client.patch(
        f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
        json={
            "verified_sheet_number": "A001",
            "verified_sheet_title": "SITE PLAN - EXISTING & TEMPORARY CONTROLS",
            "review_status": "verified",
        },
    ).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/coverage/draft").status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft").status_code == 200

    body = client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={}).json()
    item = next(row for row in body["items"] if row["trade_code"] == "architectural_general")
    assert item["trade_data"]["explicit_subscope_only"] is True
    assert item["trade_data"]["quantity_method"] == "explicit_source_dimension_review_required"
    assert item["review_status"] == "blocked"


def test_generic_pricing_input_apply_clears_pricing_blocker_after_quantity(client):
    pid = _prepare_generic_scope(client)
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    reqs = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()["items"]
    electrical_req = next(row for row in reqs if row["trade_code"] == "electrical")
    client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{electrical_req['id']}/apply",
        json={"quantity": "42", "unit": "EA", "source": "staff_verified_takeoff"},
    )
    scope_item_id = electrical_req["scope_item_id"]
    resp = client.post(
        f"/api/v1/projects/{pid}/pricing/generic-inputs/{scope_item_id}/apply",
        json={
            "pricing_method": "unit_rate_needed",
            "amount": "125.50",
            "source": "verified_internal_unit_rate",
            "actor": "estimator-1",
            "note": "Verified unit rate for test fixture count.",
        },
    )
    assert resp.status_code == 200
    item = resp.json()
    assert item["review_status"] == "pending"
    assert item["conflict_status"] == "none"
    assert item["trade_data"]["pricing_ready"] is True
    assert item["trade_data"]["pricing_basis"]["amount"] == "125.50"
    assert {b["code"] for b in item["blocking_issues"]} == set()

    qa = client.post(f"/api/v1/projects/{pid}/qa/findings/draft").json()
    electrical_codes = {row["code"] for row in qa["items"] if row.get("trade_code") == "electrical"}
    assert "missing_quantity" not in electrical_codes
    assert "missing_unit_rate" not in electrical_codes


def test_generic_pricing_input_apply_rejects_method_mismatch(client):
    pid = _prepare_generic_scope(client)
    body = client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={}).json()
    electrical = next(row for row in body["items"] if row["trade_code"] == "electrical")
    resp = client.post(
        f"/api/v1/projects/{pid}/pricing/generic-inputs/{electrical['id']}/apply",
        json={"pricing_method": "quote_based", "amount": "125", "source": "bad_source"},
    )
    assert resp.status_code == 409


def test_generic_cost_provenance_seed_creates_draft_shell(client):
    pid = _prepare_generic_scope(client)
    resp = client.post(f"/api/v1/projects/{pid}/pricing/generic-cost-provenance/seed", json={
        "effective_date": "2026-01-01",
        "pricing_date": "2026-07-01",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["published"] is False
    assert body["pricing_ready"] is False
    assert body["version"]["status"] == "draft"
    assert body["sources"][0]["verified"] is False

    cbid = body["cost_book"]["id"]
    vid = body["version"]["id"]
    version = client.get(f"/api/v1/cost-books/{cbid}/versions/{vid}").json()
    assert version["status"] == "draft"


def test_pricing_prep_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={}).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/pricing/generic-cost-provenance/seed", json={
        "effective_date": "2026-01-01",
        "pricing_date": "2026-07-01",
    }).status_code == 404
