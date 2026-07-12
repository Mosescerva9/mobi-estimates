"""Basis of Estimate draft API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.boe import draft_boe
from app.router_tenant_guard import require_project_for_request

boe_router = APIRouter(prefix="/projects", tags=["boe"])


def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> None:
    require_project_for_request(project_id, tenant_id=tenant_id, company_id=company_id)


@boe_router.get("/{project_id}/boe/draft")
def get_project_boe_draft(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return deterministic draft BOE JSON.

    This endpoint does not create a PDF, approve an estimate, send a message, or
    deliver customer-facing final estimate content.
    """
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    return draft_boe(project_id)
