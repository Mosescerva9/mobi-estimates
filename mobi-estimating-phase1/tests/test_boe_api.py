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
    assert any("Quantity" in assumption for assumption in body["assumptions"])
    assert "Pricing, quantities" in body["delivery_blockers"][1]


def test_boe_draft_unknown_project_404(client):
    resp = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/boe/draft")
    assert resp.status_code == 404
