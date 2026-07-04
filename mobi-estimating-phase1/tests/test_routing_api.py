"""Sheet-routing and eligibility-override tests."""

from __future__ import annotations

from tests.conftest import make_sheet_pdf, prepare_verified_project


def _route(client, pid, trade):
    return {
        s["pdf_page_number"]: s
        for s in client.get(
            f"/api/v1/projects/{pid}/trades/{trade}/eligible-sheets"
        ).json()["sheets"]
    }


def test_relevant_verified_sheet_is_eligible(client):
    pid = prepare_verified_project(client)
    routing = _route(client, pid, "painting")
    assert routing[1]["eligibility"] == "eligible"  # A-101 finish sheet


def test_unverified_sheet_is_blocked(client):
    # Upload + process but do NOT verify any sheet.
    pid = client.post(
        "/api/v1/projects/upload", data={"project_name": "U"},
        files={"plan": ("plans.pdf",
                        make_sheet_pdf([{"number": "A-101", "title": "FINISH",
                                         "body": "PAINTING FINISH SCHEDULE"}]),
                        "application/pdf")},
    ).json()["project_id"]
    client.post(f"/api/v1/projects/{pid}/process")
    routing = _route(client, pid, "painting")
    assert routing[1]["eligibility"] == "blocked_unverified"


def test_ocr_required_sheet_is_blocked(client):
    # Image-only page → requires_ocr. Verify it, then routing should block on OCR.
    pid = client.post(
        "/api/v1/projects/upload", data={"project_name": "O"},
        files={"plan": ("plans.pdf", make_sheet_pdf([{"image_only": True}]),
                        "application/pdf")},
    ).json()["project_id"]
    client.post(f"/api/v1/projects/{pid}/process")
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    client.patch(
        f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
        json={"verified_sheet_number": "A-101", "review_status": "verified"},
    )
    routing = _route(client, pid, "painting")
    assert routing[1]["eligibility"] == "blocked_ocr"


def test_irrelevant_sheet_excluded(client):
    pid = client.post(
        "/api/v1/projects/upload", data={"project_name": "E"},
        files={"plan": ("plans.pdf",
                        make_sheet_pdf([{"number": "E-101", "title": "POWER PLAN",
                                         "body": "ELECTRICAL PANEL SCHEDULE"}]),
                        "application/pdf")},
    ).json()["project_id"]
    client.post(f"/api/v1/projects/{pid}/process")
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    client.patch(
        f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
        json={"verified_sheet_number": "E-101", "review_status": "verified"},
    )
    assert _route(client, pid, "painting")[1]["eligibility"] == "excluded"


def test_different_trades_route_same_sheet_differently(client):
    pid = prepare_verified_project(client)
    painting = _route(client, pid, "painting")
    concrete = _route(client, pid, "demo_concrete")
    # A-101 finish sheet: eligible for painting, not eligible for concrete.
    assert painting[1]["eligibility"] == "eligible"
    assert concrete[1]["eligibility"] != "eligible"
    # S-101 concrete sheet: eligible for concrete.
    assert concrete[2]["eligibility"] == "eligible"


def test_manual_include_and_exclude(client):
    pid = prepare_verified_project(client)
    # S-101 is 'requires_review' for painting; manually include it.
    sheet = [s for s in client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
             if s["pdf_page_number"] == 2][0]
    resp = client.patch(
        f"/api/v1/projects/{pid}/trades/painting/sheets/{sheet['sheet_id']}/eligibility",
        json={"manual_override": "eligible", "reviewer_notes": "include it"},
    )
    assert resp.status_code == 200
    assert resp.json()["effective_status"] == "eligible"
    # Now exclude the A-101 sheet.
    a_sheet = [s for s in client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
               if s["pdf_page_number"] == 1][0]
    resp2 = client.patch(
        f"/api/v1/projects/{pid}/trades/painting/sheets/{a_sheet['sheet_id']}/eligibility",
        json={"manual_override": "excluded"},
    )
    assert resp2.json()["effective_status"] == "excluded"


def test_eligibility_sheet_ownership_enforced(client):
    pid_a = prepare_verified_project(client, project_name="A")
    pid_b = prepare_verified_project(client, project_name="B")
    sheet_b = client.get(f"/api/v1/projects/{pid_b}/sheets").json()["items"][0]
    resp = client.patch(
        f"/api/v1/projects/{pid_a}/trades/painting/sheets/{sheet_b['sheet_id']}/eligibility",
        json={"manual_override": "excluded"},
    )
    assert resp.status_code == 404


def test_invalid_manual_override_rejected(client):
    pid = prepare_verified_project(client)
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    resp = client.patch(
        f"/api/v1/projects/{pid}/trades/painting/sheets/{sheet['sheet_id']}/eligibility",
        json={"manual_override": "banana"},
    )
    assert resp.status_code == 422
