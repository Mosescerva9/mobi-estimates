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


def test_seed_generic_cost_provenance_creates_draft_only_shell(client):
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
