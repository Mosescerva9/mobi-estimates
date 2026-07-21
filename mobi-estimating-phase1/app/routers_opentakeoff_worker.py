"""Deployable internal OpenTakeoff worker API router.

These routes are the authenticated, server-to-server boundary for the VPS-side
OpenTakeoff worker. They are mounted at ``/internal/takeoff`` and are staff-only:
the portal/admin UI calls them with a shared key plus tenant identity headers and
an actor role/id, submitting IDs and geometry — never filesystem paths. Identity
and authorization are always derived from headers and server-resolved rows, not
trusted from the JSON body.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.takeoff.worker_api import (
    WorkerActor,
    WorkerApiError,
    reconcile_body_identity,
    require_staff_actor,
    worker_api_service,
    _require_identity_headers,
)

opentakeoff_worker_router = APIRouter(prefix="/internal/takeoff", tags=["opentakeoff-worker"])


# ---------------------------------------------------------------------------
# Request models. Body identity fields are optional and, when present, must
# match the authenticated headers; the headers are always authoritative.
# Unknown fields are forbidden so browser/client code cannot smuggle provider
# selectors such as sheet_key or filesystem-ish values through ignored JSON.
# ---------------------------------------------------------------------------
class WorkerRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateJobRequest(WorkerRequestModel):
    project_id: UUID
    document_id: UUID
    operation: str
    trade: str = Field(min_length=1, max_length=64)
    scope_category: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=256)
    sheet_id: UUID | None = None
    condition: str | None = None
    default_description: str | None = None
    requested_by: str | None = None
    tenant_id: str | None = None
    company_id: str | None = None


class ConfirmScaleRequest(WorkerRequestModel):
    sheet_id: UUID
    # The browser submits the sheet identity/page only. The provider sheet key is
    # derived server-side from the verified project document filename + page.
    page_number: int = Field(ge=1)
    scale_source: str = Field(min_length=1, max_length=256)
    scale_label: str = Field(min_length=1, max_length=128)
    units_per_px: float | None = Field(default=None, gt=0)
    tenant_id: str | None = None
    company_id: str | None = None


class MeasureRequest(WorkerRequestModel):
    geometry: dict[str, Any]
    condition: str | None = None
    sheet_id: UUID | None = None
    tenant_id: str | None = None
    company_id: str | None = None


class CancelRequest(WorkerRequestModel):
    tenant_id: str | None = None
    company_id: str | None = None


class RetryRequest(WorkerRequestModel):
    tenant_id: str | None = None
    company_id: str | None = None


def _resolve_context(
    x_mobi_tenant_id: str | None,
    x_mobi_company_id: str | None,
    x_mobi_actor_role: str | None,
    x_mobi_actor_id: str | None,
) -> tuple[dict[str, str], WorkerActor]:
    identity = _require_identity_headers(x_mobi_tenant_id, x_mobi_company_id)
    actor = require_staff_actor(x_mobi_actor_role, x_mobi_actor_id)
    return identity, actor


def _fail(exc: WorkerApiError) -> HTTPException:
    return HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.message},
    )


@opentakeoff_worker_router.post("/jobs", status_code=201)
def create_job(
    body: CreateJobRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        identity, actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        reconcile_body_identity("tenant_id", identity["tenant_id"], body.tenant_id)
        reconcile_body_identity("company_id", identity["company_id"], body.company_id)
        row, created = worker_api_service.create_job(
            actor=actor,
            tenant_id=identity["tenant_id"],
            company_id=identity["company_id"],
            project_id=body.project_id,
            document_id=body.document_id,
            operation=body.operation,
            trade=body.trade,
            scope_category=body.scope_category,
            condition=body.condition,
            default_description=body.default_description or "OpenTakeoff worker measurement",
            idempotency_key=body.idempotency_key,
            requested_by=body.requested_by,
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row, "created": created}


@opentakeoff_worker_router.get("/jobs/{job_id}")
def get_job(
    job_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        identity, _actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        row = worker_api_service.get_job(
            tenant_id=identity["tenant_id"], company_id=identity["company_id"], job_id=job_id
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row}


@opentakeoff_worker_router.post("/jobs/{job_id}/confirm-scale")
def confirm_scale(
    job_id: UUID,
    body: ConfirmScaleRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        identity, actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        reconcile_body_identity("tenant_id", identity["tenant_id"], body.tenant_id)
        reconcile_body_identity("company_id", identity["company_id"], body.company_id)
        row = worker_api_service.confirm_scale(
            actor=actor,
            tenant_id=identity["tenant_id"],
            company_id=identity["company_id"],
            job_id=job_id,
            sheet_id=body.sheet_id,
            page_number=body.page_number,
            scale_source=body.scale_source,
            scale_label=body.scale_label,
            units_per_px=body.units_per_px,
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row}


@opentakeoff_worker_router.post("/jobs/{job_id}/measure-line")
def measure_line(
    job_id: UUID,
    body: MeasureRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return _measure(
        "line", job_id, body, x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
    )


@opentakeoff_worker_router.post("/jobs/{job_id}/measure-polygon")
def measure_polygon(
    job_id: UUID,
    body: MeasureRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return _measure(
        "polygon", job_id, body, x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
    )


@opentakeoff_worker_router.post("/jobs/{job_id}/measure-count")
def measure_count(
    job_id: UUID,
    body: MeasureRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    # Count geometry is a marker list under ``geometry.points`` (>= 1 marker);
    # each marker is one EA. See the worker service for the deterministic tally.
    return _measure(
        "count", job_id, body, x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
    )


def _measure(
    kind: str,
    job_id: UUID,
    body: MeasureRequest,
    x_mobi_tenant_id: str | None,
    x_mobi_company_id: str | None,
    x_mobi_actor_role: str | None,
    x_mobi_actor_id: str | None,
) -> dict[str, Any]:
    try:
        identity, actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        reconcile_body_identity("tenant_id", identity["tenant_id"], body.tenant_id)
        reconcile_body_identity("company_id", identity["company_id"], body.company_id)
        row = worker_api_service.measure(
            actor=actor,
            tenant_id=identity["tenant_id"],
            company_id=identity["company_id"],
            job_id=job_id,
            kind=kind,
            geometry=body.geometry,
            condition=body.condition,
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row}


@opentakeoff_worker_router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: UUID,
    body: CancelRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        identity, actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        if body is not None:
            reconcile_body_identity("tenant_id", identity["tenant_id"], body.tenant_id)
            reconcile_body_identity("company_id", identity["company_id"], body.company_id)
        row = worker_api_service.cancel(
            actor=actor,
            tenant_id=identity["tenant_id"],
            company_id=identity["company_id"],
            job_id=job_id,
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row}


@opentakeoff_worker_router.post("/jobs/{job_id}/retry", status_code=201)
def retry_job(
    job_id: UUID,
    body: RetryRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create (or idempotently return) a durable retry attempt of a failed job.

    Returns ``{job, created}`` where ``created`` is False when the failed job
    already has a retry attempt (idempotent). The new job is linked to the failed
    parent via attempt_number/parent_job_id/root_job_id; the original failed job
    and its error are retained unchanged.
    """
    try:
        identity, actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        if body is not None:
            reconcile_body_identity("tenant_id", identity["tenant_id"], body.tenant_id)
            reconcile_body_identity("company_id", identity["company_id"], body.company_id)
        row, created = worker_api_service.retry_job(
            actor=actor,
            tenant_id=identity["tenant_id"],
            company_id=identity["company_id"],
            job_id=job_id,
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"job": row, "created": created}


@opentakeoff_worker_router.get("/jobs/{job_id}/artifacts")
def get_artifacts(
    job_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
    x_mobi_actor_role: str | None = Header(default=None),
    x_mobi_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        identity, _actor = _resolve_context(
            x_mobi_tenant_id, x_mobi_company_id, x_mobi_actor_role, x_mobi_actor_id
        )
        artifacts = worker_api_service.get_artifacts(
            tenant_id=identity["tenant_id"], company_id=identity["company_id"], job_id=job_id
        )
    except WorkerApiError as exc:
        raise _fail(exc) from exc
    return {"artifacts": artifacts}
