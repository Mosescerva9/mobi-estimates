"""Tenant identity/isolation discovery and two-tenant test plan tests (audit P0-2)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

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
from app.schemas import ProjectStatus
from app.services import storage
from tests.conftest import make_sheet_pdf, prepare_priced_project, prepare_verified_project


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
    queue_gap = next(gap for gap in discovery["gaps"] if gap["id"] == "queue_and_cache_tenantless")
    artifact_gap = next(gap for gap in discovery["gaps"] if gap["id"] == "local_artifact_paths_tenantless")
    assert "tenant/company/project-scoped local paths" in artifact_gap["evidence"]
    assert {
        "tests/test_tenant_boundary_plan.py::test_upload_persists_original_pdf_under_tenant_scoped_project_path",
        "tests/test_tenant_boundary_plan.py::test_processing_artifacts_are_written_under_tenant_scoped_project_path",
    }.issubset(set(artifact_gap["implemented_evidence"]))
    assert {"private object storage", "signed access checks"}.issubset(
        set(artifact_gap["remaining_blockers"])
    )
    assert "extraction-cache keys now carry tenant/company identity" in queue_gap["evidence"]
    assert "not yet proven tenant-scoped" not in queue_gap["evidence"]
    assert {
        "tests/test_extraction_cache.py::test_extraction_cache_key_includes_tenant_and_company_identity",
        "tests/test_extraction_cache.py::test_extraction_cache_storage_is_partitioned_by_tenant_company_key",
    }.issubset(set(queue_gap["implemented_evidence"]))
    assert {"durable queues", "leases", "traces", "model-call context"}.issubset(
        set(queue_gap["remaining_blockers"])
    )


def test_two_tenant_test_plan_includes_allow_and_cross_tenant_denies() -> None:
    plan = get_two_tenant_test_plan()

    assert plan["schema_version"] == "tenant_boundary_plan_v1"
    assert plan["execution_status"] == "partial_local_tests_only"
    assert len(plan["fixtures"]) == 2
    assert {fixture["tenant_id"] for fixture in plan["fixtures"]} == {"tenant_a", "tenant_b"}
    assert plan["allow_check_count"] >= 1
    assert plan["deny_check_count"] >= 4
    assert plan["planned_check_count"] == len(plan["matrix"])
    assert plan["implemented_check_count"] == 6
    assert plan["remaining_planned_check_count"] == 0

    cross_tenant_denies = [
        row
        for row in plan["matrix"]
        if row["actor_tenant"] != row["target_tenant"] and row["expected"] == "deny"
    ]
    assert len(cross_tenant_denies) >= 4
    surfaces = {row["surface"] for row in cross_tenant_denies}
    assert {"engine_api", "auth_claims", "artifact_storage", "workflow_cache"}.issubset(surfaces)


def test_two_tenant_plan_claims_only_executed_local_slices() -> None:
    plan = get_two_tenant_test_plan()

    rows = {row["id"]: row for row in plan["matrix"]}
    assert rows["tenant_a_can_read_own_project"]["status"] == "local_test_passing"
    assert rows["tenant_a_cannot_read_tenant_b_project"]["status"] == "local_test_passing"
    assert rows["tenant_a_cannot_mutate_tenant_b_project"]["status"] == "local_test_passing"
    assert rows["tampered_project_claim_is_denied"]["status"] == "local_test_passing"
    assert rows["tampered_project_claim_is_denied"]["implemented_evidence"] == [
        "tests/test_tenant_boundary_plan.py::test_project_status_api_denies_tampered_tenant_company_claim_pair",
    ]
    assert rows["tenant_a_cannot_fetch_tenant_b_artifact"]["status"] == "local_test_passing"
    assert {
        "tests/test_tenant_boundary_plan.py::test_processing_routes_deny_cross_tenant_project_and_artifact_access",
        "tests/test_tenant_boundary_plan.py::test_processing_artifact_route_denies_confused_deputy_path_swap",
        "tests/test_tenant_boundary_plan.py::test_processing_image_route_denies_confused_deputy_path_swap",
    }.issubset(set(rows["tenant_a_cannot_fetch_tenant_b_artifact"]["implemented_evidence"]))
    assert rows["tenant_b_job_cannot_reuse_tenant_a_cache"]["status"] == "local_test_passing"
    assert rows["tenant_b_job_cannot_reuse_tenant_a_cache"]["implemented_evidence"] == [
        "tests/test_extraction_cache.py::test_extraction_cache_key_includes_tenant_and_company_identity",
        "tests/test_extraction_cache.py::test_extraction_cache_storage_is_partitioned_by_tenant_company_key",
    ]
    assert not any(row.get("status") == "passing" for row in plan["matrix"])
    assert all(row["status"] in {"planned", "local_test_passing"} for row in plan["matrix"])


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


def test_project_creation_denies_null_sentinel_tenant_identity_at_db_boundary() -> None:
    """Direct DB callers must not persist malformed tenant/company identity rows."""

    with pytest.raises(PermissionError, match="tenant_project_context_required:tenant_id"):
        database.create_project(
            project_id=uuid4(),
            name="Malformed tenant project",
            contractor_name=None,
            original_file_name="plans.pdf",
            stored_file_path="/tmp/plans.pdf",
            status=ProjectStatus.UPLOADED.value,
            page_count=1,
            file_sha256="a" * 64,
            file_size_bytes=123,
            tenant_id="null",
            company_id="company_a",
        )


def test_project_creation_normalizes_tenant_identity_at_db_boundary(client) -> None:
    project_id = uuid4()

    row = database.create_project(
        project_id=project_id,
        name="Trimmed tenant project",
        contractor_name=None,
        original_file_name="plans.pdf",
        stored_file_path="/tmp/plans.pdf",
        status=ProjectStatus.UPLOADED.value,
        page_count=1,
        file_sha256="b" * 64,
        file_size_bytes=123,
        tenant_id=" tenant_a ",
        company_id=" company_a ",
    )

    assert row["id"] == str(project_id)
    assert row["tenant_id"] == "tenant_a"
    assert row["company_id"] == "company_a"


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


def test_project_status_api_executes_two_tenant_matrix_allow_and_deny_rows(client, valid_pdf_bytes) -> None:
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


def test_project_status_api_denies_tampered_tenant_company_claim_pair(client, valid_pdf_bytes) -> None:
    """A valid tenant with a swapped company claim must not read project state."""

    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B tampered claim project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    allowed = client.get(
        f"/api/v1/projects/{project_id}/status",
        headers=tenant_b_headers,
    )
    assert allowed.status_code == 200

    denied_swapped_company = client.get(
        f"/api/v1/projects/{project_id}/status",
        headers={"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_a"},
    )
    assert denied_swapped_company.status_code == 403
    assert "cross_tenant_project_access_denied:company_id" in str(denied_swapped_company.json())

    denied_swapped_tenant = client.get(
        f"/api/v1/projects/{project_id}/status",
        headers={"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_b"},
    )
    assert denied_swapped_tenant.status_code == 403
    assert "cross_tenant_project_access_denied:tenant_id" in str(denied_swapped_tenant.json())


def test_database_status_update_for_tenant_denies_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B DB status project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        database.update_project_status_for_tenant(
            project_id,
            ProjectStatus.PROCESSING,
            tenant_id="tenant_a",
            company_id="company_a",
        )
    stored = database.get_project(project_id)
    assert stored is not None
    assert stored["status"] == ProjectStatus.UPLOADED.value

    updated = database.update_project_status_for_tenant(
        project_id,
        ProjectStatus.PROCESSING,
        tenant_id=" tenant_b ",
        company_id=" company_b ",
    )
    assert updated is not None
    assert updated["status"] == ProjectStatus.PROCESSING.value


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


def test_estimate_readiness_api_denies_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    """Readiness evidence must not be exposed through UUID-only/cross-tenant access."""

    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B readiness project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    allowed = client.get(
        f"/api/v1/projects/{project_id}/estimate-readiness",
        headers=tenant_b_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["project_id"] == project_id

    denied = client.get(
        f"/api/v1/projects/{project_id}/estimate-readiness",
        headers=tenant_a_headers,
    )
    assert denied.status_code == 403
    assert "cross_tenant_project_access_denied" in str(denied.json())

    missing = client.get(f"/api/v1/projects/{project_id}/estimate-readiness", headers={})
    assert missing.status_code == 403
    assert "tenant_project_context_required" in str(missing.json())


def test_owner_review_package_api_denies_cross_tenant_uuid_substitution(client, valid_pdf_bytes) -> None:
    """Internal review packets carry readiness/BOE evidence and must be tenant scoped."""

    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B owner review project"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]

    allowed = client.get(
        f"/api/v1/projects/{project_id}/owner-review/package",
        headers=tenant_b_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["project_id"] == project_id
    assert allowed.json()["package_type"] == "internal_owner_review_v1"
    assert allowed.json()["customer_delivery_ready"] is False

    denied = client.get(
        f"/api/v1/projects/{project_id}/owner-review/package",
        headers=tenant_a_headers,
    )
    assert denied.status_code == 403
    assert "cross_tenant_project_access_denied" in str(denied.json())

    missing = client.get(f"/api/v1/projects/{project_id}/owner-review/package", headers={})
    assert missing.status_code == 403
    assert "tenant_project_context_required" in str(missing.json())


def test_project_status_mutation_api_executes_two_tenant_matrix_deny_row(client, valid_pdf_bytes) -> None:
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


def test_project_scoped_engine_routes_deny_uuid_only_missing_tenant_headers(client, valid_pdf_bytes) -> None:
    """Project-scoped internal evidence routes must not expose UUID-only access."""

    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B UUID-only route deny"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload.status_code == 201
    project_id = upload.json()["project_id"]
    fake_id = "00000000-0000-0000-0000-000000000000"

    checks = [
        ("get", f"/api/v1/projects/{project_id}/status", None),
        ("get", f"/api/v1/projects/{project_id}/estimate-readiness", None),
        ("get", f"/api/v1/projects/{project_id}/coverage", None),
        ("post", f"/api/v1/projects/{project_id}/coverage", {"trade_code": "painting", "trade_name": "Painting"}),
        ("get", f"/api/v1/projects/{project_id}/boe/draft", None),
        ("get", f"/api/v1/projects/{project_id}/owner-review/package", None),
        ("post", f"/api/v1/projects/{project_id}/pricing/preview", {"cost_book_version_id": fake_id}),
        ("get", f"/api/v1/projects/{project_id}/estimates", None),
        ("post", f"/api/v1/projects/{project_id}/estimates", {"name": "Estimate", "cost_book_version_id": fake_id}),
        ("get", f"/api/v1/projects/{project_id}/proposals", None),
        ("get", f"/api/v1/projects/{project_id}/customer-revisions", None),
    ]
    for method, path, json_body in checks:
        request = getattr(client, method)
        kwargs = {"headers": {}}
        if json_body is not None:
            kwargs["json"] = json_body
        response = request(path, **kwargs)
        assert response.status_code == 403, path
        assert "tenant_project_context_required" in str(response.json()), path


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


def test_processing_job_lookup_fails_closed_on_tenant_mismatched_active_job(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A mismatched active job"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    # Simulate a stale/corrupt row that shares the project UUID but not the tenant
    # identity. Tenant-scoped lookup must not expose it or treat it as an
    # idempotent active job.
    with database.get_connection() as connection:
        connection.execute(
            "UPDATE processing_jobs SET tenant_id = ?, company_id = ? WHERE id = ?",
            ("tenant_b", "company_b", job["id"]),
        )
        connection.commit()

    assert database.get_latest_job(project_id) is None
    retry_outcome, retry_job, _ = database.claim_processing_slot(project_id, force=False)
    assert retry_outcome == "invalid_state"
    assert retry_job is None


def test_internal_project_status_update_fails_closed_on_tenantless_project_row(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenantless internal status update"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE projects SET tenant_id = NULL, company_id = NULL WHERE id = ?",
            (str(project_id),),
        )
        connection.commit()

    with pytest.raises(PermissionError, match="tenant_project_context_required"):
        database.update_project_status(project_id, ProjectStatus.PROCESSING)

    unchanged = database.get_project(project_id)
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] is None
    assert unchanged["company_id"] is None


def test_processing_job_update_fails_closed_on_tenant_mismatched_job(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A mismatched update job"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE processing_jobs SET tenant_id = ?, company_id = ? WHERE id = ?",
            ("tenant_b", "company_b", job["id"]),
        )
        connection.commit()

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        database.update_job(UUID(job["id"]), status="processing")

    unchanged = database.get_job(UUID(job["id"]))
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] == "tenant_b"
    assert unchanged["company_id"] == "company_b"


def test_processing_job_update_fails_closed_on_tenantless_job(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenantless update job"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE processing_jobs SET tenant_id = NULL, company_id = NULL WHERE id = ?",
            (job["id"],),
        )
        connection.commit()

    with pytest.raises(PermissionError, match="tenant_project_context_required"):
        database.update_job(UUID(job["id"]), status="processing")

    unchanged = database.get_job(UUID(job["id"]))
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] is None
    assert unchanged["company_id"] is None


def test_processing_job_update_denies_identity_field_mutation(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    upload = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Immutable job identity update"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    assert upload.status_code == 201
    project_id = UUID(upload.json()["project_id"])

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with pytest.raises(ValueError, match="processing job identity fields are immutable: tenant_id"):
        database.update_job(UUID(job["id"]), tenant_id="tenant_b")

    unchanged = database.get_job(UUID(job["id"]))
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["company_id"] == "company_a"
    assert unchanged["project_id"] == str(project_id)


def test_processing_route_denies_confused_deputy_original_pdf_path_swap(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A original PDF"},
        files={"plan": ("a.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B original PDF"},
        files={"plan": ("b.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]
    tenant_b_project = database.get_project(project_b_id)
    assert tenant_b_project is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE projects SET stored_file_path = ? WHERE id = ?",
            (tenant_b_project["stored_file_path"], project_a_id),
        )
        connection.commit()

    response = client.post(
        f"/api/v1/projects/{project_a_id}/process",
        json={},
        headers=tenant_a_headers,
    )

    assert response.status_code == 403
    assert "Original uploaded PDF path does not match project tenant context" in str(response.json())
    project_a = database.get_project(UUID(project_a_id))
    assert project_a is not None
    assert project_a["status"] == "uploaded"
    assert database.get_latest_job(UUID(project_a_id)) is None
    assert database.list_sheets(UUID(project_a_id), limit=100, offset=0) == ([], 0)


def test_processing_worker_denies_confused_deputy_original_pdf_path_swap(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A worker original PDF"},
        files={"plan": ("a.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B worker original PDF"},
        files={"plan": ("b.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = upload_a.json()["project_id"]
    project_b_id = upload_b.json()["project_id"]
    tenant_b_project = database.get_project(project_b_id)
    assert tenant_b_project is not None
    outcome, job, _ = database.claim_processing_slot(project_a_id, force=False)
    assert outcome == "created"
    assert job is not None

    with database.get_connection() as connection:
        connection.execute(
            "UPDATE projects SET stored_file_path = ? WHERE id = ?",
            (tenant_b_project["stored_file_path"], project_a_id),
        )
        connection.commit()

    result = process_project(UUID(project_a_id), job["id"])

    assert result == {"status": "failed", "error_code": "original_pdf_tenant_mismatch"}
    failed_job = database.get_job(job["id"])
    assert failed_job is not None
    assert failed_job["status"] == "failed"
    assert failed_job["error_code"] == "original_pdf_tenant_mismatch"
    project_a = database.get_project(UUID(project_a_id))
    assert project_a is not None
    assert project_a["status"] == "failed"
    assert database.list_sheets(UUID(project_a_id), limit=100, offset=0) == ([], 0)


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
    project_row = database.get_project(UUID(project_id))
    assert project_row is not None
    assert project_row["stored_file_path"] == relative
    assert not project_row["stored_file_path"].startswith(("/", "\\"))
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


def test_insert_sheet_binds_sheet_identity_to_project_and_job_tenant(client, valid_pdf_bytes) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}
    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A insert sheet guard"},
        files={"plan": ("a.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B insert sheet guard"},
        files={"plan": ("b.pdf", valid_pdf_bytes, "application/pdf")},
        headers=tenant_b_headers,
    )
    assert upload_a.status_code == 201
    assert upload_b.status_code == 201
    project_a_id = UUID(upload_a.json()["project_id"])
    project_b_id = UUID(upload_b.json()["project_id"])

    outcome_a, job_a, _ = database.claim_processing_slot(project_a_id, force=False)
    outcome_b, job_b, _ = database.claim_processing_slot(project_b_id, force=False)
    assert outcome_a == "created"
    assert outcome_b == "created"
    assert job_a is not None
    assert job_b is not None

    def sheet_payload(**overrides):
        payload = {
            "id": str(uuid4()),
            "project_id": str(project_a_id),
            "job_id": job_a["id"],
            "pdf_page_number": 1,
            "page_index": 0,
            "detected_sheet_number": "A-101",
            "detected_sheet_title": "PLAN",
            "detection_confidence": 0.99,
            "requires_review": 0,
            "requires_ocr": 0,
            "text_char_count": 12,
            "page_width_points": 612.0,
            "page_height_points": 792.0,
            "rotation": 0,
            "page_sha256": "c" * 64,
            "duplicate_of_sheet_id": None,
            "full_image_path": "tenants/tenant_a/companies/company_a/projects/x/processed/page-001/full.png",
            "thumbnail_path": "tenants/tenant_a/companies/company_a/projects/x/processed/page-001/thumbnail.png",
            "text_path": "tenants/tenant_a/companies/company_a/projects/x/processed/page-001/text.txt",
            "processing_status": "complete",
            "processing_error": None,
            "review_status": "pending",
            "review_notes": None,
            "verified_sheet_number": None,
            "verified_sheet_title": None,
            "verified_at": None,
        }
        payload.update(overrides)
        return payload

    mismatched_identity_payload = sheet_payload(tenant_id="tenant_b", company_id="company_b")
    with pytest.raises(ValueError, match="sheet tenant/company identity must match project"):
        database.insert_sheet(mismatched_identity_payload)

    mismatched_job_payload = sheet_payload(job_id=job_b["id"])
    with pytest.raises(ValueError, match="sheet job identity must match project tenant"):
        database.insert_sheet(mismatched_job_payload)

    with database.get_connection() as connection:
        rejected_rows = connection.execute(
            "SELECT COUNT(*) FROM sheets WHERE id IN (?, ?)",
            (mismatched_identity_payload["id"], mismatched_job_payload["id"]),
        ).fetchone()[0]
    assert rejected_rows == 0

    inserted = database.insert_sheet(sheet_payload(tenant_id=None, company_id=None))
    assert inserted["project_id"] == str(project_a_id)
    assert inserted["job_id"] == job_a["id"]
    assert inserted["tenant_id"] == "tenant_a"
    assert inserted["company_id"] == "company_a"
    assert database.count_sheets(project_a_id) == 1

    latest_job_b = database.get_latest_job(project_b_id)
    assert latest_job_b is not None
    assert latest_job_b["id"] == job_b["id"]
    assert database.count_sheets(project_b_id) == 0


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
    assert "TENANT B SECRET TEXT" in _read_sheet_text(tenant_b_sheet)

    tenant_a_sheet = database.get_sheet(UUID(project_a_id), UUID(sheet_a_id))
    assert tenant_a_sheet is not None
    self_consistent_corrupt_sheet = {
        **tenant_a_sheet,
        "tenant_id": tenant_b_sheet["tenant_id"],
        "company_id": tenant_b_sheet["company_id"],
        "text_path": tenant_b_sheet["text_path"],
    }
    assert _read_sheet_text(self_consistent_corrupt_sheet) == ""

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
    assert "TENANT B SECRET TEXT" in _read_census_sheet_text(tenant_b_sheet)

    tenant_a_sheet = database.get_sheet(UUID(project_a_id), UUID(sheet_a_id))
    assert tenant_a_sheet is not None
    self_consistent_corrupt_sheet = {
        **tenant_a_sheet,
        "tenant_id": tenant_b_sheet["tenant_id"],
        "company_id": tenant_b_sheet["company_id"],
        "text_path": tenant_b_sheet["text_path"],
    }
    assert _read_census_sheet_text(self_consistent_corrupt_sheet) == ""

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


def test_processing_image_route_denies_confused_deputy_path_swap(client) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}

    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A image route"},
        files={"plan": ("a.pdf", make_sheet_pdf([{"number": "A-101", "title": "A PLAN"}]), "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B image route"},
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
            "UPDATE sheets SET full_image_path = ? WHERE id = ?",
            (tenant_b_sheet["full_image_path"], sheet_a_id),
        )
        connection.commit()

    response = client.get(
        f"/api/v1/projects/{project_a_id}/sheets/{sheet_a_id}/image",
        headers=tenant_a_headers,
    )
    assert response.status_code == 403
    assert "Artifact path does not match project tenant context" in str(response.json())


def test_processing_artifact_route_denies_self_consistent_sheet_tenant_drift(client) -> None:
    tenant_a_headers = {"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": "company_a"}
    tenant_b_headers = {"X-Mobi-Tenant-Id": "tenant_b", "X-Mobi-Company-Id": "company_b"}

    upload_a = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant A artifact row drift"},
        files={"plan": ("a.pdf", make_sheet_pdf([{"number": "A-101", "title": "A PLAN"}]), "application/pdf")},
        headers=tenant_a_headers,
    )
    upload_b = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Tenant B artifact row drift"},
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
            """
            UPDATE sheets
            SET tenant_id = ?, company_id = ?, thumbnail_path = ?
            WHERE id = ?
            """,
            (
                tenant_b_sheet["tenant_id"],
                tenant_b_sheet["company_id"],
                tenant_b_sheet["thumbnail_path"],
                sheet_a_id,
            ),
        )
        connection.commit()

    response = client.get(
        f"/api/v1/projects/{project_a_id}/sheets/{sheet_a_id}/thumbnail",
        headers=tenant_a_headers,
    )
    assert response.status_code == 404
    assert "Sheet not found" in str(response.json())


def test_scope_assembly_mapping_denies_corrupt_cross_tenant_identity(client) -> None:
    """Assembly mappings are pricing inputs and must not be served from UUIDs alone."""
    from app.database import get_connection

    tenant_headers = {"X-Mobi-Tenant-Id": "test_tenant", "X-Mobi-Company-Id": "test_company"}
    project_id, _ = prepare_priced_project(client)
    scope_items = client.get(f"/api/v1/projects/{project_id}/scope-items", headers=tenant_headers).json()["items"]
    scope_item_id = scope_items[0]["id"]

    created = client.post(
        f"/api/v1/projects/{project_id}/scope-items/{scope_item_id}/assembly-mapping",
        json={"assembly_code": "PT-WALL", "reviewer_id": "qa"},
        headers=tenant_headers,
    )
    assert created.status_code == 200, created.text
    mapping = created.json()
    assert mapping["tenant_id"] == "test_tenant"
    assert mapping["company_id"] == "test_company"

    with get_connection() as c:
        c.execute(
            "UPDATE scope_assembly_mappings SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", mapping["id"]),
        )
        c.commit()

    denied = client.get(
        f"/api/v1/projects/{project_id}/scope-items/{scope_item_id}/assembly-mapping",
        headers=tenant_headers,
    )
    assert denied.status_code == 404
    assert "No mapping for scope item" in denied.text


def test_estimate_line_items_deny_cross_tenant_scope_item_pointer(client) -> None:
    """Estimate line items must not persist or serve cross-tenant scope pointers."""
    from uuid import UUID

    from app import pricing_db
    from app.database import get_connection

    project_a_id, cost_book_version_id = prepare_priced_project(client)
    project_b_id, _ = prepare_priced_project(client)
    tenant_headers = {"X-Mobi-Tenant-Id": "test_tenant", "X-Mobi-Company-Id": "test_company"}

    estimate = client.post(
        f"/api/v1/projects/{project_a_id}/estimates",
        json={"name": "Tenant line test", "cost_book_version_id": cost_book_version_id},
        headers=tenant_headers,
    ).json()
    estimate_version_id = estimate["version"]["id"]
    project_a_scope = client.get(
        f"/api/v1/projects/{project_a_id}/scope-items", headers=tenant_headers
    ).json()["items"][0]["id"]
    project_b_scope = client.get(
        f"/api/v1/projects/{project_b_id}/scope-items", headers=tenant_headers
    ).json()["items"][0]["id"]

    with pytest.raises(PermissionError):
        pricing_db.replace_line_items(
            estimate_version_id,
            UUID(project_a_id),
            [
                {
                    "trade_code": "painting",
                    "scope_item_id": project_b_scope,
                    "description": "cross tenant scope pointer",
                    "quantity": "1",
                    "unit": "EA",
                    "direct_cost_total": "1.00",
                    "status": "priced",
                }
            ],
        )

    pricing_db.replace_line_items(
        estimate_version_id,
        UUID(project_a_id),
        [
            {
                "trade_code": "painting",
                "scope_item_id": project_a_scope,
                "description": "valid scope pointer",
                "quantity": "1",
                "unit": "EA",
                "direct_cost_total": "1.00",
                "status": "priced",
            }
        ],
    )
    items = pricing_db.get_line_items(estimate_version_id)
    assert len(items) == 1
    line_id = items[0]["id"]

    with get_connection() as c:
        c.execute("UPDATE estimate_line_items SET scope_item_id=? WHERE id=?", (project_b_scope, line_id))
        c.commit()

    assert pricing_db.get_line_items(estimate_version_id) == []
    assert pricing_db.get_line_item(estimate_version_id, UUID(line_id)) is None


def test_coverage_rows_ignore_tenant_mismatched_rows_for_same_project(client) -> None:
    """Coverage dispositions must not be read, updated, or deduped from a project UUID alone."""
    from app.database import get_connection

    tenant_headers = {"X-Mobi-Tenant-Id": "test_tenant", "X-Mobi-Company-Id": "test_company"}
    project_id = prepare_verified_project(client)
    payload = {
        "trade_code": "electrical",
        "trade_name": "Electrical",
        "csi_divisions": ["26"],
        "detected_from": ["sheet_discipline"],
        "disposition": "allowance",
        "basis_note": "Carried as an allowance pending customer revision.",
        "status": "ready",
    }
    created = client.post(
        f"/api/v1/projects/{project_id}/coverage", json=payload, headers=tenant_headers
    )
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]

    with get_connection() as c:
        c.execute(
            "UPDATE trade_coverage_rows SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", row_id),
        )
        c.commit()

    listing = client.get(f"/api/v1/projects/{project_id}/coverage", headers=tenant_headers).json()
    assert listing["total"] == 0

    validation = client.get(
        f"/api/v1/projects/{project_id}/coverage/validate", headers=tenant_headers
    ).json()
    assert validation["row_count"] == 0
    assert validation["findings"][0]["code"] == "coverage_matrix_empty"

    patched = client.patch(
        f"/api/v1/projects/{project_id}/coverage/{row_id}",
        json={"disposition": "excluded_by_mobi"},
        headers=tenant_headers,
    )
    assert patched.status_code == 404

    # The mismatched row must be neither served nor silently mutated, and it must
    # not block the owning tenant from creating its own row for the same trade.
    recreated = client.post(
        f"/api/v1/projects/{project_id}/coverage", json=payload, headers=tenant_headers
    )
    assert recreated.status_code == 201, recreated.text
    assert recreated.json()["id"] != row_id

    with get_connection() as c:
        stale = c.execute(
            "SELECT disposition, tenant_id FROM trade_coverage_rows WHERE id=?", (row_id,)
        ).fetchone()
    assert stale["disposition"] == "allowance"
    assert stale["tenant_id"] == "other_tenant"


def test_coverage_validation_ignores_tenant_mismatched_scope_item_evidence(client) -> None:
    """A tenant-mismatched scope item must not satisfy an included row's basis requirement."""
    from app.database import get_connection

    tenant_headers = {"X-Mobi-Tenant-Id": "test_tenant", "X-Mobi-Company-Id": "test_company"}
    project_id, _ = prepare_priced_project(client)
    scope_items = client.get(
        f"/api/v1/projects/{project_id}/scope-items", headers=tenant_headers
    ).json()["items"]
    assert scope_items
    trade_code = scope_items[0]["trade_code"]

    created = client.post(
        f"/api/v1/projects/{project_id}/coverage",
        json={
            "trade_code": trade_code,
            "trade_name": trade_code.title(),
            "disposition": "included_module",
            "status": "ready",
        },
        headers=tenant_headers,
    )
    assert created.status_code == 201, created.text

    # Scope items are the only basis for this included row, so it validates today.
    validation = client.get(
        f"/api/v1/projects/{project_id}/coverage/validate", headers=tenant_headers
    ).json()
    assert validation["complete"] is True

    with get_connection() as c:
        c.execute(
            "UPDATE scope_items SET tenant_id=?, company_id=? WHERE project_id=? AND trade_code=?",
            ("other_tenant", "other_company", project_id, trade_code),
        )
        c.commit()

    validation = client.get(
        f"/api/v1/projects/{project_id}/coverage/validate", headers=tenant_headers
    ).json()
    assert validation["complete"] is False
    assert [finding["code"] for finding in validation["findings"]] == ["included_without_basis"]
