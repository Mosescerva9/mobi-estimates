"""Generic-Lane Scope Candidate Creation v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_generic_scope_draft_creates_blocked_scope_items_from_coverage(client):
    pid = _upload_process_and_verify(client)
    census = client.post(f"/api/v1/projects/{pid}/coverage/draft").json()

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    assert drafted.status_code == 200
    body = drafted.json()
    assert body["created_count"] == census["detected_trade_count"]
    assert body["skipped_count"] == 0

    electrical_items = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=electrical"
    ).json()
    assert electrical_items["total"] == 1
    item = electrical_items["items"][0]
    assert item["category_code"] == "generic_scope"
    assert item["review_status"] == "blocked"
    assert item["quantity_basis"] == "unknown"

    electrical_created = next(row for row in body["created"] if row["trade_code"] == "electrical")
    assert electrical_created["trade_module_version"] == "0.1.0"
    assert electrical_created["trade_data"]["generic_lane"] == "general_trade"
    assert electrical_created["trade_data"]["source_trade_code"] == "electrical"
    assert electrical_created["blocking_issues"][0]["code"] == "missing_quantity"

    detail = client.get(f"/api/v1/projects/{pid}/scope-items/{electrical_created['id']}")
    assert detail.status_code == 200
    evidence = detail.json()["evidence"]
    assert evidence[0]["extracted_text_quote"] == "PANEL SCHEDULE"
    assert bool(evidence[0]["requires_human_verification"]) is True

    coverage = client.get(f"/api/v1/projects/{pid}/coverage").json()["items"]
    electrical_row = next(row for row in coverage if row["trade_code"] == "electrical")
    assert electrical_row["disposition"] == "included_generic"
    assert electrical_row["status"] == "ready"

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is True
    assert validation["findings"] == []


def test_generic_scope_draft_is_idempotent(client):
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")

    first = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft").json()
    second = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft").json()

    assert first["created_count"] > 0
    assert second["created_count"] == 0
    assert second["skipped_count"] == first["created_count"]
    assert {row["reason"] for row in second["skipped"]} == {"active_scope_exists"}


def test_generic_scope_draft_unknown_project_404(client):
    resp = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/coverage/generic-scope/draft"
    )
    assert resp.status_code == 404
