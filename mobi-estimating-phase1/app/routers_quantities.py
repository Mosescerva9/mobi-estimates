"""Quantity requirements API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_project
from app.estimating.quantities import QuantityBasis
from app.quantity_requirements import (
    QuantityRequirementError,
    apply_quantity_requirement,
    draft_quantity_requirements,
    list_quantity_requirements,
)

quantity_router = APIRouter(prefix="/projects", tags=["quantity-requirements"])


class QuantityApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    quantity: str = Field(min_length=1, max_length=64)
    unit: str = Field(min_length=1, max_length=32)
    quantity_basis: QuantityBasis = QuantityBasis.MANUAL_REVIEWER_ENTRY
    source: str = Field(default="verified_input", max_length=64)
    actor: str = Field(default="system", max_length=128)
    note: str | None = Field(default=None, max_length=1000)


_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "scope_not_found": status.HTTP_409_CONFLICT,
    "already_resolved": status.HTTP_409_CONFLICT,
    "invalid_quantity": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_unit": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _http(exc: QuantityRequirementError) -> HTTPException:
    return HTTPException(status_code=_ERROR_STATUS.get(exc.code, 400), detail=exc.message)


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@quantity_router.get("/{project_id}/quantity-requirements")
def list_project_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    items = list_quantity_requirements(project_id)
    return {"items": items, "total": len(items)}


@quantity_router.post("/{project_id}/quantity-requirements/draft")
def draft_project_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    """Draft internal quantity requirements from missing-quantity scope blockers.

    This does not generate quantities, price estimates, or deliver customer output.
    """
    _require_project(project_id)
    return draft_quantity_requirements(project_id)


@quantity_router.post("/{project_id}/quantity-requirements/{requirement_id}/apply")
def apply_project_quantity_requirement(
    project_id: UUID,
    requirement_id: UUID,
    body: QuantityApplyRequest,
) -> dict[str, Any]:
    """Apply a verified quantity to the linked scope item.

    This resolves the quantity requirement and clears only the missing_quantity
    blocker. It does not price, approve, or deliver the estimate.
    """
    _require_project(project_id)
    try:
        return apply_quantity_requirement(
            project_id,
            requirement_id,
            quantity=body.quantity,
            unit=body.unit,
            quantity_basis=str(body.quantity_basis),
            source=body.source,
            actor=body.actor,
            note=body.note,
        )
    except QuantityRequirementError as exc:
        raise _http(exc)
