"""Human-review workflow tests."""

from __future__ import annotations

import json
from uuid import uuid4

from app.database import get_connection
from tests.conftest import prepare_verified_project
from tests.test_trade_census_api import _upload_process_and_verify


def _extract_items(client, pid, trade="painting"):
    client.post(f"/api/v1/projects/{pid}/trades/{trade}/extractions", json={})
    return client.get(f"/api/v1/projects/{pid}/scope-items?trade_code={trade}").json()["items"]


def _walls(items):
    return [i for i in items if i["category_code"] == "interior_walls"][0]


def _insert_customer_revision_style_scope_item(pid: str, *, quantity_basis: str) -> str:
    """Insert a scope_items row directly to simulate a pre-existing (legacy or
    corrupt) accepted-customer-revision blocker, bypassing the normal
    customer-revision decision flow.
    """
    item_id = str(uuid4())
    run_id = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'general_trade', 'completed', 'test', 1, 't', 't', "
            "'test_tenant', 'test_company')",
            (run_id, pid),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "review_status, conflict_status, blocking_issues, quantity_basis, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'general_trade', 'test', 'test', 'customer_revision_rescope', "
            "'Accepted customer revision requires rescope.', 'blocked', 'blocking', ?, ?, "
            "'t', 't', 'test_tenant', 'test_company')",
            (
                item_id, pid, run_id,
                json.dumps([{"code": "customer_revision_rescope_required"}]),
                quantity_basis,
            ),
        )
        conn.commit()
    return item_id


def test_ai_candidate_starts_pending(client):
    pid = prepare_verified_project(client)
    items = _extract_items(client, pid)
    assert all(i["review_status"] in ("pending", "blocked") for i in items)
    assert not any(i["review_status"] == "approved" for i in items)


def test_approval_requires_trusted_evidence(client):
    pid = prepare_verified_project(client)
    items = _extract_items(client, pid)
    walls = _walls(items)
    # Strip the evidence to simulate a candidate without trusted evidence.
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM evidence_references WHERE scope_item_id=?", (walls["id"],))
        conn.commit()
    resp = client.post(f"/api/v1/projects/{pid}/scope-items/{walls['id']}/approve").json()
    assert resp["approved"] is False
    assert any(b["code"] == "missing_verified_sheet" for b in resp["blocking_issues"])


def test_approval_requires_quantity_when_required(client):
    pid = prepare_verified_project(client)
    items = _extract_items(client, pid)
    walls = _walls(items)
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE scope_items SET quantity=NULL WHERE id=?", (walls["id"],))
        conn.commit()
    resp = client.post(f"/api/v1/projects/{pid}/scope-items/{walls['id']}/approve").json()
    assert resp["approved"] is False
    assert any(b["code"] == "missing_quantity" for b in resp["blocking_issues"])


def test_successful_approval(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    resp = client.post(f"/api/v1/projects/{pid}/scope-items/{walls['id']}/approve").json()
    assert resp["approved"] is True
    assert resp["review_status"] == "approved"


def test_correction_preserves_original_candidate(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    before = client.get(f"/api/v1/projects/{pid}/scope-items/{walls['id']}").json()
    original = before["original_provider_candidate"]
    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}",
        json={"description": "Corrected description", "reviewer_id": "alice"},
    ).json()
    assert resp["scope_item"]["description"] == "Corrected description"
    # Original provider candidate is untouched.
    assert resp["original_provider_candidate"] == original
    assert resp["scope_item"]["review_status"] == "corrected"


def test_manual_quantity_is_marked(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}",
        json={"quantity": "250", "unit": "SF"},
    ).json()
    assert resp["scope_item"]["quantity_basis"] == "manual_reviewer_entry"
    assert resp["scope_item"]["quantity"] == "250"


def test_recalculation_uses_registered_formula(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    resp = client.post(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}/recalculate",
        json={"formula_id": "painting.wall_gross_area",
              "inputs": {"length_ft": "30", "height_ft": "10"}},
    ).json()
    assert resp["scope_item"]["quantity"] == "300.0000"
    assert resp["scope_item"]["quantity_basis"] == "deterministic_derivation"


def test_recalculation_rejects_unregistered_formula_for_trade(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    resp = client.post(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}/recalculate",
        json={"formula_id": "demo_concrete.slab_volume",
              "inputs": {"length_ft": "1", "width_ft": "1", "thickness_in": "1"}},
    )
    assert resp.status_code == 400


def test_recalculation_rejects_arbitrary_formula(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    resp = client.post(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}/recalculate",
        json={"formula_id": "evil.exec", "inputs": {}},
    )
    assert resp.status_code == 400


