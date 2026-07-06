"""Estimate readiness gate v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def _prepare_project(client) -> str:
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft")
    client.post(f"/api/v1/projects/{pid}/qa/findings/draft")
    return pid


def _resolve_quantities_and_pricing(client, pid: str) -> None:
    reqs = client.get(f"/api/v1/projects/{pid}/quantity-requirements").json()["items"]
    for req in reqs:
        client.post(
            f"/api/v1/projects/{pid}/quantity-requirements/{req['id']}/apply",
            json={"quantity": "10", "unit": req["suggested_unit"] or "EA", "source": "test_verified_quantity"},
        )
    scope_items = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"]
    for item in scope_items:
        detail = client.get(f"/api/v1/projects/{pid}/scope-items/{item['id']}").json()
        method = detail["trade_data"].get("pricing_method")
        if not method:
            continue
        client.post(
            f"/api/v1/projects/{pid}/pricing/generic-inputs/{item['id']}/apply",
            json={"pricing_method": method, "amount": "100", "source": "test_verified_pricing"},
        )
    client.post(f"/api/v1/projects/{pid}/qa/findings/draft")


def test_estimate_readiness_blocked_with_open_requirements(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/estimate-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["ready_for_owner_review"] is False
    assert body["customer_delivery_ready"] is False
    codes = {row["code"] for row in body["blockers"]}
    assert "open_quantity_requirements" in codes
    assert "critical_qa_findings" in codes


def test_estimate_readiness_ready_after_quantity_and_pricing_inputs(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    resp = client.get(f"/api/v1/projects/{pid}/estimate-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready_for_owner_review"
    assert body["ready_for_owner_review"] is True
    assert body["customer_delivery_ready"] is False
    assert body["summary"]["open_quantity_requirement_count"] == 0
    assert body["summary"]["missing_pricing_input_count"] == 0
    assert body["summary"]["critical_qa_finding_count"] == 0


def test_estimate_readiness_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/estimate-readiness").status_code == 404
