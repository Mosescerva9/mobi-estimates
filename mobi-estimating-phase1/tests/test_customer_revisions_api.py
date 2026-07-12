"""Customer Revision Parser / Workflow v1 tests."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from app.customer_revisions import RevisionDecisionError, _dumps, decide_revision_request
from app.database import get_connection
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
    assert body["rescope_blocker"]["tenant_id"] == "test_tenant"
    assert body["rescope_blocker"]["company_id"] == "test_company"
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

    resolved = client.post(
        f"/api/v1/projects/{pid}/customer-revisions/{request_id}/resolve-rescope",
        json={"actor": "moses", "notes": "Rescope applied to internal scope."},
    )
    assert resolved.status_code == 200
    resolved_body = resolved.json()
    assert resolved_body["status"] == "rescope_resolved"
    assert resolved_body["customer_delivery_ready"] is False
    assert resolved_body["delivery_ready"] is False
    assert resolved_body["estimate_regenerated"] is False
    assert resolved_body["external_message_sent"] is False
    assert resolved_body["version"]["version_number"] == 1
    assert resolved_body["version"]["blocker_scope_item_id"] == body["rescope_blocker"]["id"]
    assert resolved_body["version"]["before_snapshot"]["scope_item"]["review_status"] == "blocked"
    assert resolved_body["version"]["after_snapshot"]["scope_item"]["review_status"] == "pending"
    assert resolved_body["version"]["changed_items"][0]["customer_revision_request_id"] == request_id
    assert resolved_body["version"]["readiness_snapshot"]["customer_delivery_ready"] is False

    after_readiness = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    rescope_blockers_after = [
        item for item in after_readiness["details"]["open_scope_blockers"]
        if item["scope_item_id"] == body["rescope_blocker"]["id"]
    ]
    assert rescope_blockers_after == []

    versions = client.get(
        f"/api/v1/projects/{pid}/customer-revisions/{request_id}/rescope-versions"
    ).json()
    assert versions["total"] == 1
    assert versions["items"][0]["id"] == resolved_body["version"]["id"]

    listed_after = client.get(f"/api/v1/projects/{pid}/customer-revisions").json()["items"]
    assert listed_after[0]["status"] == "rescope_resolved"

    double_resolve = client.post(
        f"/api/v1/projects/{pid}/customer-revisions/{request_id}/resolve-rescope",
        json={"actor": "moses"},
    )
    assert double_resolve.status_code == 409


def test_customer_revision_rescope_carries_tenant_identity_to_run_and_scope_item(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please add plumbing fixture rough-ins shown on P-201.",
    }).json()
    request_id = created["items"][0]["id"]

    resp = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "accepted",
    })

    assert resp.status_code == 200
    scope_item_id = resp.json()["rescope_blocker"]["id"]
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                scope_items.tenant_id AS scope_tenant_id,
                scope_items.company_id AS scope_company_id,
                extraction_runs.tenant_id AS run_tenant_id,
                extraction_runs.company_id AS run_company_id,
                extraction_runs.project_id AS run_project_id
            FROM scope_items
            JOIN extraction_runs ON extraction_runs.id = scope_items.extraction_run_id
            WHERE scope_items.id=?
            """,
            (scope_item_id,),
        ).fetchone()

    assert dict(row) == {
        "scope_tenant_id": "test_tenant",
        "scope_company_id": "test_company",
        "run_tenant_id": "test_tenant",
        "run_company_id": "test_company",
        "run_project_id": pid,
    }


def test_customer_revision_rescope_fails_closed_when_project_identity_missing(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please add plumbing fixture rough-ins shown on P-201.",
    }).json()
    request_id = created["items"][0]["id"]
    with get_connection() as conn:
        conn.execute("UPDATE projects SET tenant_id=NULL WHERE id=?", (pid,))
        conn.commit()

    with pytest.raises(RevisionDecisionError, match="tenant-scoped project identity") as exc_info:
        decide_revision_request(UUID(pid), UUID(request_id), decision="accepted")

    assert exc_info.value.code == "tenant_unscoped"
    with get_connection() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE project_id=?", (pid,)
        ).fetchone()[0]
        scope_count = conn.execute(
            "SELECT COUNT(*) FROM scope_items WHERE project_id=?", (pid,)
        ).fetchone()[0]
        request_status = conn.execute(
            "SELECT status FROM customer_revision_requests WHERE id=?", (request_id,)
        ).fetchone()[0]

    assert run_count == 0
    assert scope_count == 0
    assert request_status == "open"


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


def test_customer_revision_rescope_resolution_requires_accepted_request(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please remove extra lighting on E-101.",
    }).json()
    request_id = created["items"][0]["id"]

    unresolved = client.post(
        f"/api/v1/projects/{pid}/customer-revisions/{request_id}/resolve-rescope",
        json={"actor": "moses"},
    )

    assert unresolved.status_code == 409



