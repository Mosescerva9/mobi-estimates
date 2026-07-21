"""Generic-Lane Scope Candidate Creation v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def test_generic_scope_draft_creates_blocked_scope_items_from_coverage(client):
    pid = _upload_process_and_verify(client)
    census = client.post(f"/api/v1/projects/{pid}/coverage/draft").json()

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    assert drafted.status_code == 200
    body = drafted.json()
    assert body["created_count"] == census["detected_trade_count"]
    assert body["skipped_count"] == 0

    electrical_items = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=electrical"
    ).json()
    assert electrical_items["total"] == 1
    item = electrical_items["items"][0]
    assert item["category_code"] == "generic_scope"
    assert item["review_status"] == "blocked"
    assert item["quantity_basis"] == "unknown"

    electrical_created = next(row for row in body["created"] if row["trade_code"] == "electrical")
    assert electrical_created["trade_module_version"] == "0.1.0"
    assert electrical_created["trade_data"]["generic_lane"] == "general_trade"
    assert electrical_created["trade_data"]["source_trade_code"] == "electrical"
    assert electrical_created["blocking_issues"][0]["code"] == "missing_quantity"

    detail = client.get(f"/api/v1/projects/{pid}/scope-items/{electrical_created['id']}")
    assert detail.status_code == 200
    evidence = detail.json()["evidence"]
    assert evidence[0]["extracted_text_quote"] == "PANEL SCHEDULE"
    assert bool(evidence[0]["requires_human_verification"]) is True

    coverage = client.get(f"/api/v1/projects/{pid}/coverage").json()["items"]
    electrical_row = next(row for row in coverage if row["trade_code"] == "electrical")
    assert electrical_row["disposition"] == "included_generic"
    assert electrical_row["status"] == "ready"

    validation = client.get(f"/api/v1/projects/{pid}/coverage/validate").json()
    assert validation["complete"] is True
    assert validation["findings"] == []


def test_generic_scope_draft_preserves_unverified_sheet_index_evidence_quotes(client):
    from tests.conftest import make_sheet_pdf

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
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process").status_code == 202

    census = client.post(f"/api/v1/projects/{pid}/coverage/draft").json()
    electrical_row = next(row for row in census["rows"] if row["trade_code"] == "electrical")
    assert electrical_row["evidence_refs"][0]["text_quote"] == "E-101 ELECTRICAL SITE PLAN"
    unverified_refs = [
        {**ref, "verified_sheet_number": None, "verified_sheet_title": None}
        for ref in electrical_row["evidence_refs"]
    ]
    patched = client.patch(
        f"/api/v1/projects/{pid}/coverage/{electrical_row['id']}",
        json={"evidence_refs": unverified_refs},
    )
    assert patched.status_code == 200

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    assert drafted.status_code == 200
    electrical_created = next(row for row in drafted.json()["created"] if row["trade_code"] == "electrical")
    assert electrical_created["evidence_count"] == 1

    detail = client.get(f"/api/v1/projects/{pid}/scope-items/{electrical_created['id']}")
    assert detail.status_code == 200
    evidence = detail.json()["evidence"]
    assert evidence[0]["extracted_text_quote"] == "E-101 ELECTRICAL SITE PLAN"
    assert evidence[0]["verified_sheet_number"] == "unverified"
    assert bool(evidence[0]["requires_human_verification"]) is True


def test_generic_scope_evidence_ref_prefers_sheet_quote_over_pointer():
    from app.generic_scope import _first_evidence_ref

    row = {
        "evidence_refs": [
            {
                "sheet_id": "sheet-pointer",
                "pdf_page_number": 1,
                "verified_sheet_number": "G-001",
                "reason": "",
            },
            {
                "sheet_id": "sheet-quoted",
                "pdf_page_number": 2,
                "verified_sheet_number": None,
                "verified_sheet_title": None,
                "text_quote": "E-101 ELECTRICAL SITE PLAN",
            },
        ]
    }

    ref = _first_evidence_ref(row)

    assert ref is not None
    assert ref["sheet_id"] == "sheet-quoted"
    assert ref["text_quote"] == "E-101 ELECTRICAL SITE PLAN"


def test_generic_scope_evidence_ref_prefers_verified_pointer_over_reason_only():
    from app.generic_scope import _first_evidence_ref

    row = {
        "evidence_refs": [
            {
                "sheet_id": "sheet-pointer",
                "pdf_page_number": 1,
                "verified_sheet_number": "G-001",
                "verified_sheet_title": "COVER SHEET AND SHEET INDEX",
            },
            {
                "sheet_id": "sheet-reason",
                "pdf_page_number": 2,
                "verified_sheet_number": None,
                "verified_sheet_title": None,
                "reason": "sheet_prefix:E",
            },
        ]
    }

    ref = _first_evidence_ref(row)

    assert ref is not None
    assert ref["sheet_id"] == "sheet-pointer"
    assert ref["verified_sheet_number"] == "G-001"


def test_generic_scope_draft_is_idempotent(client):
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")

    first = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft").json()
    second = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft").json()

    assert first["created_count"] > 0
    assert second["created_count"] == 0
    assert second["skipped_count"] == first["created_count"]
    assert {row["reason"] for row in second["skipped"]} == {"active_scope_exists"}


def test_generic_scope_draft_extracts_review_required_explicit_gate_width(client):
    from tests.conftest import make_sheet_pdf

    pdf = make_sheet_pdf([
        {
            "number": "A001",
            "title": "SITE PLAN - EXISTING & TEMPORARY CONTROLS",
            "body": (
                "TEMPORARY FENCE ENCLOSURE WITH MESH SCREEN. "
                "PROVIDE GATES FOR PEDESTRIAN AND VEHICLE ACCESS.\n"
                "4 FT. EMERGENCY EGRESS GATE - INSTALL EMERGENCY EXIT ONLY SIGN ON GATE"
            ),
        }
    ])
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Explicit Gate Width Proof"},
        files={"plan": ("gate-plan.pdf", pdf, "application/pdf")},
    ).json()["project_id"]
    assert client.post(f"/api/v1/projects/{pid}/process").status_code == 202
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    assert client.patch(
        f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
        json={
            "verified_sheet_number": "A001",
            "verified_sheet_title": "SITE PLAN - EXISTING & TEMPORARY CONTROLS",
            "review_status": "verified",
        },
    ).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/coverage/draft").status_code == 200

    drafted = client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    assert drafted.status_code == 200
    item = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=architectural_general"
    ).json()["items"][0]
    assert item["quantity"] == "4.0"
    assert item["unit"] == "LF"
    assert item["quantity_basis"] == "explicit_plan_quantity"
    assert item["review_status"] == "blocked"

    detail = client.get(f"/api/v1/projects/{pid}/scope-items/{item['id']}").json()
    assert {issue["code"] for issue in detail["scope_item"]["blocking_issues"]} == {"missing_pricing_basis"}
    assert detail["trade_data"]["explicit_subscope_only"] is True
    assert detail["trade_data"]["quantity_method"] == "explicit_source_dimension_review_required"
    provenance = detail["scope_item"]["raw_quantity_inputs"]["explicit_source_quantity_v1"]
    assert provenance["source"] == "processed_sheet_text"
    assert provenance["subscope_only"] is True
    assert provenance["requires_human_review"] is True
    assert detail["evidence"][0]["pdf_page_number"] == 1
    assert detail["evidence"][0]["verified_sheet_number"] == "A001"
    assert "4 FT. EMERGENCY EGRESS GATE" in detail["evidence"][0]["extracted_text_quote"]
    assert bool(detail["evidence"][0]["requires_human_verification"]) is True


def test_generic_scope_draft_unknown_project_404(client):
    resp = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/coverage/generic-scope/draft"
    )
    assert resp.status_code == 404
