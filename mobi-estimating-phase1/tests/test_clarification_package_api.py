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


def test_clarification_package_prioritizes_and_groups_candidates(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/clarifications/package")
    assert resp.status_code == 200
    body = resp.json()

    candidates = body["candidates"]
    assert candidates
    scores = [candidate["priority_score"] for candidate in candidates]
    ranks = [candidate["priority_rank"] for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    assert ranks == list(range(1, len(candidates) + 1))
    assert all(candidate["priority_bucket"] in {"urgent", "high", "medium", "low"} for candidate in candidates)

    summary = body["summary"]
    assert summary["highest_priority_score"] == scores[0]
    assert summary["highest_priority_bucket"] == candidates[0]["priority_bucket"]
    assert summary["top_candidate_ids"][0] == candidates[0]["id"]
    assert (
        summary["urgent_candidate_count"]
        + summary["high_candidate_count"]
        + summary["medium_candidate_count"]
        + summary["low_candidate_count"]
    ) == summary["candidate_count"]

    groups = body["groups"]
    for group_name in ("by_priority_bucket", "by_severity", "by_trade", "by_source_code", "by_source"):
        assert group_name in groups
        assert groups[group_name]
        assert sum(group["count"] for group in groups[group_name]) == summary["candidate_count"]
        assert all("highest_priority_score" in group for group in groups[group_name])

    assert body["customer_delivery_ready"] is False
    assert body["customer_message_ready"] is False
    assert body["send_ready"] is False


def test_owner_review_embedded_clarifications_match_direct_package(client):
    pid = _prepare_project(client)

    direct = client.get(f"/api/v1/projects/{pid}/clarifications/package")
    owner_review = client.get(f"/api/v1/projects/{pid}/owner-review/package")

    assert direct.status_code == 200
    assert owner_review.status_code == 200
    direct_body = direct.json()
    owner_body = owner_review.json()
    embedded = owner_body["review_packet"]["clarification_package"]

    direct_body_without_time = {k: v for k, v in direct_body.items() if k != "generated_at"}
    embedded_without_time = {k: v for k, v in embedded.items() if k != "generated_at"}
    assert embedded_without_time == direct_body_without_time
    assert owner_body["customer_delivery_ready"] is False
    assert owner_body["review_packet"]["readiness"]["customer_delivery_ready"] is False
    assert embedded["customer_delivery_ready"] is False
    assert embedded["customer_message_ready"] is False
    assert embedded["send_ready"] is False
    assert embedded["send_gate"]

    serialized = str(embedded).lower()
    assert "send_ready': true" not in serialized
    assert "customer_message_ready': true" not in serialized
    assert "customer_delivery_ready': true" not in serialized


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
