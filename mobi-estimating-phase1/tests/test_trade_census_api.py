"""Automatic Trade Census Draft Generation v1 tests."""

from __future__ import annotations

from tests.conftest import TEST_TENANT_HEADERS, make_sheet_pdf


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
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    process = client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS)
    assert process.status_code == 202

    expected = {
        1: ("E-101", "ELECTRICAL POWER PLAN"),
        2: ("P-101", "PLUMBING PLAN"),
        3: ("M-101", "MECHANICAL HVAC PLAN"),
        4: ("A-601", "DOOR AND FINISH SCHEDULES"),
    }
    for sheet in client.get(f"/api/v1/projects/{pid}/sheets", headers=TEST_TENANT_HEADERS).json()["items"]:
        number, title = expected[sheet["pdf_page_number"]]
        verified = client.patch(
            f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
            json={
                "verified_sheet_number": number,
                "verified_sheet_title": title,
                "review_status": "verified",
            },
            headers=TEST_TENANT_HEADERS,
        )
        assert verified.status_code == 200
    return pid


def test_draft_trade_census_seeds_coverage_rows_from_processed_sheets(client):
    pid = _upload_process_and_verify(client)

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
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
    assert electrical["evidence_refs"][0]["text_quote"] == "PANEL SCHEDULE"
    assert "sheet_text_keyword:panel schedule" in electrical["detected_from"]

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate", headers=TEST_TENANT_HEADERS).json()
    assert validation["complete"] is False
    assert validation["critical_count"] == body["detected_trade_count"]
    assert {finding["code"] for finding in validation["findings"]} == {"undispositioned_trade"}


def test_draft_trade_census_is_idempotent_and_preserves_disposition(client):
    pid = _upload_process_and_verify(client)
    first = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS).json()
    first_total = client.get(f"/api/v1/projects/{pid}/coverage", headers=TEST_TENANT_HEADERS).json()["total"]

    electrical = next(row for row in first["rows"] if row["trade_code"] == "electrical")
    patched = client.patch(
        f"/api/v1/projects/{pid}/coverage/{electrical['id']}",
        json={
            "disposition": "customer_confirmation_needed",
            "status": "needs_customer",
            "basis_note": "Customer must confirm whether low-voltage is included with electrical base scope.",
        },
        headers=TEST_TENANT_HEADERS,
    )
    assert patched.status_code == 200

    second = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS).json()
    second_total = client.get(f"/api/v1/projects/{pid}/coverage", headers=TEST_TENANT_HEADERS).json()["total"]
    assert second_total == first_total

    updated_electrical = next(row for row in second["rows"] if row["trade_code"] == "electrical")
    assert updated_electrical["id"] == electrical["id"]
    assert updated_electrical["disposition"] == "customer_confirmation_needed"
    assert updated_electrical["status"] == "needs_customer"
    assert "sheet_prefix:E" in updated_electrical["detected_from"]