def test_customer_safe_revision_history_sanitizes_internal_fields(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "source": "customer_email",
        "actor": "pm_jane_internal",
        "text": "Please add secret internal reviewer notes from BOE_REVIEW on E-101 and PM_JANE.",
    }).json()
    request_id = created["items"][0]["id"]
    unsafe_payload = {
        "raw_text": "raw secret pricing/reprice text from Moses and reviewer PM_JANE",
        "sheet_refs": ["E-101", "PM_JANE", "internal note", "A 2.01"],
        "review_decision": {
            "decision": "accepted",
            "reviewer": "Moses Internal",
            "notes": "Do not expose this internal note or pricing basis.",
            "follow_up_task": "unknown_internal_pricing_review",
        },
    }
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE customer_revision_requests
            SET trade_code='BOE_REVIEW', summary='raw PM_JANE pricing/reprice internal summary', payload=?
            WHERE id=?
            """,
            (_dumps(unsafe_payload), request_id),
        )
        conn.commit()

    resp = client.get(f"/api/v1/projects/{pid}/customer-revisions/customer-history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["history_type"] == "customer_safe_revision_history_v1"
    assert body["read_only"] is True
    item = body["items"][0]
    assert item["trade"] == "general"
    assert item["summary"] == "Requested added scope."
    assert item["sheet_refs"] == ["E-101", "A 2.01"]
    assert item["follow_up"] == "In review"

    rendered = json.dumps(body)
    forbidden = [
        "raw PM_JANE",
        "PM_JANE",
        "BOE_REVIEW",
        "Moses Internal",
        "internal note",
        "pricing/reprice",
        "raw_text",
        "reviewer",
        "notes",
        "before_snapshot",
        "after_snapshot",
        "readiness_snapshot",
        "customer_delivery_ready",
        "external_message_sent",
        "estimate_approved",
        "estimate_delivered",
        "billing_action_taken",
    ]
    for needle in forbidden:
        assert needle not in rendered


def test_customer_safe_revision_history_reports_version_counts_without_snapshots(client):
    pid = _upload_process_and_verify(client)
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please add plumbing fixture rough-ins shown on P-201.",
    }).json()
    request_id = created["items"][0]["id"]
    accepted = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "accepted",
        "reviewer": "moses",
        "notes": "Accepted internally for scope update.",
    })
    assert accepted.status_code == 200
    resolved = client.post(
        f"/api/v1/projects/{pid}/customer-revisions/{request_id}/resolve-rescope",
        json={"actor": "moses", "notes": "Resolved internal scope blocker."},
    )
    assert resolved.status_code == 200

    history = client.get(f"/api/v1/projects/{pid}/customer-revisions/customer-history").json()
    assert history["total"] == 1
    item = history["items"][0]
    assert item["status"] == "Scope update recorded"
    assert item["trade"] == "plumbing"
    assert item["summary"] == "Requested added scope for plumbing."
    assert item["follow_up"] == "Scope update in progress"
    assert item["version_count"] == 1
    assert item["latest_version_at"]
    rendered = json.dumps(history)
    assert "before_snapshot" not in rendered
    assert "after_snapshot" not in rendered
    assert "readiness_snapshot" not in rendered
    assert "customer_delivery_ready" not in rendered
    assert "external_message_sent" not in rendered
    assert "estimate_approved" not in rendered
    assert "estimate_delivered" not in rendered
    assert "billing_action_taken" not in rendered
    assert "Resolved internal scope blocker" not in rendered


def test_customer_safe_revision_submit_returns_sanitized_created_items_only(client):
    pid = _upload_process_and_verify(client)
    resp = client.post(f"/api/v1/projects/{pid}/customer-revisions/customer-submit", json={
        "text": "Please add electrical outlets on E-101. Internal PM_JANE pricing/reprice note should not echo.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["submission_type"] == "customer_safe_revision_submission_v1"
    assert body["created_count"] == 1
    assert body["customer_submission_recorded"] is True
    item = body["items"][0]
    assert item["action"] == "Include"
    assert item["status"] == "Received"
    assert item["trade"] == "electrical"
    assert item["summary"] == "Requested added scope for electrical."
    assert item["sheet_refs"] == ["E-101"]

    rendered = json.dumps(body)
    assert "PM_JANE" not in rendered
    assert "pricing/reprice" not in rendered
    assert "raw_text" not in rendered
    assert "actor" not in rendered
    assert "reviewer" not in rendered
    assert "notes" not in rendered
    assert "customer_delivery_ready" not in rendered
    assert "external_message_sent" not in rendered
    assert "estimate_approved" not in rendered
    assert "estimate_delivered" not in rendered
    assert "billing_action_taken" not in rendered

    history = client.get(f"/api/v1/projects/{pid}/customer-revisions/customer-history").json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == item["id"]
    assert history["items"][0]["summary"] == item["summary"]


def test_customer_safe_revision_submit_validation_and_unknown_project(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(
        f"/api/v1/projects/{missing}/customer-revisions/customer-submit",
        json={"text": "Please revise scope."},
    ).status_code == 404
    pid = _upload_process_and_verify(client)
    assert client.post(
        f"/api/v1/projects/{pid}/customer-revisions/customer-submit",
        json={"text": ""},
    ).status_code == 422
    assert client.post(
        f"/api/v1/projects/{pid}/customer-revisions/customer-submit",
        json={"text": "Please revise scope.", "actor": "staff"},
    ).status_code == 422
    assert client.post(
        f"/api/v1/projects/{pid}/customer-revisions/customer-submit",
        json={"text": "x" * 5001},
    ).status_code == 422
