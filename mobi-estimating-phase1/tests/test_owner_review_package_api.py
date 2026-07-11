"""Internal owner-review package v1 tests."""

from __future__ import annotations

from tests.test_estimate_readiness_api import _prepare_project, _resolve_quantities_and_pricing


def test_owner_review_package_blocked_until_requirements_resolved(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/owner-review/package")
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_type"] == "internal_owner_review_v1"
    assert body["status"] == "blocked"
    assert body["ready_for_owner_review"] is False
    assert body["customer_delivery_ready"] is False
    assert body["blockers"]
    assert body["review_packet"]["basis_of_estimate"]["delivery_ready"] is False
    register = body["review_packet"]["assumptions_register"]
    assert register["customer_delivery_ready"] is False
    assert register["summary"]["open_question_count"] > 0
    assert body["executive_summary"]["open_question_count"] == register["summary"]["open_question_count"]


def test_owner_review_package_abstains_after_test_quantity_and_pricing_inputs(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    resp = client.get(f"/api/v1/projects/{pid}/owner-review/package")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["ready_for_owner_review"] is False
    assert body["customer_delivery_ready"] is False
    codes = {row["code"] for row in body["blockers"]}
    assert "unsupported_customer_delivery_scope" in codes
    assert "test_only_delivery_sources" in codes
    assert body["executive_summary"]["open_quantity_requirement_count"] == 0
    assert body["executive_summary"]["missing_pricing_input_count"] == 0
    assert body["executive_summary"]["assumption_count"] >= 0
    assert body["executive_summary"]["exclusion_count"] >= 0
    assert body["executive_summary"]["open_question_count"] >= 0
    assert "approve_for_customer_delivery_prep" in body["review_decision_options"]
    assert body["review_packet"]["readiness"]["customer_delivery_ready"] is False
    assert body["review_packet"]["assumptions_register"]["customer_delivery_ready"] is False


def test_owner_review_package_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/owner-review/package").status_code == 404
