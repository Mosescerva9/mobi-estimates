"""Basis of Estimate Draft Generator v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_boe_draft_summarizes_documents_coverage_scope_and_qa(client):
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    client.post(f"/api/v1/projects/{pid}/qa/findings/draft")

    resp = client.get(f"/api/v1/projects/{pid}/boe/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == pid
    assert body["status"] == "draft"
    assert body["delivery_ready"] is False
    assert body["document_basis"]["sheet_count"] == 4
    assert body["coverage_summary"]["trade_count"] > 0
    assert body["coverage_summary"]["complete"] is True
    assert body["scope_summary"]["scope_item_count"] == body["coverage_summary"]["trade_count"]
    assert body["scope_summary"]["blocked_scope_item_count"] > 0
    assert body["qa_summary"]["critical_count"] > 0
    assert body["assumptions_register"]["register_type"] == "assumptions_exclusions_open_questions_v1"
    assert body["assumptions_register"]["customer_delivery_ready"] is False
    assert body["assumptions_register"]["summary"]["assumption_count"] > 0
    assert body["assumptions_register"]["summary"]["open_question_count"] > 0
    assert any(
        row["code"] == "missing_quantity"
        for row in body["assumptions_register"]["open_questions"]
    )
    assert any("Quantity" in assumption for assumption in body["assumptions"])
    assert "Pricing, quantities" in body["delivery_blockers"][1]


def test_boe_draft_unknown_project_404(client):
    resp = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/boe/draft")
    assert resp.status_code == 404

def test_assumptions_register_returns_full_untruncated_detail(monkeypatch):
    from uuid import uuid4

    from app import assumptions_register

    pid = uuid4()
    items = [
        {
            "id": f"scope-{idx}",
            "project_id": str(pid),
            "trade_code": "general_trade",
            "assumptions": [{"text": f"Assumption {idx}"}],
            "exclusions": [{"text": f"Exclusion {idx}"}],
            "blocking_issues": [{"code": "missing_quantity", "message": f"Question {idx}"}],
        }
        for idx in range(125)
    ]

    monkeypatch.setattr(assumptions_register, "_list_all_scope_items", lambda project_id: (items, len(items)))
    monkeypatch.setattr(assumptions_register, "validate_coverage", lambda project_id: {"findings": []})
    monkeypatch.setattr(assumptions_register, "list_qa_findings", lambda project_id: [])
    monkeypatch.setattr(assumptions_register, "list_quantity_requirements", lambda project_id: [])
    monkeypatch.setattr(
        assumptions_register,
        "summarize_scope_provenance",
        lambda scope_items: {
            "missing_extraction_provenance": [],
            "low_extraction_confidence": [],
            "quantity_basis_unclear": [],
        },
    )

    body = assumptions_register.build_assumptions_register(pid)

    assert body["summary"]["assumption_count"] == 125
    assert len(body["assumptions"]) == 125
    assert body["summary"]["exclusion_count"] == 125
    assert len(body["exclusions"]) == 125
    assert body["summary"]["open_question_count"] == 125
    assert len(body["open_questions"]) == 125
    assert len(body["all_entries"]) == 375
    assert body["customer_delivery_ready"] is False


def test_boe_uses_all_scope_items_for_parallel_legacy_counts(monkeypatch):
    from uuid import uuid4

    from app import boe

    pid = uuid4()
    items = [
        {
            "id": f"scope-{idx}",
            "trade_code": "general_trade",
            "review_status": "blocked" if idx == 1000 else "pending",
            "assumptions": [{"text": f"Assumption {idx}"}],
            "exclusions": [],
            "blocking_issues": [{"message": "Late blocker"}] if idx == 1000 else [],
        }
        for idx in range(1001)
    ]
    calls = []

    def fake_list_scope_items(project_id, *, filters, limit, offset):
        calls.append({"limit": limit, "offset": offset})
        return items, len(items)

    monkeypatch.setattr(boe, "get_project", lambda project_id: {"name": "Big Project"})
    monkeypatch.setattr(boe, "list_sheets", lambda project_id, limit, offset: ([], 0))
    monkeypatch.setattr(boe, "list_coverage_rows", lambda project_id: [{"trade_code": "general_trade", "trade_name": "General"}])
    monkeypatch.setattr(boe, "list_scope_items", fake_list_scope_items)
    monkeypatch.setattr(boe, "list_qa_findings", lambda project_id: [])
    monkeypatch.setattr(boe, "validate_coverage", lambda project_id: {"complete": True, "critical_count": 0, "major_count": 0})
    monkeypatch.setattr(boe, "build_assumptions_register", lambda project_id: {"summary": {}, "customer_delivery_ready": False})

    body = boe.draft_boe(pid)

    assert calls[0]["limit"] == 10000
    assert body["scope_summary"]["scope_item_count"] == 1001
    assert body["scope_summary"]["blocked_scope_item_count"] == 1
    assert body["coverage_summary"]["trades"][0]["scope_item_count"] == 1001
    assert "Late blocker" in body["open_questions"]
