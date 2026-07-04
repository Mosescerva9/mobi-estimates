"""Human-review workflow tests."""

from __future__ import annotations

from tests.conftest import prepare_verified_project


def _extract_items(client, pid, trade="painting"):
    client.post(f"/api/v1/projects/{pid}/trades/{trade}/extractions", json={})
    return client.get(f"/api/v1/projects/{pid}/scope-items?trade_code={trade}").json()["items"]


def _walls(items):
    return [i for i in items if i["category_code"] == "interior_walls"][0]


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
