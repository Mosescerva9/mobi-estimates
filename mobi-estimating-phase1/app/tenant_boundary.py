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
        "evidence": "app/database.py project and job lookups are keyed by project_id without tenant/company columns.",
        "required_repair": "Persist tenant/company identity on every project, job, artifact, scope, quantity, pricing, review, and workflow row.",
    },
    {
        "id": "local_artifact_paths_tenantless",
        "severity": "p0",
        "status": "blocked",
        "component": "engine_artifacts",
        "evidence": "Local upload/artifact paths are project-oriented and are not proven tenant-scoped object keys.",
        "required_repair": "Use private tenant/project-scoped object keys with signed access checks and immutable content hashes.",
    },
    {
        "id": "queue_and_cache_tenantless",
        "severity": "p0",
        "status": "blocked",
        "component": "workflow",
        "evidence": "Processing jobs and extraction cache keys are not proven to include tenant identity.",
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
        "status": "planned",
    },
    {
        "id": "tenant_a_cannot_read_tenant_b_project",
        "surface": "engine_api",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b",
        "expected": "deny",
        "status": "planned",
    },
    {
        "id": "tenant_a_cannot_mutate_tenant_b_project",
        "surface": "engine_api",
        "actor_tenant": "tenant_a",
        "target_tenant": "tenant_b",
        "target": "project_b",
        "expected": "deny",
        "status": "planned",
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

    return {
        "schema_version": SCHEMA_VERSION,
        "fixtures": list(_TWO_TENANT_FIXTURES),
        "matrix": list(_TWO_TENANT_MATRIX),
        "planned_check_count": len(_TWO_TENANT_MATRIX),
        "deny_check_count": sum(1 for row in _TWO_TENANT_MATRIX if row["expected"] == "deny"),
        "allow_check_count": sum(1 for row in _TWO_TENANT_MATRIX if row["expected"] == "allow"),
        "execution_status": "planned_not_implemented",
    }
