"""Estimate readiness gate API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.estimate_readiness import evaluate_estimate_readiness
from app.router_tenant_guard import require_project_for_request

readiness_router = APIRouter(prefix="/projects", tags=["estimate-readiness"])


@readiness_router.get("/{project_id}/estimate-readiness")
def get_project_estimate_readiness(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Evaluate internal owner-review readiness.

    This does not approve, publish, price, send, or deliver a customer estimate.
    """
    require_project_for_request(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    return evaluate_estimate_readiness(project_id)
