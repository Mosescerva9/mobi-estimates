"""Generic lane pricing-prep API."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.generic_pricing import assign_generic_pricing_methods, seed_generic_cost_provenance
from app.generic_pricing_inputs import PricingInputError, apply_generic_pricing_input
from app.router_tenant_guard import require_project_for_request

pricing_prep_router = APIRouter(prefix="/projects", tags=["pricing-prep"])


class CostProvenanceSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_date: date
    pricing_date: date


class PricingMethodDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regenerate_qa: bool = Field(default=False)


class GenericPricingInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing_method: str = Field(pattern="^(unit_rate_needed|quote_based|allowance)$")
    amount: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=128)
    actor: str = Field(default="system", max_length=128)
    note: str | None = Field(default=None, max_length=1000)
    cost_components: dict[str, Any] | None = None


_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "invalid_amount": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "method_mismatch": status.HTTP_409_CONFLICT,
}


def _pricing_input_http(exc: PricingInputError) -> HTTPException:
    return HTTPException(status_code=_ERROR_STATUS.get(exc.code, 400), detail=exc.message)


def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> None:
    require_project_for_request(project_id, tenant_id=tenant_id, company_id=company_id)


@pricing_prep_router.post("/{project_id}/pricing/generic-methods/draft")
def draft_project_generic_pricing_methods(
    project_id: UUID,
    body: PricingMethodDraftRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Assign internal pricing-method metadata to generic scope items.

    This does not price, approve, or deliver estimates.
    """
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    return assign_generic_pricing_methods(project_id)


@pricing_prep_router.post("/{project_id}/pricing/generic-inputs/{scope_item_id}/apply")
def apply_project_generic_pricing_input(
    project_id: UUID,
    scope_item_id: UUID,
    body: GenericPricingInputRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Apply a verified generic pricing basis to a scope item.

    This records readiness input only. It does not create a final priced estimate,
    approve work, publish pricing, or deliver customer output.
    """
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    try:
        return apply_generic_pricing_input(
            project_id,
            scope_item_id,
            pricing_method=body.pricing_method,
            amount=body.amount,
            source=body.source,
            actor=body.actor,
            note=body.note,
            cost_components=body.cost_components,
        )
    except PricingInputError as exc:
        raise _pricing_input_http(exc)


@pricing_prep_router.post("/{project_id}/pricing/generic-cost-provenance/seed")
def seed_project_generic_cost_provenance(
    project_id: UUID,
    body: CostProvenanceSeedRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a draft-only cost provenance shell for later verified rates.

    This does not publish a cost-book version and does not produce prices.
    """
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    return seed_generic_cost_provenance(
        project_id,
        effective_date=body.effective_date,
        pricing_date=body.pricing_date,
    )
