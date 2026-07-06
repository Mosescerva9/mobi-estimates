"""QA Findings Log v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_qa_findings_draft_from_coverage_validator(client):
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")

    drafted = client.post(f"/api/v1/projects/{pid}/qa/findings/draft")
    assert drafted.status_code == 200
    body = drafted.json()
    assert body["finding_count"] > 0
    assert {item["code"] for item in body["items"]} == {"undispositioned_trade"}
    assert body["critical_count"] == body["finding_count"]

    listed = client.get(f"/api/v1/projects/{pid}/qa/findings").json()
    assert listed["total"] == body["finding_count"]


def test_qa_findings_draft_from_generic_scope_blockers_is_idempotent(client):
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")

    first = client.post(f"/api/v1/projects/{pid}/qa/findings/draft").json()
    second = client.post(f"/api/v1/projects/{pid}/qa/findings/draft").json()

    assert first["finding_count"] == second["finding_count"]
    codes = {item["code"] for item in second["items"]}
    assert {"missing_quantity", "missing_pricing_basis"} <= codes
    assert all(item["source"] == "automated_qa_v1" for item in second["items"])


def test_qa_findings_unknown_project_404(client):
    assert client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/qa/findings").status_code == 404
    assert client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/qa/findings/draft").status_code == 404
