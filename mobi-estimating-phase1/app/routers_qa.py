"""QA Findings Log API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.qa_findings import draft_qa_findings, list_qa_findings
from app.router_tenant_guard import require_project_for_request

qa_router = APIRouter(prefix="/projects", tags=["qa"])


def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> None:
    require_project_for_request(project_id, tenant_id=tenant_id, company_id=company_id)


@qa_router.get("/{project_id}/qa/findings")
def list_project_qa_findings(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    items = list_qa_findings(project_id)
    return {"items": items, "total": len(items)}


@qa_router.post("/{project_id}/qa/findings/draft")
def draft_project_qa_findings(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Regenerate automated internal QA findings.

    This is an internal log generator. It does not approve, price, send, or deliver
    a customer estimate.
    """
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    return draft_qa_findings(project_id)
