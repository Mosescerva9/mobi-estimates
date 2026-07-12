"""Customer revision request API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.customer_revisions import (
    RevisionDecisionError,
    create_revision_requests,
    decide_revision_request,
    list_customer_safe_revision_history,
    list_revision_requests,
    list_revision_rescope_versions,
    resolve_revision_rescope,
    submit_customer_safe_revision_request,
)
from app.router_tenant_guard import require_project_for_request

revision_router = APIRouter(prefix="/projects", tags=["customer-revisions"])


class RevisionParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="customer_message", max_length=64)
    actor: str = Field(default="customer", max_length=128)
    text: str = Field(min_length=1, max_length=10000)


class CustomerRevisionSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)


class RevisionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(accepted|rejected|needs_clarification)$")
    reviewer: str = Field(default="staff", max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class RevisionRescopeResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(default="staff", max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


def _enforce_project_access(
    project_id: UUID,
    tenant_id: str | None,
    company_id: str | None,
) -> None:
    require_project_for_request(project_id, tenant_id=tenant_id, company_id=company_id)


@revision_router.get("/{project_id}/customer-revisions")
def list_project_customer_revisions(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    items = list_revision_requests(project_id)
    return {"items": items, "total": len(items)}


@revision_router.get("/{project_id}/customer-revisions/customer-history")
def list_project_customer_safe_revision_history(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return a customer-safe, read-only revision history view.

    This endpoint is the contract for customer-facing portals. It intentionally
    omits raw parser text, internal notes, reviewers, snapshots, readiness
    internals, pricing language, and mutation controls.
    """
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    return list_customer_safe_revision_history(project_id)


@revision_router.post("/{project_id}/customer-revisions/customer-submit")
def submit_project_customer_safe_revision(
    project_id: UUID,
    body: CustomerRevisionSubmitRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record a customer revision request and return only a safe customer view.

    This does not decide the request, rescope, price, approve, deliver, bill, or
    send external messages.
    """
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    return submit_customer_safe_revision_request(project_id, raw_text=body.text)


@revision_router.post("/{project_id}/customer-revisions/parse")
def parse_project_customer_revisions(
    project_id: UUID,
    body: RevisionParseRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Parse and log customer revision feedback internally.

    This does not send a message, regenerate an estimate, or deliver revised work.
    """
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    return create_revision_requests(
        project_id,
        source=body.source,
        actor=body.actor,
        raw_text=body.text,
    )


@revision_router.post("/{project_id}/customer-revisions/{request_id}/decide")
def decide_project_customer_revision(
    project_id: UUID,
    request_id: UUID,
    body: RevisionDecisionRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record internal decision for a parsed customer revision.

    This creates a rescope/reprice/clarification task marker only. It does not
    send messages, regenerate estimates, or deliver revised work.
    """
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    try:
        return decide_revision_request(
            project_id,
            request_id,
            decision=body.decision,
            reviewer=body.reviewer,
            notes=body.notes,
        )
    except RevisionDecisionError as exc:
        code_map = {
            "not_found": 404, "already_decided": 409, "invalid_decision": 422,
            "not_accepted_for_rescope": 409, "rescope_blocker_missing": 409,
            "already_resolved": 409,
        }
        raise HTTPException(status_code=code_map.get(exc.code, 400), detail=exc.message)


@revision_router.post("/{project_id}/customer-revisions/{request_id}/resolve-rescope")
def resolve_project_customer_revision_rescope(
    project_id: UUID,
    request_id: UUID,
    body: RevisionRescopeResolveRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Resolve an accepted customer revision rescope blocker internally.

    This snapshots before/after internal scope state and reruns readiness. It does
    not send messages, regenerate a customer estimate, or unlock customer delivery.
    """
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    req = body or RevisionRescopeResolveRequest()
    try:
        return resolve_revision_rescope(
            project_id,
            request_id,
            actor=req.actor,
            notes=req.notes,
        )
    except RevisionDecisionError as exc:
        code_map = {
            "not_found": 404, "already_decided": 409, "invalid_decision": 422,
            "not_accepted_for_rescope": 409, "rescope_blocker_missing": 409,
            "already_resolved": 409,
        }
        raise HTTPException(status_code=code_map.get(exc.code, 400), detail=exc.message)


@revision_router.get("/{project_id}/customer-revisions/{request_id}/rescope-versions")
def list_project_customer_revision_rescope_versions(
    project_id: UUID,
    request_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _enforce_project_access(project_id, x_mobi_tenant_id, x_mobi_company_id)
    items = list_revision_rescope_versions(project_id, request_id)
    return {"items": items, "total": len(items)}
