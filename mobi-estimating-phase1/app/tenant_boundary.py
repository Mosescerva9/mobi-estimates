"""Tenant identity/isolation discovery + two-tenant test plan (audit P0-2).

The current Phase-1 estimating engine is intentionally fail-closed for staging and
production until tenant-scoped identity exists. This module records the known
engine-boundary gaps and exposes a deterministic two-tenant adversarial test plan
so the next implementation slices can convert each planned check into executable
integration tests without losing the audit requirements.

It does not authenticate requests, authorize projects, touch storage, or claim
that tenant isolation is implemented. All current rows are marked ``planned`` or
``blocked`` until code and environment evidence prove otherwise.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "tenant_boundary_plan_v1"

_MALFORMED_IDENTITY_SENTINELS = frozenset({"none", "null", "undefined", "nan"})

# Source-observed engine gaps from the GPT-5.6 Sol audit and current repo
# inspection. Keep this conservative: clearing an item requires implemented code
# plus tests against two tenants.
TENANT_BOUNDARY_GAPS: tuple[dict[str, Any], ...] = (
    {
        "id": "engine_auth_shared_key_only",
        "severity": "p0",
        "status": "blocked",
        "component": "engine_auth",
        "evidence": "app/auth.py accepts an optional shared API key; no tenant-scoped JWT/workload identity is enforced.",
        "required_repair": "Require tenant-scoped signed identity with issuer/audience/expiry and project/company claims.",
    },
    {
        "id": "sqlite_project_rows_tenantless",
        "severity": "p0",
        "status": "blocked",
        "component": "engine_database",
        "evidence": "Projects, processing jobs, and processed sheet rows now carry tenant/company identity in the first P0 slices; remaining evidence-bearing engine rows still require tenant scoping.",
        "required_repair": "Persist tenant/company identity on every artifact, scope, quantity, pricing, review, cache, and workflow row.",
    },
    {
        "id": "local_artifact_paths_tenantless",
        "severity": "p0",
        "status": "blocked",
        "component": "engine_artifacts",
        "evidence": "New uploads and generated processing artifacts use tenant/company/project-scoped local paths in narrow local tests; local artifacts are still not proven private object-storage keys with signed access checks.",
        "implemented_evidence": [
            "tests/test_tenant_boundary_plan.py::test_upload_persists_original_pdf_under_tenant_scoped_project_path",
            "tests/test_tenant_boundary_plan.py::test_processing_artifacts_are_written_under_tenant_scoped_project_path",
        ],
        "remaining_blockers": [
            "private object storage",
            "signed access checks",
            "immutable content hashes for every artifact",
        ],
        "required_repair": "Use private tenant/project-scoped object keys with signed access checks and immutable content hashes.",
    },
    {
        "id": "queue_and_cache_tenantless",
        "severity": "p0",
        "status": "blocked",
        "component": "workflow",
        "evidence": "Processing jobs and extraction-cache keys now carry tenant/company identity in narrow local tests; future durable queues, leases, traces, and model-call context are still not proven tenant-scoped.",
        "implemented_evidence": [
            "tests/test_tenant_boundary_plan.py::test_processing_job_rows_carry_project_tenant_identity",
            "tests/test_extraction_cache.py::test_extraction_cache_key_includes_tenant_and_company_identity",
            "tests/test_extraction_cache.py::test_extraction_cache_storage_is_partitioned_by_tenant_company_key",
        ],
        "remaining_blockers": [
            "durable queues",
            "leases",
            "traces",
            "model-call context",
        ],
        "required_repair": "Include tenant identity in every queue message, lease, idempotency key, cache key, trace, and model-call context.",
    },
)

_TWO_TENANT_FIXTURES: tuple[dict[str, str], ...] = (
    {"tenant_id": "tenant_a", "company_id": "company_a", "project_id": "project_a"},
    {"tenant_id": "tenant_b", "company_id": "company_b", "project_id": "project_b"},
)

_TWO_TENANT_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "id": "tenant_a_can_read_own_project",
        "surface": "engine_api",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_a",
        "target": "project_a",
        "expected": "allow",
        "status": "local_test_passing",
        "implemented_evidence": [
            "tests/test_tenant_boundary_plan.py::test_project_status_api_executes_two_tenant_matrix_allow_and_deny_rows",
        ],
    },
    {
        "id": "tenant_a_cannot_read_tenant_b_project",
        "surface": "engine_api",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b",
        "expected": "deny",
        "status": "local_test_passing",
        "implemented_evidence": [
            "tests/test_tenant_boundary_plan.py::test_project_status_api_executes_two_tenant_matrix_allow_and_deny_rows",
        ],
    },
    {
        "id": "tenant_a_cannot_mutate_tenant_b_project",
        "surface": "engine_api",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b",
        "expected": "deny",
        "status": "local_test_passing",
        "implemented_evidence": [
            "tests/test_tenant_boundary_plan.py::test_project_status_mutation_api_executes_two_tenant_matrix_deny_row",
        ],
    },
    {
        "id": "tampered_project_claim_is_denied",
        "surface": "auth_claims",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b",
        "expected": "deny",
        "status": "planned",
    },
    {
        "id": "tenant_a_cannot_fetch_tenant_b_artifact",
        "surface": "artifact_storage",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b_artifact",
        "expected": "deny",
        "status": "planned",
    },
    {
        "id": "tenant_b_job_cannot_reuse_tenant_a_cache",
        "surface": "workflow_cache",
        "actor_tenant": "tenant_b",
        "target_tenant": "tenant_a",
        "target": "project_a_cache_key",
        "expected": "deny",
        "status": "planned",
    },
)


def get_tenant_boundary_discovery() -> dict[str, Any]:
    """Return current P0 tenant-boundary status without implying readiness."""

    blocked = [gap for gap in TENANT_BOUNDARY_GAPS if gap["status"] == "blocked"]
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_isolation_ready": False,
        "release_start_allowed": False,
        "status": "blocked",
        "blocked_gap_count": len(blocked),
        "gaps": list(TENANT_BOUNDARY_GAPS),
        "required_release_condition": (
            "Every engine request, row, object, queue message, cache key, trace, "
            "and model call must carry validated tenant identity; cross-tenant attempts must deny."
        ),
    }


def get_two_tenant_test_plan() -> dict[str, Any]:
    """Return the required two-tenant adversarial matrix for P0-2."""

    implemented_count = sum(
        1 for row in _TWO_TENANT_MATRIX if row["status"] == "local_test_passing"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "fixtures": list(_TWO_TENANT_FIXTURES),
        "matrix": list(_TWO_TENANT_MATRIX),
        "planned_check_count": len(_TWO_TENANT_MATRIX),
        "implemented_check_count": implemented_count,
        "remaining_planned_check_count": len(_TWO_TENANT_MATRIX) - implemented_count,
        "deny_check_count": sum(1 for row in _TWO_TENANT_MATRIX if row["expected"] == "deny"),
        "allow_check_count": sum(1 for row in _TWO_TENANT_MATRIX if row["expected"] == "allow"),
        "execution_status": "partial_local_tests_only",
    }


def _normalize_identity_component(value: str | None) -> str:
    """Return a tenant identity component or ``""`` when it is not auditable.

    Tenant/company/project IDs are security-boundary evidence. Common null
    sentinels must not be accepted as real tenant identifiers, otherwise a caller
    could create or access a project under a plausible-looking ``"null"`` or
    ``"undefined"`` tenant and bypass the intended fail-closed missing-identity
    behavior.
    """

    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.lower() in _MALFORMED_IDENTITY_SENTINELS:
        return ""
    # Reject comma-delimited values so duplicate/coalesced identity headers cannot
    # be treated as one tenant. Tenant identity must be a single auditable value.
    if "," in normalized:
        return ""
    return normalized


def build_tenant_project_context(
    *, tenant_id: str | None, company_id: str | None, project_id: str | None
) -> dict[str, str]:
    """Build the minimal tenant/project identity context required by P0-2.

    This is a deliberately small, deterministic enforcement primitive for the
    next API/DB slices. It does not claim full tenant isolation. It fails closed
    whenever any identity component is missing, blank, or a common null sentinel
    so call sites cannot fall back to UUID-only project access.
    """

    context = {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "project_id": project_id,
    }
    normalized = {name: _normalize_identity_component(value) for name, value in context.items()}
    missing = [name for name, value in normalized.items() if not value]
    if missing:
        raise PermissionError(
            "tenant_project_context_required:" + ",".join(sorted(missing))
        )
    return normalized


def _require_tenant_project_context(
    side_name: str, context: dict[str, Any]
) -> dict[str, str]:
    """Return trimmed identity values or fail closed on blank/missing/sentinel fields."""

    required = ("tenant_id", "company_id", "project_id")
    normalized = {
        field: _normalize_identity_component(context.get(field))
        for field in required
    }
    missing = [field for field, value in normalized.items() if not value]
    if missing:
        raise PermissionError(
            f"{side_name}_tenant_project_context_required:"
            + ",".join(sorted(missing))
        )
    return normalized


def assert_same_tenant_project_access(
    actor_context: dict[str, Any], target_context: dict[str, Any]
) -> None:
    """Deny UUID-substitution access unless tenant, company, and project match.

    This guard is intentionally stricter than the eventual workflow may need for
    all operations: the first P0-2 slice proves that a tenant-A actor cannot read
    or mutate a tenant-B project by presenting only tenant-B's UUID. Broader
    role/assignment semantics can be layered on top after canonical tenant rows
    exist.
    """

    actor = _require_tenant_project_context("actor", actor_context)
    target = _require_tenant_project_context("target", target_context)

    mismatches = [field for field in actor if actor[field] != target[field]]
    if mismatches:
        raise PermissionError(
            "cross_tenant_project_access_denied:" + ",".join(sorted(mismatches))
        )


def assert_request_matches_project_tenant(
    *,
    project_row: dict[str, Any],
    request_tenant_id: str | None,
    request_company_id: str | None,
) -> None:
    """Fail closed unless request and project row carry matching tenant identity.

    This is a narrow API/DB enforcement slice, not full tenant isolation. Normal
    project-scoped API access must not allow tenantless rows, because that falls
    back to UUID-only project access. Legacy migration/quarantine handling should
    use an explicitly named non-customer path, not this guard.
    """

    project_tenant_id = project_row.get("tenant_id")
    project_company_id = project_row.get("company_id")
    project_id = project_row.get("id")
    actor = build_tenant_project_context(
        tenant_id=request_tenant_id,
        company_id=request_company_id,
        project_id=project_id,
    )
    target = _require_tenant_project_context(
        "target",
        {
            "tenant_id": project_tenant_id,
            "company_id": project_company_id,
            "project_id": project_id,
        },
    )
    assert_same_tenant_project_access(actor, target)
