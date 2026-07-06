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


def test_customer_revision_decision_marks_rescope_task_without_delivery(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please add plumbing fixture rough-ins shown on P-201.",
    }).json()
    request_id = created["items"][0]["id"]

    resp = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "accepted",
        "reviewer": "moses",
        "notes": "Accepted for rescope/reprice.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted_for_rescope"
    assert body["payload"]["review_decision"]["follow_up_task"] == "rescope_reprice_required"
    assert body["payload"]["review_decision"]["rescope_blocker_scope_item_id"]
    assert body["rescope_blocker"]["category_code"] == "customer_revision_rescope"
    assert body["rescope_blocker"]["review_status"] == "blocked"
    assert body["rescope_blocker"]["trade_code"] == "plumbing"
    assert body["rescope_blocker"]["blocking_issues"][0]["code"] == "customer_revision_rescope_required"
    assert body["rescope_blocker"]["blocking_issues"][0]["customer_revision_request_id"] == request_id
    assert body["delivery_ready"] is False
    assert body["estimate_regenerated"] is False
    assert body["external_message_sent"] is False

    readiness = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    assert readiness["status"] == "blocked"
    assert any(blocker["code"] == "open_scope_blockers" for blocker in readiness["blockers"])
    rescope_blockers = [
        item for item in readiness["details"]["open_scope_blockers"]
        if item["scope_item_id"] == body["rescope_blocker"]["id"]
    ]
    assert rescope_blockers
    assert rescope_blockers[0]["blockers"][0]["customer_revision_request_id"] == request_id

    listed = client.get(f"/api/v1/projects/{pid}/customer-revisions").json()["items"]
    assert listed[0]["status"] == "accepted_for_rescope"


def test_customer_revision_decision_reject_and_double_decision_guard(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please remove extra lighting on E-101.",
    }).json()
    request_id = created["items"][0]["id"]
    first = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "rejected",
    })
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["status"] == "rejected"
    assert first_body["rescope_blocker"] is None
    second = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "accepted",
    })
    assert second.status_code == 409


def test_customer_revision_parser_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/customer-revisions").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Add outlets."
    }).status_code == 404


def test_customer_revision_needs_clarification_does_not_create_rescope_blocker(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Can you clarify if door hardware is included?",
    }).json()
    request_id = created["items"][0]["id"]

    resp = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "needs_clarification",
        "notes": "Need customer answer before scope changes.",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_customer_clarification"
    assert body["payload"]["review_decision"]["follow_up_task"] == "customer_clarification_required"
    assert body["rescope_blocker"] is None
    assert body["delivery_ready"] is False
    assert body["estimate_regenerated"] is False
    assert body["external_message_sent"] is False
