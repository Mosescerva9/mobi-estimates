"""Internal clarification package API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.clarification_package import build_clarification_package
from app.router_tenant_guard import require_project_for_request

clarification_router = APIRouter(prefix="/projects", tags=["clarifications"])


@clarification_router.get("/{project_id}/clarifications/package")
def get_project_clarification_package(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return internal clarification candidates.

    This endpoint does not approve, publish, send, email, bill, or deliver a
    customer-facing construction estimate.
    """
    require_project_for_request(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    return build_clarification_package(project_id)
