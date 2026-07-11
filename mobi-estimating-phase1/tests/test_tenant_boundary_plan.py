"""Tenant identity/isolation discovery and two-tenant test plan tests (audit P0-2)."""

from __future__ import annotations

from app.tenant_boundary import get_tenant_boundary_discovery, get_two_tenant_test_plan


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