def test_rejection_requires_reason(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    missing = client.post(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}/reject", json={}
    )
    assert missing.status_code == 422  # reason field required
    ok = client.post(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}/reject",
        json={"reason": "Not in scope"},
    )
    assert ok.status_code == 200
    assert ok.json()["scope_item"]["review_status"] == "rejected"


def test_review_history_is_append_only(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    client.patch(f"/api/v1/projects/{pid}/scope-items/{walls['id']}",
                 json={"description": "x"})
    client.post(f"/api/v1/projects/{pid}/scope-items/{walls['id']}/approve")
    history = client.get(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}"
    ).json()["review_history"]
    actions = [h["action"] for h in history]
    assert "correct" in actions and "approve" in actions
    assert len(history) >= 2


def test_trade_validation_reruns_after_correction(client):
    pid = prepare_verified_project(client)
    walls = _walls(_extract_items(client, pid))
    # Submit an invalid painting trade_data on correction → 422 from trade module.
    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{walls['id']}",
        json={"trade_data": {"thickness_in": 6}},  # not a painting field
    )
    assert resp.status_code == 422


def test_scope_item_ownership_enforced(client):
    pid_a = prepare_verified_project(client, project_name="A")
    pid_b = prepare_verified_project(client, project_name="B")
    walls_b = _walls(_extract_items(client, pid_b))
    resp = client.get(f"/api/v1/projects/{pid_a}/scope-items/{walls_b['id']}")
    assert resp.status_code == 404


def test_correcting_accepted_customer_revision_blocker_keeps_delivery_locked(client):
    """Staff correcting the auto-generated rescope blocker must not crash and
    must not clear the customer_revision_rescope_required blocker or unlock
    delivery -- only a dedicated rescope-resolution step may do that.
    """
    pid = _upload_process_and_verify(client)
    # Text with no trade keyword match -> trade_code falls back to "general_trade",
    # the only trade module every deployment registers (customer revisions can
    # otherwise parse a trade_code, e.g. "plumbing", that isn't a real registered
    # trade module in this build -- a separate, pre-existing gap this test avoids).
    created = client.post(f"/api/v1/projects/{pid}/customer-revisions/parse", json={
        "text": "Please revise the miscellaneous scope budget note for the owner.",
    }).json()
    request_id = created["items"][0]["id"]
    decided = client.post(f"/api/v1/projects/{pid}/customer-revisions/{request_id}/decide", json={
        "decision": "accepted",
    }).json()
    blocker_id = decided["rescope_blocker"]["id"]
    assert decided["rescope_blocker"]["quantity_basis"] == "unknown"

    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{blocker_id}",
        json={"reviewer_notes": "Staff reviewed blocker context.", "reviewer_id": "staff_alice"},
    )
    assert resp.status_code == 200
    body = resp.json()["scope_item"]
    assert body["quantity_basis"] == "unknown"
    codes = {issue["code"] for issue in body["blocking_issues"]}
    assert "customer_revision_rescope_required" in codes

    readiness = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    assert readiness["status"] == "blocked"
    assert any(b["code"] == "open_scope_blockers" for b in readiness["blockers"])


def test_legacy_customer_revision_quantity_basis_is_normalized_on_correction(client):
    """A row still carrying the pre-fix 'customer_revision_pending_rescope'
    sentinel must be correctable without a 500, and gets normalized to the
    valid QuantityBasis.UNKNOWN, not left corrupt.
    """
    pid = prepare_verified_project(client)
    item_id = _insert_customer_revision_style_scope_item(
        pid, quantity_basis="customer_revision_pending_rescope"
    )

    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{item_id}",
        json={"reviewer_notes": "Reviewed legacy blocker row.", "reviewer_id": "staff_bob"},
    )
    assert resp.status_code == 200
    body = resp.json()["scope_item"]
    assert body["quantity_basis"] == "unknown"
    codes = {issue["code"] for issue in body["blocking_issues"]}
    assert "customer_revision_rescope_required" in codes


def test_invalid_quantity_basis_fails_closed_on_correction(client):
    """An arbitrary/corrupt quantity_basis (not the known legacy sentinel) must
    not be silently coerced -- correction fails closed with a 422.
    """
    pid = prepare_verified_project(client)
    item_id = _insert_customer_revision_style_scope_item(
        pid, quantity_basis="totally_made_up_basis"
    )

    resp = client.patch(
        f"/api/v1/projects/{pid}/scope-items/{item_id}",
        json={"reviewer_notes": "Attempt to review corrupt row.", "reviewer_id": "staff_bob"},
    )
    assert resp.status_code == 422
    assert "totally_made_up_basis" in resp.json()["error"]["message"]
