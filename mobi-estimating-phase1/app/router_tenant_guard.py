"""Shared tenant/project guard for engine API routers.

This is a narrow P0 tenant-boundary enforcement slice: if a project row carries
``tenant_id``/``company_id``, project-scoped routes must require matching request
headers before reading or mutating UUID-addressed project data. Legacy tenantless
local rows remain readable only because the broader migration is still blocked.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.database import get_project
from app.tenant_boundary import assert_request_matches_project_tenant


def require_project_for_request(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> dict:
    """Return the project row or deny cross-tenant UUID substitution."""

    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        assert_request_matches_project_tenant(
            project_row=project,
            request_tenant_id=tenant_id,
            request_company_id=company_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return project
