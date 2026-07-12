"""Internal owner-review package API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.owner_review import build_owner_review_package
from app.router_tenant_guard import require_project_for_request

owner_review_router = APIRouter(prefix="/projects", tags=["owner-review"])


@owner_review_router.get("/{project_id}/owner-review/package")
def get_project_owner_review_package(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return internal owner-review package.

    This endpoint does not approve, publish, send, email, bill, or deliver a
    customer-facing construction estimate.
    """
    require_project_for_request(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    return build_owner_review_package(project_id)
