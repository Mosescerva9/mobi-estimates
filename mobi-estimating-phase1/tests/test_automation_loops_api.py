"""Automation Loop Runner v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_estimate_build_loop_runs_until_artifacts_stabilize(client):
    pid = _upload_process_and_verify(client)

    resp = client.post(f"/api/v1/projects/{pid}/automation-loops/estimate-build/run", json={"max_passes": 3})
    assert resp.status_code == 200
    body = resp.json()
    run = body["run"]
    observation = body["latest_observation"]

    assert run["loop_name"] == "estimate_build_loop_v1"
    assert run["status"] in {"completed_with_blockers", "completed_ready_for_internal_review"}
    assert 1 <= run["pass_count"] <= 3
    assert run["trigger"]["type"] == "project_estimate_build_requested"
    assert run["stop_condition"]["hard_pass_cap"] == 3
    assert observation["coverage_count"] > 0
    assert observation["boe_status"] == "draft"
    assert observation["boe_delivery_ready"] is False
    assert observation["open_quantity_requirement_count"] > 0
    assert observation["critical_qa_finding_count"] > 0
    assert observation["stop_reason"] in {"artifact_stabilized", "max_passes_reached"}

    action_names = {action["name"] for pass_result in body["passes"] for action in pass_result["actions"]}
    assert {
        "coverage_census",
        "generic_scope",
        "generic_pricing_methods",
        "quantity_requirements",
        "qa_findings",
        "boe_draft",
    } <= action_names

    listed = client.get(f"/api/v1/projects/{pid}/automation-loops").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == run["id"]


def test_estimate_build_loop_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/automation-loops").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/automation-loops/estimate-build/run", json={}).status_code == 404
