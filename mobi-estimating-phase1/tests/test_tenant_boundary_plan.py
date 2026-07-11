"""Tenant identity/isolation discovery and two-tenant test plan tests (audit P0-2)."""

from __future__ import annotations

import pytest

from app.tenant_boundary import (
    assert_request_matches_project_tenant,
    assert_same_tenant_project_access,
    build_tenant_project_context,
    get_tenant_boundary_discovery,
    get_two_tenant_test_plan,
)
from app.config import settings
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
