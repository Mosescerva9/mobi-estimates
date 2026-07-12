"""Generic estimate draft bridge API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.generic_estimate_bridge import GenericEstimateBridgeError, build_generic_estimate_draft
from app.proposals.draft_preview import DraftPreviewError, build_draft_proposal_preview
from app.router_tenant_guard import require_project_for_request

estimate_bridge_router = APIRouter(prefix="/projects", tags=["generic-estimate-bridge"])


class GenericEstimateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Generic All-Trade Draft Estimate", min_length=1, max_length=255)


_ERROR_STATUS = {
    "invalid_amount": status.HTTP_422_UNPROCESSABLE_ENTITY,
}

_PREVIEW_ERROR_STATUS = {
    "estimate_not_found": status.HTTP_404_NOT_FOUND,
    "estimate_version_not_found": status.HTTP_404_NOT_FOUND,
    "preview_delivery_locked": status.HTTP_423_LOCKED,
}


@estimate_bridge_router.post("/{project_id}/estimates/generic-draft", status_code=status.HTTP_201_CREATED)
def create_project_generic_estimate_draft(
    project_id: UUID,
    body: GenericEstimateDraftRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create an internal draft estimate version from generic priced scope.

    This diagnostic/internal bridge does not approve, issue, send, deliver, bill,
    or mark anything customer-ready.
    """
    require_project_for_request(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    try:
        return build_generic_estimate_draft(
            project_id,
            name=(body.name if body is not None else "Generic All-Trade Draft Estimate"),
        )
    except GenericEstimateBridgeError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@estimate_bridge_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/proposal-preview")
def get_project_generic_estimate_proposal_preview(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return a read-only customer-safe preview for an internal draft estimate version.

    This endpoint does not create a proposal, approve, issue, send, deliver, bill,
    or mark anything customer-ready.
    """
    require_project_for_request(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    try:
        return build_draft_proposal_preview(project_id, estimate_id, version_id)
    except DraftPreviewError as exc:
        raise HTTPException(
            status_code=_PREVIEW_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": exc.code, "message": exc.message},
        ) from exc
