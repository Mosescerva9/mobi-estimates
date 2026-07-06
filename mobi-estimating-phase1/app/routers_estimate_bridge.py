"""Generic estimate draft bridge API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_project
from app.generic_estimate_bridge import GenericEstimateBridgeError, build_generic_estimate_draft

estimate_bridge_router = APIRouter(prefix="/projects", tags=["generic-estimate-bridge"])


class GenericEstimateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Generic All-Trade Draft Estimate", min_length=1, max_length=255)


_ERROR_STATUS = {
    "invalid_amount": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@estimate_bridge_router.post("/{project_id}/estimates/generic-draft", status_code=status.HTTP_201_CREATED)
def create_project_generic_estimate_draft(
    project_id: UUID,
    body: GenericEstimateDraftRequest | None = None,
) -> dict[str, Any]:
    """Create an internal draft estimate version from generic priced scope.

    This diagnostic/internal bridge does not approve, issue, send, deliver, bill,
    or mark anything customer-ready.
    """
    _require_project(project_id)
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
