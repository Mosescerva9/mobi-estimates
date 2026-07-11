"""Tenant identity/isolation discovery and two-tenant test plan tests (audit P0-2)."""

from __future__ import annotations

import pytest

from app.tenant_boundary import (
    assert_same_tenant_project_access,
    build_tenant_project_context,
    get_tenant_boundary_discovery,
    get_two_tenant_test_plan,
)


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
