"""Extraction run lifecycle tests."""

from __future__ import annotations

from tests.conftest import make_trade_pdf, prepare_verified_project


def _extract(client, pid, trade="painting", **body):
    return client.post(f"/api/v1/projects/{pid}/trades/{trade}/extractions", json=body)


def test_new_extraction_run(client):
    pid = prepare_verified_project(client)
    resp = _extract(client, pid)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] in ("needs_review", "completed")
    assert body["candidate_count"] == 2


def test_duplicate_active_request_returns_same_run_or_conflict(client):
    pid = prepare_verified_project(client)
    first = _extract(client, pid).json()
    # Inline processing already completed the first run; a second non-forced
    # request must not silently start a new run.
    second = _extract(client, pid)
    assert second.status_code == 409  # already completed; force required


def test_forced_new_run_creates_distinct_run(client):
    pid = prepare_verified_project(client)
    first = _extract(client, pid).json()
    forced = _extract(client, pid, force=True).json()
    assert forced["run_id"] != first["run_id"]


def test_separate_trades_have_separate_runs(client):
    pid = prepare_verified_project(client)
    painting = _extract(client, pid, "painting").json()
    concrete = _extract(client, pid, "demo_concrete").json()
    assert painting["run_id"] != concrete["run_id"]
    assert painting["trade_code"] == "painting"
    assert concrete["trade_code"] == "demo_concrete"


def test_extraction_status_endpoint(client):
    pid = prepare_verified_project(client)
    run = _extract(client, pid).json()
    status = client.get(
        f"/api/v1/projects/{pid}/trades/painting/extractions/{run['run_id']}"
    ).json()
    assert status["run_id"] == run["run_id"]
    assert status["candidate_count"] == 2


def test_list_runs_pagination(client):
    pid = prepare_verified_project(client)
    _extract(client, pid)
    _extract(client, pid, force=True)
    listing = client.get(
        f"/api/v1/projects/{pid}/trades/painting/extractions?limit=1&offset=0"
    ).json()
    assert listing["total"] == 2
    assert len(listing["items"]) == 1


def test_dry_run_makes_no_candidates(client):
    pid = prepare_verified_project(client)
    resp = _extract(client, pid, dry_run=True).json()
    assert resp["dry_run"] is True
    items = client.get(f"/api/v1/projects/{pid}/scope-items?trade_code=painting").json()
    assert items["total"] == 0


def test_missing_processed_sheets_blocks_extraction(client):
    # Upload but never process → no sheets.
    pid = client.post(
        "/api/v1/projects/upload", data={"project_name": "NP"},
        files={"plan": ("plans.pdf", make_trade_pdf(), "application/pdf")},
    ).json()["project_id"]
    resp = _extract(client, pid)
    assert resp.status_code == 409


def test_unknown_trade_extraction_404(client):
    pid = prepare_verified_project(client)
    assert _extract(client, pid, "no_such_trade").status_code == 404


def test_approved_items_unchanged_after_reextraction(client):
    pid = prepare_verified_project(client)
    first = _extract(client, pid).json()
    items = client.get(
        f"/api/v1/projects/{pid}/scope-items?extraction_run_id={first['run_id']}"
    ).json()["items"]
    walls = [i for i in items if i["category_code"] == "interior_walls"][0]
    client.post(f"/api/v1/projects/{pid}/scope-items/{walls['id']}/approve")

    # Force a re-extraction → a new run with new candidates.
    second = _extract(client, pid, force=True).json()
    approved = client.get(f"/api/v1/projects/{pid}/scope-items/{walls['id']}").json()
    assert approved["scope_item"]["review_status"] == "approved"
    # New candidates are tied to the new run, not the old approved item.
    new_items = client.get(
        f"/api/v1/projects/{pid}/scope-items?extraction_run_id={second['run_id']}"
    ).json()["items"]
    assert all(i["id"] != walls["id"] for i in new_items)
    assert len(new_items) == 2  # comparison data available across runs


def test_run_state_survives_restart(client):
    pid = prepare_verified_project(client)
    run = _extract(client, pid).json()
    from tests.conftest import TEST_TENANT_HEADERS
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client2:
        status = client2.get(
            f"/api/v1/projects/{pid}/trades/painting/extractions/{run['run_id']}",
            headers=TEST_TENANT_HEADERS,
        )
    assert status.status_code == 200
    assert status.json()["candidate_count"] == 2
