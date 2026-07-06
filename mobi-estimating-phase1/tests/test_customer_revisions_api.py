"""Customer Revision Parser / Workflow v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_customer_revision_parser_creates_structured_requests(client):
    pid = _upload_process_and_verify(client)
    resp = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "source": "customer_email",
        "actor": "customer",
        "text": """
        1. Please exclude the extra lighting on E-101.
        2. Add plumbing fixture rough-ins shown on P-201.
        3. Can you clarify if door hardware is included?
        """,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 3
    actions = {item["action"] for item in body["items"]}
    assert {"exclude", "include", "clarify"} <= actions
    trades = {item["trade_code"] for item in body["items"]}
    assert {"electrical", "plumbing", "doors_hardware"} <= trades
    electrical = next(item for item in body["items"] if item["trade_code"] == "electrical")
    assert electrical["payload"]["sheet_refs"] == ["E-101"]

    listed = client.get(f"/api/v1/projects/{pid}/customer-revisions").json()
    assert listed["total"] == 3
    assert all(item["status"] == "open" for item in listed["items"])


def test_customer_revision_parser_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/customer-revisions").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Add outlets."
    }).status_code == 404
