"""Generic lane pricing-prep API."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_project
from app.generic_pricing import assign_generic_pricing_methods, seed_generic_cost_provenance

pricing_prep_router = APIRouter(prefix="/projects", tags=["pricing-prep"])


class CostProvenanceSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_date: date
    pricing_date: date


class PricingMethodDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regenerate_qa: bool = Field(default=False)


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@pricing_prep_router.post("/{project_id}/pricing/generic-methods/draft")
def draft_project_generic_pricing_methods(
    project_id: UUID,
    body: PricingMethodDraftRequest | None = None,
) -> dict[str, Any]:
    """Assign internal pricing-method metadata to generic scope items.

    This does not price, approve, or deliver estimates.
    """
    _require_project(project_id)
    return assign_generic_pricing_methods(project_id)


@pricing_prep_router.post("/{project_id}/pricing/generic-cost-provenance/seed")
def seed_project_generic_cost_provenance(
    project_id: UUID,
    body: CostProvenanceSeedRequest,
) -> dict[str, Any]:
    """Create a draft-only cost provenance shell for later verified rates.

    This does not publish a cost-book version and does not produce prices.
    """
    _require_project(project_id)
    return seed_generic_cost_provenance(
        project_id,
        effective_date=body.effective_date,
        pricing_date=body.pricing_date,
    )
