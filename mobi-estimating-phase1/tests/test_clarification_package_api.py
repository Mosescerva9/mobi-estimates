"""Internal clarification package v1 tests."""

from __future__ import annotations

from tests.test_estimate_readiness_api import _prepare_project, _resolve_quantities_and_pricing

_FORBIDDEN_TERMS = (
    "reprice",
    "pricing",
    "bill",
    "invoice",
    "payment",
    "deliver",
    "delivery",
    "approve",
    "approval",
    "readiness",
    "blocker",
    "blocks_delivery",
    "provenance",
    "qa_finding",
    "coverage_row",
    "before",
    "after",
    "snapshot",
)


def _assert_customer_safe(text: str) -> None:
    lowered = text.lower()
    for term in _FORBIDDEN_TERMS:
        assert term not in lowered, f"forbidden term {term!r} in {text!r}"


def test_owner_review_package_includes_clarification_package_when_blocked(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/owner-review/package")
    assert resp.status_code == 200
    body = resp.json()

    pkg = body["review_packet"]["clarification_package"]
    assert pkg["package_type"] == "internal_clarification_package_v1"
    assert pkg["customer_delivery_ready"] is False
    assert pkg["customer_message_ready"] is False
    assert pkg["send_ready"] is False
    assert pkg["summary"]["candidate_count"] > 0
    assert pkg["summary"]["blocking_candidate_count"] > 0
    assert pkg["summary"]["customer_safe_candidate_count"] > 0

    for candidate in pkg["candidates"]:
        assert candidate["human_approval_required"] is True
        assert candidate["customer_safe_question"]
        _assert_customer_safe(candidate["customer_safe_question"])

    es = body["executive_summary"]
    assert es["clarification_candidate_count"] == pkg["summary"]["candidate_count"]
    assert es["blocking_clarification_candidate_count"] == pkg["summary"]["blocking_candidate_count"]
    assert es["critical_clarification_candidate_count"] == pkg["summary"]["critical_candidate_count"]


def test_clarification_package_endpoint_blocked_project(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/clarifications/package")
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_type"] == "internal_clarification_package_v1"
    assert body["customer_delivery_ready"] is False
    assert body["customer_message_ready"] is False
    assert body["send_ready"] is False
    assert body["summary"]["blocking_candidate_count"] > 0


def test_clarification_package_ready_project_has_no_blocking_candidates(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    resp = client.get(f"/api/v1/projects/{pid}/clarifications/package")
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_delivery_ready"] is False
    assert body["customer_message_ready"] is False
    assert body["send_ready"] is False
    assert body["summary"]["blocking_candidate_count"] == 0


def test_clarification_package_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/clarifications/package").status_code == 404
