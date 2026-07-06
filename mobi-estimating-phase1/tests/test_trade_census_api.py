"""Automatic Trade Census Draft Generation v1 tests."""

from __future__ import annotations

from tests.conftest import make_sheet_pdf


def _upload_process_and_verify(client) -> str:
    pdf = make_sheet_pdf(
        [
            {
                "number": "E-101",
                "title": "ELECTRICAL POWER PLAN",
                "body": "PANEL SCHEDULE\nLIGHTING FIXTURE SCHEDULE\nPOWER PLAN",
            },
            {
                "number": "P-101",
                "title": "PLUMBING PLAN",
                "body": "PLUMBING FIXTURE SCHEDULE\nDOMESTIC WATER\nSANITARY RISER",
            },
            {
                "number": "M-101",
                "title": "MECHANICAL HVAC PLAN",
                "body": "HVAC DUCTWORK\nAIR HANDLING UNIT\nDIFFUSER SCHEDULE",
            },
            {
                "number": "A-601",
                "title": "DOOR AND FINISH SCHEDULES",
                "body": "DIVISION 08 DOOR SCHEDULE\nDIVISION 09 FINISH SCHEDULE\nPAINT PT-1",
            },
        ]
    )
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Trade Census"},
        files={"plan": ("plans.pdf", pdf, "application/pdf")},
    ).json()["project_id"]
    process = client.post(f"/api/v1/projects/{pid}/process")
    assert process.status_code == 202

    expected = {
        1: ("E-101", "ELECTRICAL POWER PLAN"),
        2: ("P-101", "PLUMBING PLAN"),
        3: ("M-101", "MECHANICAL HVAC PLAN"),
        4: ("A-601", "DOOR AND FINISH SCHEDULES"),
    }
    for sheet in client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]:
        number, title = expected[sheet["pdf_page_number"]]
        verified = client.patch(
            f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
            json={
                "verified_sheet_number": number,
                "verified_sheet_title": title,
                "review_status": "verified",
            },
        )
        assert verified.status_code == 200
    return pid


def test_draft_trade_census_seeds_coverage_rows_from_processed_sheets(client):
    pid = _upload_process_and_verify(client)

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft")
    assert drafted.status_code == 200
    body = drafted.json()
    assert body["sheet_count"] == 4
    assert body["processed_sheet_count"] == 4
    codes = {row["trade_code"] for row in body["rows"]}
    assert {"electrical", "plumbing", "hvac", "architectural_general", "doors_hardware", "finishes"} <= codes

    electrical = next(row for row in body["rows"] if row["trade_code"] == "electrical")
    assert electrical["csi_divisions"] == ["26"]
    assert "sheet_prefix:E" in electrical["detected_from"]
    assert electrical["disposition"] == "undispositioned"
    assert electrical["status"] == "draft"
    assert electrical["evidence_refs"][0]["verified_sheet_number"] == "E-101"

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is False
    assert validation["critical_count"] == body["detected_trade_count"]
    assert {finding["code"] for finding in validation["findings"]} == {"undispositioned_trade"}


def test_draft_trade_census_is_idempotent_and_preserves_disposition(client):
    pid = _upload_process_and_verify(client)
    first = client.post(f"/api/v1/projects/{pid}/coverage/draft").json()
    first_total = client.get(f"/api/v1/projects/{pid}/coverage").json()["total"]

    electrical = next(row for row in first["rows"] if row["trade_code"] == "electrical")
    patched = client.patch(
        f"/api/v1/projects/{pid}/coverage/{electrical['id']}",
        json={
            "disposition": "customer_confirmation_needed",
            "status": "needs_customer",
            "basis_note": "Customer must confirm whether low-voltage is included with electrical base scope.",
        },
    )
    assert patched.status_code == 200

    second = client.post(f"/api/v1/projects/{pid}/coverage/draft").json()
    second_total = client.get(f"/api/v1/projects/{pid}/coverage").json()["total"]
    assert second_total == first_total

    updated_electrical = next(row for row in second["rows"] if row["trade_code"] == "electrical")
    assert updated_electrical["id"] == electrical["id"]
    assert updated_electrical["disposition"] == "customer_confirmation_needed"
    assert updated_electrical["status"] == "needs_customer"
    assert "sheet_prefix:E" in updated_electrical["detected_from"]


def test_draft_trade_census_unknown_project_404(client):
    resp = client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/coverage/draft")
    assert resp.status_code == 404