def test_draft_trade_census_project_name_fallback_for_sparse_evcs_plans(client):
    pdf = make_sheet_pdf([
        {"number": "", "title": "", "body": "DSA DEPARTMENT OF GENERAL SERVICES Issue Date"},
    ])
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Lot 50 Accessibility Upgrades & EVCS - Plans"},
        files={"plan": ("sparse-evcs.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    body = drafted.json()
    by_code = {row["trade_code"]: row for row in body["rows"]}

    assert {"civil_sitework", "concrete", "electrical"} <= set(by_code)
    assert "project_name:site_accessibility_scope" in by_code["civil_sitework"]["detected_from"]
    assert "project_name:accessibility_flatwork_scope" in by_code["concrete"]["detected_from"]
    assert "project_name:ev_charging_scope" in by_code["electrical"]["detected_from"]
    assert "hvac" not in by_code
    assert "plumbing" not in by_code
    assert by_code["electrical"]["evidence_refs"][0]["sheet_id"] is None


def test_draft_trade_census_project_name_fallback_for_roof_replacement(client):
    pdf = make_sheet_pdf([
        {"number": "", "title": "", "body": "ISSUE DATE: SEPTEMBER 3, 2025"},
    ])
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "DSH Administration and Annex Building Roof Replacement Patton - Plans"},
        files={"plan": ("sparse-roof.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    by_code = {row["trade_code"]: row for row in drafted.json()["rows"]}

    assert {"architectural_general", "roofing_waterproofing", "structural"} <= set(by_code)
    assert "project_name:building_roof_project" in by_code["architectural_general"]["detected_from"]
    assert "project_name:roof_scope" in by_code["roofing_waterproofing"]["detected_from"]
    assert "project_name:structural_review_scope" in by_code["structural"]["detected_from"]
    assert "electrical" not in by_code
    assert "plumbing" not in by_code


def test_draft_trade_census_sheet_index_fallback_uses_real_cover_sheet_text(client):
    pdf = make_sheet_pdf(
        [
            {
                "number": "G-001",
                "title": "COVER SHEET AND SHEET INDEX",
                "body": "LIST OF DRAWINGS\nC-101 CIVIL SITE PLAN\nS-101 STRUCTURAL NOTES\nE-101 ELECTRICAL SITE PLAN",
            },
            {"number": "", "title": "", "body": "Sparse scanned plan graphics only"},
        ]
    )
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Generic Campus Improvements"},
        files={"plan": ("sheet-index.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    by_code = {row["trade_code"]: row for row in drafted.json()["rows"]}

    assert {"civil_sitework", "structural", "electrical"} <= set(by_code)
    assert "sheet_index_prefix:C" in by_code["civil_sitework"]["detected_from"]
    assert "sheet_index_prefix:S" in by_code["structural"]["detected_from"]
    assert "sheet_index_prefix:E" in by_code["electrical"]["detected_from"]
    assert by_code["electrical"]["evidence_refs"][0]["sheet_id"] is not None
    assert by_code["electrical"]["evidence_refs"][0]["text_quote"] == "E-101 ELECTRICAL SITE PLAN"
    assert by_code["electrical"]["confidence"] < 0.9
    assert "plumbing" not in by_code
    assert "hvac" not in by_code


def test_draft_trade_census_cover_sheet_without_index_does_not_invent_mep(client):
    pdf = make_sheet_pdf(
        [
            {
                "number": "",
                "title": "COVER SHEET",
                "body": "SHEET INDEX\nELECTRICAL NOTES\nMECHANICAL SCHEDULE\nPLUMBING PLAN\nPROJECT CONTACTS",
            },
        ]
    )
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Generic Campus Improvements"},
        files={"plan": ("cover-only.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    codes = {row["trade_code"] for row in drafted.json()["rows"]}

    assert "electrical" not in codes
    assert "plumbing" not in codes
    assert "hvac" not in codes


def test_sheet_prefix_rejects_project_number_as_hvac_sheet():
    from app.trade_census import _sheet_prefix

    assert _sheet_prefix("H27-Z147-B") == ""
    assert _sheet_prefix("H-101") == "H"


def test_project_number_in_sheet_index_text_does_not_seed_hvac(client):
    pdf = make_sheet_pdf([
        {
            "number": "G-001",
            "title": "COVER SHEET AND SHEET INDEX",
            "body": "SHEET INDEX\nUSC PROJECT # H27-Z147-B\nA101 FLOOR PLAN\nC200 CIVIL PLAN",
        }
    ])
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Longstreet Theatre Exterior Restoration"},
        files={"plan": ("project-number-cover.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202
    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    codes = {row["trade_code"] for row in drafted.json()["rows"]}
    assert "hvac" not in codes


def test_draft_trade_census_reads_drawing_content_notes_schedules_and_callouts(client):
    pdf = make_sheet_pdf(
        [
            {
                "number": "",
                "title": "",
                "body": "CONSTRUCTION NOTES\nACCESSIBLE PARKING STALL STRIPING TO REMAIN\nNEW CONCRETE CURB RAMP WITH TRUNCATED DOMES",
            },
            {
                "number": "",
                "title": "",
                "body": "POWER SCHEDULE\nPROVIDE EV CHARGER AND CONDUIT TO PANELBOARD P1",
            },
            {
                "number": "",
                "title": "",
                "body": "ROOF DETAIL CALLOUTS\nINSTALL ROOF MEMBRANE, FLASHING, AND ROOF DRAIN PROTECTION",
            },
        ]
    )
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Generic Campus Work"},
        files={"plan": ("content-signals.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    by_code = {row["trade_code"]: row for row in drafted.json()["rows"]}

    assert {"civil_sitework", "concrete", "electrical", "roofing_waterproofing"} <= set(by_code)
    assert "sheet_text_keyword:accessible parking" in by_code["civil_sitework"]["detected_from"]
    assert "sheet_text_keyword:concrete curb" in by_code["concrete"]["detected_from"]
    assert "sheet_text_keyword:panelboard" in by_code["electrical"]["detected_from"]
    assert "sheet_text_keyword:roof membrane" in by_code["roofing_waterproofing"]["detected_from"]
    assert by_code["electrical"]["evidence_refs"][0]["text_quote"] == "PROVIDE EV CHARGER AND CONDUIT TO PANELBOARD P1"
    assert by_code["roofing_waterproofing"]["evidence_refs"][0]["sheet_id"] is not None


def test_draft_trade_census_ambiguous_flashing_signal_does_not_create_roofing(client):
    pdf = make_sheet_pdf(
        [
            {
                "number": "",
                "title": "",
                "body": "TRAFFIC NOTES\nPROVIDE FLASHING BEACON AND WARNING LIGHT AT CROSSWALK",
            },
        ]
    )
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Generic Campus Work"},
        files={"plan": ("flashing-beacon.pdf", pdf, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS).status_code == 202

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/draft", headers=TEST_TENANT_HEADERS)
    assert drafted.status_code == 200
    codes = {row["trade_code"] for row in drafted.json()["rows"]}

    assert "roofing_waterproofing" not in codes


def test_draft_trade_census_unknown_project_404(client):
    resp = client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/coverage/draft")
    assert resp.status_code == 404
