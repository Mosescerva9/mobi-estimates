"""Phase 3 API: trades, sheet routing, extraction runs, scope items, and review.

All routes are mounted under ``/api/v1``. Filesystem paths are never exposed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from app.config import settings
from app.database import count_sheets, get_sheet
from app.extraction.provider_schemas import PROVIDER_SCHEMA_VERSION
from app.extraction.schemas import (
    ExtractionRequest,
    RoutingStatus,
)
from app.extraction.service import ExtractionError, route_sheets, run_extraction
from app.extraction_db import (
    claim_extraction_run,
    get_latest_derivation,
    get_run,
    get_scope_item,
    list_conflicts,
    list_evidence,
    list_review_events,
    list_runs,
    list_scope_items,
    set_manual_override,
    upsert_routing_decision,
)
from app.router_tenant_guard import require_project_for_request
from app.review.schemas import (
    ApprovalRequest,
    CorrectionRequest,
    RecalculateRequest,
    RejectionRequest,
)
from app.review.service import (
    ReviewError,
    approve_item,
    correct_item,
    recalculate_item,
    reject_item,
)
from app.trades.registry import (
    DisabledTradeError,
    UnknownTradeError,
    trade_registry,
)

trades_router = APIRouter(prefix="/trades", tags=["trades"])
extraction_router = APIRouter(prefix="/projects", tags=["extraction"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> dict:
    return require_project_for_request(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    )


def _require_trade(trade_code: str, *, enabled: bool = False):
    try:
        return trade_registry.get(trade_code, require_enabled=enabled)
    except UnknownTradeError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown trade '{trade_code}'") from exc
    except DisabledTradeError as exc:
        raise HTTPException(status_code=409, detail=f"Trade '{trade_code}' is disabled") from exc


def _trade_summary(module) -> dict[str, Any]:
    definition = module.get_definition()
    return {
        "trade_code": module.trade_code,
        "trade_name": module.trade_name,
        "enabled": trade_registry.is_enabled(module.trade_code),
        "module_version": module.module_version,
        "schema_version": module.schema_version,
        "supported_categories": definition.scope_categories,
    }


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------
@trades_router.get("")
def list_trades() -> dict[str, Any]:
    modules = trade_registry.list_modules()
    return {"trades": [_trade_summary(m) for m in modules]}


@trades_router.get("/{trade_code}")
def get_trade(trade_code: str) -> dict[str, Any]:
    module = _require_trade(trade_code)
    return module.get_definition().model_dump(mode="json")


# ---------------------------------------------------------------------------
# Sheet routing / eligibility
# ---------------------------------------------------------------------------
@extraction_router.get("/{project_id}/trades/{trade_code}/eligible-sheets")
def preview_eligible_sheets(
    project_id: UUID,
    trade_code: str,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    _require_trade(trade_code, enabled=True)
    decisions = route_sheets(
        project_id, trade_code, run_id=None, selected_sheet_ids=None, persist=False
    )
    return {
        "project_id": str(project_id),
        "trade_code": trade_code,
        "sheets": [
            {
                "sheet_id": d["sheet_id"],
                "pdf_page_number": d.get("pdf_page_number"),
                "eligibility": d["eligibility"],
                "manual_override": d.get("manual_override"),
                "effective_status": d.get("effective_status"),
                "reason": d["reason"],
            }
            for d in decisions
        ],
    }


@extraction_router.patch(
    "/{project_id}/trades/{trade_code}/sheets/{sheet_id}/eligibility"
)
def override_sheet_eligibility(
    project_id: UUID,
    trade_code: str,
    sheet_id: UUID,
    body: dict[str, Any],
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    module = _require_trade(trade_code, enabled=True)
    sheet = get_sheet(project_id, sheet_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="Sheet not found")

    override = body.get("manual_override")
    if override not in (RoutingStatus.ELIGIBLE.value, RoutingStatus.EXCLUDED.value):
        raise HTTPException(
            status_code=422,
            detail="manual_override must be 'eligible' or 'excluded'",
        )
    notes = body.get("reviewer_notes")

    # Ensure a routing row exists (compute the automatic decision first).
    from app.extraction.service import _read_sheet_text, _route_sheet_with_text_quality_gate

    result = _route_sheet_with_text_quality_gate(module, sheet, _read_sheet_text(sheet))
    upsert_routing_decision(
        project_id=project_id, sheet_id=sheet_id, trade_code=trade_code,
        extraction_run_id=None, eligibility=result.eligibility.value,
        reason=result.reason, automatic=True,
    )
    decision = set_manual_override(
        project_id, trade_code, sheet_id, manual_override=override, reviewer_notes=notes
    )
    return {
        "sheet_id": str(sheet_id),
        "trade_code": trade_code,
        "automatic_eligibility": decision["eligibility"],
        "manual_override": decision["manual_override"],
        "effective_status": decision["manual_override"] or decision["eligibility"],
        "reviewer_notes": decision["reviewer_notes"],
    }


# ---------------------------------------------------------------------------
# Extraction runs
# ---------------------------------------------------------------------------
@extraction_router.post(
    "/{project_id}/trades/{trade_code}/extractions",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_extraction(
    project_id: UUID,
    trade_code: str,
    background: BackgroundTasks,
    body: ExtractionRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    module = _require_trade(trade_code, enabled=True)
    request = body or ExtractionRequest()

    # Deterministic PDF processing must be complete (at least one sheet).
    if count_sheets(project_id) == 0:
        raise HTTPException(
            status_code=409,
            detail="Project has no processed sheets; run processing first",
        )

    if request.selected_sheet_ids:
        for sid in request.selected_sheet_ids:
            if get_sheet(project_id, sid) is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Selected sheet {sid} does not belong to this project",
                )

    use_live = bool(request.use_live_provider and settings.enable_live_extraction)
    provider = "openai" if use_live else settings.extraction_provider
    model = settings.openai_model if provider == "openai" else provider

    outcome, run = claim_extraction_run(
        project_id=project_id, trade_code=trade_code, provider=provider, model=model,
        prompt_version=module.get_prompt_version("scope_extractor"),
        provider_schema_version=PROVIDER_SCHEMA_VERSION,
        trade_schema_version=module.schema_version,
        force=request.force, dry_run=request.dry_run,
    )

    if outcome == "active":
        return _run_public(run, message="Extraction already in progress")
    if outcome == "exists_completed":
        raise HTTPException(
            status_code=409,
            detail="Extraction already completed for this trade; pass force=true",
        )

    run_id = UUID(run["id"])
    if settings.extraction_inline:
        run_extraction(project_id, trade_code, run_id)
        run = get_run(project_id, run_id)
    else:
        background.add_task(run_extraction, project_id, trade_code, run_id)

    return _run_public(run, message="Extraction started")


@extraction_router.get("/{project_id}/trades/{trade_code}/extractions/{run_id}")
def get_extraction_status(
    project_id: UUID,
    trade_code: str,
    run_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    run = get_run(project_id, run_id)
    if run is None or run["trade_code"] != trade_code:
        raise HTTPException(status_code=404, detail="Extraction run not found")
    return _run_public(run)


@extraction_router.get("/{project_id}/trades/{trade_code}/extractions")
def list_extraction_runs(
    project_id: UUID,
    trade_code: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    _require_trade(trade_code)
    rows, total = list_runs(project_id, trade_code, limit=limit, offset=offset)
    return {"items": [_run_public(r) for r in rows], "total": total,
            "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Scope items
# ---------------------------------------------------------------------------
@extraction_router.get("/{project_id}/scope-items")
def list_project_scope_items(
    project_id: UUID,
    trade_code: str | None = None,
    extraction_run_id: UUID | None = None,
    category: str | None = None,
    review_status: str | None = None,
    conflict_severity: str | None = None,
    sheet_id: UUID | None = None,
    missing_quantity: bool = False,
    requires_review: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    filters = {
        "trade_code": trade_code, "extraction_run_id": extraction_run_id,
        "category_code": category, "review_status": review_status,
        "conflict_severity": conflict_severity, "sheet_id": sheet_id,
        "missing_quantity": missing_quantity, "requires_review": requires_review,
    }
    rows, total = list_scope_items(project_id, filters=filters, limit=limit, offset=offset)
    return {"items": [_scope_summary(r) for r in rows], "total": total,
            "limit": limit, "offset": offset}


@extraction_router.get("/{project_id}/scope-items/{item_id}")
def get_project_scope_item(
    project_id: UUID,
    item_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    item = get_scope_item(project_id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scope item not found")
    return _scope_detail(item)


@extraction_router.patch("/{project_id}/scope-items/{item_id}")
def correct_project_scope_item(
    project_id: UUID,
    item_id: UUID,
    body: CorrectionRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    try:
        item = correct_item(project_id, item_id, body)
    except ReviewError as exc:
        raise _review_http(exc)
    return _scope_detail(item)


@extraction_router.post("/{project_id}/scope-items/{item_id}/approve")
def approve_project_scope_item(
    project_id: UUID,
    item_id: UUID,
    body: ApprovalRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    request = body or ApprovalRequest()
    try:
        return approve_item(project_id, item_id, reviewer_id=request.reviewer_id,
                            reviewer_notes=request.reviewer_notes)
    except ReviewError as exc:
        raise _review_http(exc)


@extraction_router.post("/{project_id}/scope-items/{item_id}/reject")
def reject_project_scope_item(
    project_id: UUID,
    item_id: UUID,
    body: RejectionRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    try:
        item = reject_item(project_id, item_id, reason=body.reason,
                           reviewer_id=body.reviewer_id)
    except ReviewError as exc:
        raise _review_http(exc)
    return _scope_detail(item)


@extraction_router.post("/{project_id}/scope-items/{item_id}/recalculate")
def recalculate_project_scope_item(
    project_id: UUID,
    item_id: UUID,
    body: RecalculateRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    try:
        item = recalculate_item(project_id, item_id, formula_id=body.formula_id,
                                inputs=body.inputs, reviewer_id=body.reviewer_id)
    except ReviewError as exc:
        raise _review_http(exc)
    return _scope_detail(item)


# ---------------------------------------------------------------------------
# Response shaping (no filesystem paths)
# ---------------------------------------------------------------------------
def _run_public(run: dict[str, Any], *, message: str | None = None) -> dict[str, Any]:
    out = {
        "run_id": run.get("id"),
        "project_id": run.get("project_id"),
        "trade_code": run.get("trade_code"),
        "status": run.get("status"),
        "provider": run.get("provider"),
        "model_identifier": run.get("model_identifier"),
        "prompt_version": run.get("prompt_version"),
        "attempt": run.get("attempt"),
        "dry_run": bool(run.get("dry_run")),
        "input_sheet_count": run.get("input_sheet_count"),
        "processed_sheet_count": run.get("processed_sheet_count"),
        "blocked_sheet_count": run.get("blocked_sheet_count"),
        "candidate_count": run.get("candidate_count"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "error_code": run.get("error_code"),
        "error_message": run.get("error_message"),
    }
    if message:
        out["message"] = message
    return out


def _scope_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "trade_code": item["trade_code"],
        "category_code": item["category_code"],
        "description": item["description"],
        "location": item.get("location"),
        "quantity": item.get("quantity"),
        "unit": item.get("unit"),
        "quantity_basis": item.get("quantity_basis"),
        "review_status": item.get("review_status"),
        "conflict_status": item.get("conflict_status"),
        "extraction_run_id": item.get("extraction_run_id"),
    }


def _scope_detail(item: dict[str, Any]) -> dict[str, Any]:
    project_id = UUID(item["project_id"])
    item_id = UUID(item["id"])
    evidence = list_evidence(item_id)
    for e in evidence:  # defensive: never expose an absolute filesystem path
        ref = e.get("source_artifact_ref")
        if isinstance(ref, str) and ref.startswith("/"):
            e["source_artifact_ref"] = None
    return {
        "scope_item": _scope_summary(item) | {
            "trade_module_version": item["trade_module_version"],
            "trade_schema_version": item["trade_schema_version"],
            "material_or_substrate": item.get("material_or_substrate"),
            "extraction_confidence": item.get("extraction_confidence"),
            "blocking_issues": item.get("blocking_issues") or [],
            "assumptions": item.get("assumptions") or [],
            "exclusions": item.get("exclusions") or [],
            "calculation_id": item.get("calculation_id"),
            "calculation_version": item.get("calculation_version"),
            "approved_at": item.get("approved_at"),
            "reviewer_notes": item.get("reviewer_notes"),
        },
        "trade_data": item.get("trade_data") or {},
        "original_provider_candidate": item.get("original_provider_candidate") or {},
        "evidence": evidence,
        "quantity_derivation": get_latest_derivation(project_id, item_id),
        "conflicts": list_conflicts(project_id, item_id),
        "review_history": list_review_events(project_id, item_id),
    }


def _review_http(exc: ReviewError) -> HTTPException:
    code_map = {
        "not_found": 404, "unknown_trade": 404, "reason_required": 422,
        "invalid_trade_data": 422, "invalid_inputs": 422,
        "unsupported_formula": 400,
    }
    return HTTPException(status_code=code_map.get(exc.code, 400), detail=exc.message)
