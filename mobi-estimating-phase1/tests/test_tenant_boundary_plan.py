"""Tenant identity/isolation discovery and two-tenant test plan tests (audit P0-2)."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from app import database
from app.extraction.service import _read_sheet_text
from app.services.processing_service import ProcessingError, process_project
from app.trade_census import _read_sheet_text as _read_census_sheet_text
from app.tenant_boundary import (
    assert_request_matches_project_tenant,
    assert_same_tenant_project_access,
    build_tenant_project_context,
    get_tenant_boundary_discovery,
    get_two_tenant_test_plan,
)
from app.config import settings
from app.services import storage
from tests.conftest import make_sheet_pdf


def test_tenant_boundary_discovery_is_truthfully_blocked() -> None:
    discovery = get_tenant_boundary_discovery()

    assert discovery["schema_version"] == "tenant_boundary_plan_v1"
    assert discovery["tenant_isolation_ready"] is False
    assert discovery["release_start_allowed"] is False
    assert discovery["status"] == "blocked"
    assert discovery["blocked_gap_count"] >= 4

    gap_ids = {gap["id"] for gap in discovery["gaps"]}
    assert "engine_auth_shared_key_only" in gap_ids
    assert "sqlite_project_rows_tenantless" in gap_ids
    assert all(gap["severity"] == "p0" for gap in discovery["gaps"])
    assert all(gap["status"] == "blocked" for gap in discovery["gaps"])


def test_two_tenant_test_plan_includes_allow_and_cross_tenant_denies() -> None:
    plan = get_two_tenant_test_plan()

    assert plan["schema_version"] == "tenant_boundary_plan_v1"
    assert plan["execution_status"] == "planned_not_implemented"
    assert len(plan["fixtures"]) == 2
    assert {fixture["tenant_id"] for fixture in plan["fixtures"]} == {"tenant_a", "tenant_b"}
    assert plan["allow_check_count"] >= 1
    assert plan["deny_check_count"] >= 4
    assert plan["planned_check_count"] == len(plan["matrix"])

    cross_tenant_denies = [
        row
        for row in plan["matrix"]
        if row["actor_tenant"] != row["target_tenant"] and row["expected"] == "deny"
    ]
    assert len(cross_tenant_denies) >= 4
    surfaces = {row["surface"] for row in cross_tenant_denies}
    assert {"engine_api", "auth_claims", "artifact_storage", "workflow_cache"}.issubset(surfaces)


def test_two_tenant_plan_does_not_claim_enforcement_yet() -> None:
    plan = get_two_tenant_test_plan()

    assert all(row["status"] == "planned" for row in plan["matrix"])
    assert not any(row.get("status") == "passing" for row in plan["matrix"])


def test_tenant_project_context_fails_closed_when_identity_is_missing() -> None:
    with pytest.raises(PermissionError, match="tenant_project_context_required"):
        build_tenant_project_context(
            tenant_id="tenant_a",
            company_id="company_a",
            project_id=None,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "null"),
        ("tenant_id", " undefined "),
        ("company_id", "None"),
        ("project_id", "NaN"),
    ],
)
def test_tenant_project_context_fails_closed_on_null_sentinels(field, value) -> None:
    context = {
        "tenant_id": "tenant_a",
        "company_id": "company_a",
        "project_id": "project_a",
    }
    context[field] = value

    with pytest.raises(PermissionError, match=f"tenant_project_context_required:{field}"):
        build_tenant_project_context(**context)


def test_same_tenant_project_guard_denies_null_sentinel_direct_context() -> None:
    actor = {"tenant_id": "null", "company_id": "company_b", "project_id": "project_b"}
    target = build_tenant_project_context(
        tenant_id="tenant_b",
        company_id="company_b",
        project_id="project_b",
    )

    with pytest.raises(PermissionError, match="actor_tenant_project_context_required:tenant_id"):
        assert_same_tenant_project_access(actor, target)


def test_same_tenant_project_guard_allows_exact_context_match() -> None:
    actor = build_tenant_project_context(
        tenant_id=" tenant_a ",
        company_id="company_a",
        project_id="project_a",
    )
    target = build_tenant_project_context(
        tenant_id="tenant_a",
        company_id="company_a",
        project_id="project_a",
    )

    assert actor["tenant_id"] == "tenant_a"
    assert_same_tenant_project_access(actor, target)


def test_same_tenant_project_guard_denies_uuid_substitution() -> None:
    actor = build_tenant_project_context(
        tenant_id="tenant_a",
        company_id="company_a",
        project_id="project_a",
    )
    target = build_tenant_project_context(
        tenant_id="tenant_b",
        company_id="company_b",
        project_id="project_b",
    )

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        assert_same_tenant_project_access(actor, target)


def test_same_tenant_project_guard_denies_project_id_only_context() -> None:
    actor = {"project_id": "project_b"}
    target = build_tenant_project_context(
        tenant_id="tenant_b",
        company_id="company_b",
        project_id="project_b",
    )

    with pytest.raises(PermissionError, match="actor_tenant_project_context_required"):
        assert_same_tenant_project_access(actor, target)


def test_same_tenant_project_guard_denies_blank_direct_context() -> None:
    actor = {"tenant_id": "   ", "company_id": "company_b", "project_id": "project_b"}
    target = build_tenant_project_context(
        tenant_id="tenant_b",
        company_id="company_b",
        project_id="project_b",
    )

    with pytest.raises(PermissionError, match="actor_tenant_project_context_required"):
        assert_same_tenant_project_access(actor, target)


def test_project_row_tenant_guard_denies_mismatched_request_headers() -> None:
    project = {
        "id": "project_b",
        "tenant_id": "tenant_b",
        "company_id": "company_b",
    }

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        assert_request_matches_project_tenant(
            project_row=project,
            request_tenant_id="tenant_a",
            request_company_id="company_a",
        )


def test_project_row_tenant_guard_denies_tenantless_project_rows() -> None:
    project = {
        "id": "project_legacy",
        "tenant_id": None,
        "company_id": None,
    }

    with pytest.raises(PermissionError, match="target_tenant_project_context_required"):
        assert_request_matches_project_tenant(
            project_row=project,
            request_tenant_id="tenant_a",
            request_company_id="company_a",
        )


def test_project_status_api_denies_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers={"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"},
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    allowed = client.get(
        f"/api/v1/projects/{project_id}/status",
        headers={"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"},
    )
    assert allowed.status_code == 200

    denied = client.get(
        f"/api/v1/projects/{project_id}/status",
        headers={"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"},
    )
    assert denied.status_code == 403
    assert "cross_tenant_project_access_denied" in str(denied.json())


def test_project_status_api_requires_tenant_headers_for_tenant_scoped_rows(client, valid_pdf_bytes) -> None:
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant scoped project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers={"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"},
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    missing = client.get(f"/api/v1/projects/{project_id}/status", headers={})
    assert missing.status_code == 403
    assert "tenant_project_context_required" in str(missing.json())

    missing_mutation = client.patch(
        f"/api/v1/projects/{project_id}/status",
        data={"new_status": "processing"},
        headers={},
    )
    assert missing_mutation.status_code == 403
    assert "tenant_project_context_required" in str(missing_mutation.json())


def test_project_status_mutation_api_denies_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B status mutation"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    denied = client.patch(
        f"/api/v1/projects/{project_id}/status",
        data={"new_status": "processing"},
        headers=tenant_a_headers,
    )
    assert denied.status_code == 403
    assert "cross_tenant_project_access_denied" in str(denied.json())

    allowed = client.patch(
        f"/api/v1/projects/{project_id}/status",
        data={"new_status": "processing"},
        headers=tenant_b_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "processing"


def test_project_scoped_engine_routes_deny_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B engine routes"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]
    fake_id = "00000000-0000-0000-0000-000000000000"

    checks = [
        ("get", f"/api/v1/projects/{project_id}/estimate-readiness", None),
        ("get", f"/api/v1/projects/{project_id}/coverage", None),
        (
            "post",
            f"/api/v1/projects/{project_id}/coverage",
            {"trade_code": "painting", "trade_name": "Painting"},
        ),
        ("patch", f"/api/v1/projects/{project_id}/coverage/{fake_id}", {"status": "blocked"}),
        ("post", f"/api/v1/projects/{project_id}/coverage/draft", {}),
        ("post", f"/api/v1/projects/{project_id}/coverage/generic-scope/draft", {}),
        ("get", f"/api/v1/projects/{project_id}/coverage/validate", None),
        ("get", f"/api/v1/projects/{project_id}/boe/draft", None),
        ("get", f"/api/v1/projects/{project_id}/qa/findings", None),
        ("post", f"/api/v1/projects/{project_id}/qa/findings/draft", {}),
        ("get", f"/api/v1/projects/{project_id}/quantity-requirements", None),
        ("post", f"/api/v1/projects/{project_id}/quantity-requirements/draft", {}),
        (
            "post",
            f"/api/v1/projects/{project_id}/quantity-requirements/{fake_id}/apply",
            {"quantity": "12", "unit": "SF", "source": "verified_input"},
        ),
        ("get", f"/api/v1/projects/{project_id}/trades/painting/eligible-sheets", None),
        ("patch", f"/api/v1/projects/{project_id}/trades/painting/sheets/{fake_id}/eligibility", {"manual_override": "eligible"}),
        ("post", f"/api/v1/projects/{project_id}/trades/painting/extractions", {}),
        ("get", f"/api/v1/projects/{project_id}/trades/painting/extractions", None),
        ("get", f"/api/v1/projects/{project_id}/trades/painting/extractions/{fake_id}", None),
        ("get", f"/api/v1/projects/{project_id}/scope-items", None),
        ("get", f"/api/v1/projects/{project_id}/scope-items/{fake_id}", None),
        ("patch", f"/api/v1/projects/{project_id}/scope-items/{fake_id}", {"description": "corrected"}),
        ("post", f"/api/v1/projects/{project_id}/scope-items/{fake_id}/approve", {}),
        ("post", f"/api/v1/projects/{project_id}/scope-items/{fake_id}/reject", {"reason": "not in scope"}),
        ("post", f"/api/v1/projects/{project_id}/scope-items/{fake_id}/recalculate", {"formula_id": "x", "inputs": {}}),
        ("get", f"/api/v1/projects/{project_id}/owner-review/package", None),
        ("post", f"/api/v1/projects/{project_id}/pricing/generic-methods/draft", {}),
        ("post", f"/api/v1/projects/{project_id}/pricing/generic-cost-provenance/seed", {"effective_date": "2026-07-11", "pricing_date": "2026-07-11"}),
        ("post", f"/api/v1/projects/{project_id}/pricing/generic-inputs/{fake_id}/apply", {"pricing_method": "unit_rate_needed", "amount": "1", "source": "staff_verified_rate"}),
        ("post", f"/api/v1/projects/{project_id}/pricing/preview", {"cost_book_version_id": fake_id}),
        ("post", f"/api/v1/projects/{project_id}/scope-items/{fake_id}/assembly-mapping", {"assembly_code": "ASM", "reviewer_id": "qa"}),
        ("get", f"/api/v1/projects/{project_id}/scope-items/{fake_id}/assembly-mapping", None),
        ("post", f"/api/v1/projects/{project_id}/estimates", {"name": "Estimate", "cost_book_version_id": fake_id}),
        ("get", f"/api/v1/projects/{project_id}/estimates", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}", None),
        ("post", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/price", {}),
        ("post", f"/api/v1/projects/{project_id}/estimates/{fake_id}/reprice", {}),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/line-items", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/rollup", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/exceptions", None),
        ("post", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/approve", {}),
        ("post", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/line-items/{fake_id}/override", {"field": "quantity", "new_value": "2", "reason": "qa"}),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/export.json", None),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/export.csv", None),
        ("get", f"/api/v1/projects/{project_id}/clarifications/package", None),
        ("post", f"/api/v1/projects/{project_id}/estimates/generic-draft", {}),
        ("get", f"/api/v1/projects/{project_id}/estimates/{fake_id}/versions/{fake_id}/proposal-preview", None),
        ("post", f"/api/v1/projects/{project_id}/proposals", {"name": "P", "estimate_id": fake_id, "client_name": "Acme"}),
        ("get", f"/api/v1/projects/{project_id}/proposals", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}", None),
        ("post", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/issue", {}),
        ("post", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/accept", {}),
        ("post", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/decline", {"reason": "x"}),
        ("post", f"/api/v1/projects/{project_id}/proposals/{fake_id}/regenerate", {}),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/review-events", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/export.json", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/export.md", None),
        ("get", f"/api/v1/projects/{project_id}/proposals/{fake_id}/versions/{fake_id}/export.html", None),
        ("get", f"/api/v1/projects/{project_id}/customer-revisions", None),
        ("get", f"/api/v1/projects/{project_id}/customer-revisions/customer-history", None),
        ("post", f"/api/v1/projects/{project_id}/customer-revisions/customer-submit", {"text": "revise scope"}),
        ("post", f"/api/v1/projects/{project_id}/customer-revisions/parse", {"text": "revise scope"}),
        ("post", f"/api/v1/projects/{project_id}/customer-revisions/{fake_id}/decide", {"decision": "accepted"}),
        ("post", f"/api/v1/projects/{project_id}/customer-revisions/{fake_id}/resolve-rescope", {}),
        ("get", f"/api/v1/projects/{project_id}/customer-revisions/{fake_id}/rescope-versions", None),
    ]
    for method, path, json_body in checks:
        request = getattr(client, method)
        kwargs = {"headers": tenant_a_headers}
        if json_body is not None:
            kwargs["json"] = json_body
        response = request(path, **kwargs)
        assert response.status_code == 403, path
        assert "cross_tenant_project_access_denied" in str(response.json()), path


def test_processing_routes_deny_cross_tenant_project_and_artifact_access(client) -> None:
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    pdf = make_sheet_pdf([{"number": "A-101", "title": "TENANT B PLAN"}])
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B processed artifacts"},
        files={"plan": ("plans.pdf", pdf, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    denied_process = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers=tenant_a_headers,
    )
    assert denied_process.status_code == 403
    assert "cross_tenant_project_access_denied" in str(denied_process.json())

    processed = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers=tenant_b_headers,
    )
    assert processed.status_code == 202
    sheet_id = client.get(
        f"/api/v1/projects/{project_id}/sheets",
        headers=tenant_b_headers,
    ).json()["items"][0]["sheet_id"]

    checks = [
        ("get", f"/api/v1/projects/{project_id}/processing-status", None),
        ("get", f"/api/v1/projects/{project_id}/sheets", None),
        ("get", f"/api/v1/projects/{project_id}/sheets/{sheet_id}", None),
        (
            "patch",
            f"/api/v1/projects/{project_id}/sheets/{sheet_id}/verification",
            {"review_status": "verified", "verified_sheet_number": "A-101"},
        ),
        ("get", f"/api/v1/projects/{project_id}/sheets/{sheet_id}/thumbnail", None),
        ("get", f"/api/v1/projects/{project_id}/sheets/{sheet_id}/image", None),
    ]
    for method, path, json_body in checks:
        request = getattr(client, method)
        kwargs = {"headers": tenant_a_headers}
        if json_body is not None:
            kwargs["json"] = json_body
        response = request(path, **kwargs)
        assert response.status_code == 403, path
        assert "cross_tenant_project_access_denied" in str(response.json()), path


def test_processing_worker_denies_cross_tenant_job_uuid_substitution(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A worker project"},
        files={"plan": ("a.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B worker project"},
        files={"plan": ("b.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]

    outcome_a, job_a, _ = database.claim_processing_slot(project_a_id, force=False)
    outcome_b, job_b, _ = database.claim_processing_slot(project_b_id, force=False)
    assert outcome_a == "created"
    assert outcome_b == "created"
    assert job_a is not None
    assert job_b is not None

    with pytest.raises(ProcessingError) as exc:
        process_project(project_a_id, job_b["id"])
    assert exc.value.code == "job_project_tenant_mismatch"

    unchanged_b = database.get_job(job_b["id"])
    assert unchanged_b is not None
    assert unchanged_b["status"] == "queued"
    assert unchanged_b["started_at"] is None
    assert unchanged_b["tenant_id"] == "tenant_b"
    assert unchanged_b["company_id"] == "company_b"
    assert database.get_project(project_a_id)["status"] == "queued"
    assert database.list_sheets(project_a_id, limit=100, offset=0) == ([], 0)


def test_processing_routes_require_tenant_headers_for_tenant_scoped_rows(client) -> None:
    tenant_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    pdf = make_sheet_pdf([{"number": "A-101", "title": "TENANT A PLAN"}])
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A processed artifacts"},
        files={"plan": ("plans.pdf", pdf, "application/pdf")},
        headers=tenant_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    missing_process = client.post(f"/api/v1/projects/{project_id}/process", json={}, headers={})
    assert missing_process.status_code == 403
    assert "tenant_project_context_required" in str(missing_process.json())

    processed = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers=tenant_headers,
    )
    assert processed.status_code == 202
    sheet_id = client.get(
        f"/api/v1/projects/{project_id}/sheets",
        headers=tenant_headers,
    ).json()["items"][0]["sheet_id"]

    for path in [
        f"/api/v1/projects/{project_id}/processing-status",
        f"/api/v1/projects/{project_id}/sheets",
        f"/api/v1/projects/{project_id}/sheets/{sheet_id}",
        f"/api/v1/projects/{project_id}/sheets/{sheet_id}/thumbnail",
        f"/api/v1/projects/{project_id}/sheets/{sheet_id}/image",
    ]:
        response = client.get(path, headers={})
        assert response.status_code == 403, path
        assert "tenant_project_context_required" in str(response.json()), path


def test_project_scoped_engine_routes_require_tenant_headers_for_tenant_rows(client, valid_pdf_bytes) -> None:
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant header required engine routes"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers={"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"},
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    response = client.get(f"/api/v1/projects/{project_id}/estimate-readiness", headers={})
    assert response.status_code == 403
    assert "tenant_project_context_required" in str(response.json())

    coverage_response = client.get(f"/api/v1/projects/{project_id}/coverage", headers={})
    assert coverage_response.status_code == 403
    assert "tenant_project_context_required" in str(coverage_response.json())

    coverage_validate_response = client.get(f"/api/v1/projects/{project_id}/coverage/validate", headers={})
    assert coverage_validate_response.status_code == 403
    assert "tenant_project_context_required" in str(coverage_validate_response.json())

    boe_response = client.get(f"/api/v1/projects/{project_id}/boe/draft", headers={})
    assert boe_response.status_code == 403
    assert "tenant_project_context_required" in str(boe_response.json())

    qa_response = client.get(f"/api/v1/projects/{project_id}/qa/findings", headers={})
    assert qa_response.status_code == 403
    assert "tenant_project_context_required" in str(qa_response.json())

    quantity_response = client.get(f"/api/v1/projects/{project_id}/quantity-requirements", headers={})
    assert quantity_response.status_code == 403
    assert "tenant_project_context_required" in str(quantity_response.json())

    extraction_response = client.get(f"/api/v1/projects/{project_id}/scope-items", headers={})
    assert extraction_response.status_code == 403
    assert "tenant_project_context_required" in str(extraction_response.json())

    pricing_response = client.post(f"/api/v1/projects/{project_id}/pricing/generic-methods/draft", json={}, headers={})
    assert pricing_response.status_code == 403
    assert "tenant_project_context_required" in str(pricing_response.json())

    pricing_estimates_response = client.get(f"/api/v1/projects/{project_id}/estimates", headers={})
    assert pricing_estimates_response.status_code == 403
    assert "tenant_project_context_required" in str(pricing_estimates_response.json())

    pricing_preview_response = client.post(
        f"/api/v1/projects/{project_id}/pricing/preview",
        json={"cost_book_version_id": "00000000-0000-0000-0000-000000000000"},
        headers={},
    )
    assert pricing_preview_response.status_code == 403
    assert "tenant_project_context_required" in str(pricing_preview_response.json())

    clarification_response = client.get(f"/api/v1/projects/{project_id}/clarifications/package", headers={})
    assert clarification_response.status_code == 403
    assert "tenant_project_context_required" in str(clarification_response.json())


def test_duplicate_upload_detection_is_tenant_local_same_tenant_blocks(client, valid_pdf_bytes) -> None:
    headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    first = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A first"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 201
    first_project_id = first.json()["project_id"]

    duplicate = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A duplicate"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=headers,
    )

    assert duplicate.status_code == 409
    duplicate_text = str(duplicate.json())
    assert first_project_id in duplicate_text
    assert "for this tenant/company context" in duplicate_text


def test_duplicate_upload_detection_allows_cross_tenant_same_bytes_without_uuid_leak(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    first = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A public spec"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert first.status_code == 201
    first_project_id = first.json()["project_id"]

    second = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B same public spec"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )

    assert second.status_code == 201
    assert second.json()["project_id"] != first_project_id
    assert first_project_id not in str(second.json())


def test_duplicate_upload_detection_ignores_legacy_unscoped_row_for_tenant_request(client, valid_pdf_bytes) -> None:
    legacy = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Legacy unscoped"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers={},
    )
    assert legacy.status_code == 403
    assert "tenant_project_context_required" in str(legacy.json())
    assert not any(settings.upload_dir.iterdir())

    tenant = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant scoped after legacy"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers={"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"},
    )

    assert tenant.status_code == 201


@pytest.mark.parametrize(
    "headers,missing",
    [
        ({}, "company_id,tenant_id"),
        ({"X-Mobi-Tenant-Id": "tenant_a"}, "company_id"),
        ({"X-Mobi-Company-Id": "company_a"}, "tenant_id"),
        ({"X-Mobi-Tenant-Id": "null", "X-Mobi-Company-Id": "company_a"}, "tenant_id"),
    ],
)
def test_upload_requires_complete_tenant_identity_before_file_persistence(
    client, valid_pdf_bytes, headers, missing
) -> None:
    response = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Missing tenant upload"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 403
    assert f"tenant_project_context_required:{missing}" in str(response.json())
    assert not any(settings.upload_dir.iterdir())


def test_upload_persists_original_pdf_under_tenant_scoped_project_path(
    client, valid_pdf_bytes
) -> None:
    tenant_headers = {"X-Mobi-Tenant-Id": "tenant/a", "X-Mobi-Company-Id": "company:b"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant scoped object path"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_headers,
    )

    assert upload.status_code == 201
    project_id = upload.json()["project_id"]
    expected_dir = storage.project_dir(
        project_id=UUID(project_id),
        tenant_id=tenant_headers["X-Mobi-Tenant-Id"],
        company_id=tenant_headers["X-Mobi-Company-Id"],
    )
    legacy_dir = storage.project_dir(UUID(project_id))

    assert (expected_dir / "original.pdf").exists()
    assert not legacy_dir.exists()
    relative = storage.relative_to_data_root(expected_dir / "original.pdf")
    assert relative.startswith("tenants/")
    assert "/companies/" in relative
    assert "/projects/" in relative
    assert "%2F" in relative
    assert "%3A" in relative


def test_storage_path_component_encodes_dotdot_tenant_headers() -> None:
    project_id = UUID("00000000-0000-0000-0000-000000000123")
    scoped = storage.project_dir(project_id, tenant_id="..", company_id="..")
    relative = storage.relative_to_data_root(scoped)

    assert scoped.is_relative_to(storage.data_root())
    assert ".." not in scoped.relative_to(storage.data_root()).parts
    assert relative == "tenants/%2E%2E/companies/%2E%2E/projects/00000000-0000-0000-0000-000000000123"


def test_processing_artifacts_are_written_under_tenant_scoped_project_path(client) -> None:
    tenant_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant scoped processed artifacts"},
        files={"plan": ("plans.pdf", make_sheet_pdf([{"number": "A-101", "title": "PLAN"}]), "application/pdf")},
        headers=tenant_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]
    processed = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers=tenant_headers,
    )

    assert processed.status_code == 202
    tenant_processed_dir = storage.processed_dir(
        UUID(project_id),
        tenant_id=tenant_headers["X-Mobi-Tenant-Id"],
        company_id=tenant_headers["X-Mobi-Company-Id"],
    )
    legacy_processed_dir = storage.processed_dir(UUID(project_id))

    assert (tenant_processed_dir / "manifest.json").exists()
    manifest = json.loads((tenant_processed_dir / "manifest.json").read_text())
    assert manifest["project_id"] == project_id
    assert manifest["tenant_id"] == tenant_headers["X-Mobi-Tenant-Id"]
    assert manifest["company_id"] == tenant_headers["X-Mobi-Company-Id"]
    assert not legacy_processed_dir.exists()
    sheet = client.get(
        f"/api/v1/projects/{project_id}/sheets",
        headers=tenant_headers,
    ).json()["items"][0]
    detail = client.get(
        f"/api/v1/projects/{project_id}/sheets/{sheet['sheet_id']}",
        headers=tenant_headers,
    ).json()
    assert detail["artifacts"]["image_available"] is True


def test_sheet_database_helpers_fail_closed_on_tenant_identity_drift(client) -> None:
    tenant_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant drift sheet helpers"},
        files={"plan": ("plans.pdf", make_sheet_pdf([{"number": "A-101", "title": "PLAN"}]), "application/pdf")},
        headers=tenant_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]
    processed = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers=tenant_headers,
    )
    assert processed.status_code == 202
    sheet = client.get(
        f"/api/v1/projects/{project_id}/sheets",
        headers=tenant_headers,
    ).json()["items"][0]
    sheet_id = sheet["sheet_id"]
    sheet_row = database.get_sheet(UUID(project_id), UUID(sheet_id))
    assert sheet_row is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE sheets SET tenant_id = ?, company_id = ? WHERE id = ?",
            ("tenant_b", "company_b", sheet_id),
        )
        connection.commit()

    assert database.get_sheet(UUID(project_id), UUID(sheet_id)) is None
    assert database.list_sheets(UUID(project_id), limit=100, offset=0) == ([], 0)
    assert database.count_sheets(UUID(project_id)) == 0

    updated = database.update_sheet_verification(
        UUID(project_id),
        UUID(sheet_id),
        verified_sheet_number="A-101",
        verified_sheet_title="Verified",
        review_notes="should not write through tenant drift",
        review_status="verified",
        requires_review=False,
    )
    assert updated is None

    with database.get_connection() as connection:
        assert database.find_duplicate_page(
            connection, UUID(project_id), sheet_row["page_sha256"]
        ) is None
        raw = connection.execute(
            "SELECT review_status, review_notes FROM sheets WHERE id = ?",
            (sheet_id,),
        ).fetchone()
    assert raw["review_status"] == "pending"
    assert raw["review_notes"] is None
    assert database.delete_sheets_for_project(UUID(project_id)) == 0

    with database.get_connection() as connection:
        still_exists = connection.execute(
            "SELECT tenant_id, company_id FROM sheets WHERE id = ?",
            (sheet_id,),
        ).fetchone()
    assert dict(still_exists) == {"tenant_id": "tenant_b", "company_id": "company_b"}


def test_extraction_text_reader_denies_confused_deputy_path_swap(client) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}

    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A extraction text"},
        files={"plan": ("a.pdf", make_sheet_pdf([{"number": "A-101", "title": "A PLAN", "body": "TENANT A TEXT"}]), "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B extraction text"},
        files={"plan": ("b.pdf", make_sheet_pdf([{"number": "B-101", "title": "B PLAN", "body": "TENANT B SECRET TEXT"}]), "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]

    assert client.post(f"/api/v1/projects/{project_a_id}/process", json={}, headers=tenant_a_headers).status_code == 202
    assert client.post(f"/api/v1/projects/{project_b_id}/process", json={}, headers=tenant_b_headers).status_code == 202

    sheet_a_id = client.get(
        f"/api/v1/projects/{project_a_id}/sheets",
        headers=tenant_a_headers,
    ).json()["items"][0]["sheet_id"]
    sheet_b_id = client.get(
        f"/api/v1/projects/{project_b_id}/sheets",
        headers=tenant_b_headers,
    ).json()["items"][0]["sheet_id"]
    tenant_b_sheet = database.get_sheet(UUID(project_b_id), UUID(sheet_b_id))
    assert tenant_b_sheet is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE sheets SET text_path = ? WHERE id = ?",
            (tenant_b_sheet["text_path"], sheet_a_id),
        )
        connection.commit()

    tenant_a_sheet = database.get_sheet(UUID(project_a_id), UUID(sheet_a_id))
    assert tenant_a_sheet is not None
    assert _read_sheet_text(tenant_a_sheet) == ""


def test_trade_census_denies_confused_deputy_text_path_swap(client) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}

    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A trade census"},
        files={"plan": ("a.pdf", make_sheet_pdf([{"number": "A-101", "title": "A PLAN", "body": "TENANT A GENERAL NOTES"}]), "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B trade census"},
        files={"plan": ("b.pdf", make_sheet_pdf([{"number": "B-101", "title": "B PLAN", "body": "PANEL SCHEDULE\nPOWER PLAN\nTENANT B SECRET TEXT"}]), "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]

    assert client.post(f"/api/v1/projects/{project_a_id}/process", json={}, headers=tenant_a_headers).status_code == 202
    assert client.post(f"/api/v1/projects/{project_b_id}/process", json={}, headers=tenant_b_headers).status_code == 202

    sheet_a_id = client.get(
        f"/api/v1/projects/{project_a_id}/sheets",
        headers=tenant_a_headers,
    ).json()["items"][0]["sheet_id"]
    sheet_b_id = client.get(
        f"/api/v1/projects/{project_b_id}/sheets",
        headers=tenant_b_headers,
    ).json()["items"][0]["sheet_id"]
    tenant_b_sheet = database.get_sheet(UUID(project_b_id), UUID(sheet_b_id))
    assert tenant_b_sheet is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE sheets SET text_path = ? WHERE id = ?",
            (tenant_b_sheet["text_path"], sheet_a_id),
        )
        connection.commit()

    tenant_a_sheet = database.get_sheet(UUID(project_a_id), UUID(sheet_a_id))
    assert tenant_a_sheet is not None
    assert _read_census_sheet_text(tenant_a_sheet) == ""

    drafted = client.post(f"/api/v1/projects/{project_a_id}/coverage/draft", headers=tenant_a_headers)
    assert drafted.status_code == 200
    rows = drafted.json()["rows"]
    assert "electrical" not in {row["trade_code"] for row in rows}
    assert "TENANT B SECRET TEXT" not in str(rows)


def test_processing_artifact_route_denies_confused_deputy_path_swap(client) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}

    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A artifact route"},
        files={"plan": ("a.pdf", make_sheet_pdf([{"number": "A-101", "title": "A PLAN"}]), "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B artifact route"},
        files={"plan": ("b.pdf", make_sheet_pdf([{"number": "B-101", "title": "B PLAN"}]), "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]

    assert client.post(f"/api/v1/projects/{project_a_id}/process", json={}, headers=tenant_a_headers).status_code == 202
    assert client.post(f"/api/v1/projects/{project_b_id}/process", json={}, headers=tenant_b_headers).status_code == 202

    sheet_a_id = client.get(
        f"/api/v1/projects/{project_a_id}/sheets",
        headers=tenant_a_headers,
    ).json()["items"][0]["sheet_id"]
    sheet_b_id = client.get(
        f"/api/v1/projects/{project_b_id}/sheets",
        headers=tenant_b_headers,
    ).json()["items"][0]["sheet_id"]
    tenant_b_sheet = database.get_sheet(UUID(project_b_id), UUID(sheet_b_id))
    assert tenant_b_sheet is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE sheets SET thumbnail_path = ? WHERE id = ?",
            (tenant_b_sheet["thumbnail_path"], sheet_a_id),
        )
        connection.commit()

    response = client.get(
        f"/api/v1/projects/{project_a_id}/sheets/{sheet_a_id}/thumbnail",
        headers=tenant_a_headers,
    )
    assert response.status_code == 403
    assert "Artifact path does not match project tenant context" in str(response.json())
