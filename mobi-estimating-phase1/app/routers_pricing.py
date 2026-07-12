"""Phase 4 API: cost books, cost inputs, assemblies, mappings, pricing preview,
estimates, pricing, rollups, exceptions, approval, overrides, exports, CSV import.

All routes under ``/api/v1``. No filesystem paths or secrets are exposed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from app import pricing_db
from app.capability_registry import classify_supported_scope, evaluate_delivery_lock
from app.extraction_db import get_scope_item
from app.pricing import service
from app.pricing.exports import estimate_csv, estimate_json
from app.pricing.imports import CsvImportError, parse_csv
from app.pricing.schemas import (
    AssemblyCreate,
    AssemblyMappingRequest,
    ApproveRequest,
    CostBookCreate,
    CostBookVersionCreate,
    CostSourceCreate,
    CrewCreate,
    EquipmentRateCreate,
    EstimateCreate,
    LaborRateCreate,
    LineItemOverride,
    MaterialRateCreate,
    OtherDirectCostCreate,
    ProductionRateCreate,
    SubcontractQuoteCreate,
)
from app.pricing_db import ImmutableError
from app.router_tenant_guard import require_project_for_request

cost_books_router = APIRouter(prefix="/cost-books", tags=["pricing"])
pricing_router = APIRouter(prefix="/projects", tags=["pricing"])

_TEST_ONLY_METADATA_KEYS = (
    "internal_testing_only",
    "test_only",
    "testing_only",
    "fixture_only",
    "synthetic_only",
)


def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> dict:
    return require_project_for_request(project_id, tenant_id=tenant_id, company_id=company_id)


def _require_cost_book(cost_book_id: UUID) -> dict:
    book = pricing_db.get_cost_book(cost_book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Cost book not found")
    return book


def _require_version(cost_book_id: UUID, version_id: UUID) -> dict:
    version = pricing_db.get_version(version_id)
    if version is None or version["cost_book_id"] != str(cost_book_id):
        raise HTTPException(status_code=404, detail="Cost-book version not found")
    return version


def _draft_guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ImmutableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Cost books + versions
# ---------------------------------------------------------------------------
@cost_books_router.post("", status_code=201)
def create_cost_book(body: CostBookCreate) -> dict[str, Any]:
    return pricing_db.create_cost_book(body.model_dump())


@cost_books_router.get("")
def list_cost_books(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = pricing_db.list_cost_books(limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@cost_books_router.get("/{cost_book_id}")
def get_cost_book(cost_book_id: UUID):
    return _require_cost_book(cost_book_id)


@cost_books_router.post("/{cost_book_id}/versions", status_code=201)
def create_version(cost_book_id: UUID, body: CostBookVersionCreate):
    _require_cost_book(cost_book_id)
    return pricing_db.create_version(cost_book_id, body.model_dump())


@cost_books_router.get("/{cost_book_id}/versions")
def list_versions(cost_book_id: UUID):
    _require_cost_book(cost_book_id)
    return {"items": pricing_db.list_versions(cost_book_id)}


@cost_books_router.get("/{cost_book_id}/versions/{version_id}")
def get_version(cost_book_id: UUID, version_id: UUID):
    return _require_version(cost_book_id, version_id)


def _validate_version_for_publish(version_id: UUID) -> list[str]:
    errors: list[str] = []
    assemblies = pricing_db.list_assemblies(version_id)
    seen: set[str] = set()
    for asm in assemblies:
        if not asm.get("components"):
            errors.append(f"assembly '{asm['assembly_code']}' has no components")
        if asm["assembly_code"] in seen:
            errors.append(f"duplicate assembly code '{asm['assembly_code']}'")
        seen.add(asm["assembly_code"])
        for comp in asm.get("components", []):
            if not comp.get("cost_item_ref"):
                errors.append(f"assembly '{asm['assembly_code']}' has a component "
                              "with no cost_item_ref")
    return errors


@cost_books_router.post("/{cost_book_id}/versions/{version_id}/publish")
def publish_version(cost_book_id: UUID, version_id: UUID):
    _require_version(cost_book_id, version_id)
    errors = _validate_version_for_publish(version_id)
    try:
        return pricing_db.publish_version(version_id, errors=errors)
    except ImmutableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@cost_books_router.post("/{cost_book_id}/versions/{version_id}/archive")
def archive_version(cost_book_id: UUID, version_id: UUID):
    _require_version(cost_book_id, version_id)
    return pricing_db.archive_version(version_id)


# ---------------------------------------------------------------------------
# Cost inputs (draft-only mutation)
# ---------------------------------------------------------------------------
_INPUT_ROUTES = [
    ("sources", CostSourceCreate, pricing_db.add_cost_source, "cost_sources"),
    ("labor-rates", LaborRateCreate, pricing_db.add_labor_rate, "labor_rates"),
    ("crews", CrewCreate, pricing_db.add_crew, "crews"),
    ("production-rates", ProductionRateCreate, pricing_db.add_production_rate, "production_rates"),
    ("material-rates", MaterialRateCreate, pricing_db.add_material_rate, "material_rates"),
    ("equipment-rates", EquipmentRateCreate, pricing_db.add_equipment_rate, "equipment_rates"),
    ("subcontract-quotes", SubcontractQuoteCreate, pricing_db.add_subcontract_quote, "subcontract_quotes"),
    ("other-direct-costs", OtherDirectCostCreate, pricing_db.add_other_direct_cost, "other_direct_costs"),
]


def _make_input_routes() -> None:
    # Bind ``model``/``adder``/``table`` per-iteration via default args. The body is
    # typed ``dict`` (PEP 563 strings prevent dynamic Pydantic annotations) and is
    # validated explicitly with the bound create model, preserving extra="forbid".
    for path, model, adder, table in _INPUT_ROUTES:
        def _create(cost_book_id: UUID, version_id: UUID, body: dict,
                    _model=model, _adder=adder):
            _require_version(cost_book_id, version_id)
            try:
                validated = _model.model_validate(body)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=exc.errors()) from exc
            return _draft_guard(_adder, version_id, validated.model_dump())

        def _list(cost_book_id: UUID, version_id: UUID, _table=table):
            _require_version(cost_book_id, version_id)
            return {"items": pricing_db.list_inputs(_table, version_id)}

        cost_books_router.add_api_route(
            f"/{{cost_book_id}}/versions/{{version_id}}/{path}", _create,
            methods=["POST"], status_code=201, name=f"create_{table}")
        cost_books_router.add_api_route(
            f"/{{cost_book_id}}/versions/{{version_id}}/{path}", _list,
            methods=["GET"], name=f"list_{table}")


_make_input_routes()


# ---------------------------------------------------------------------------
# Assemblies
# ---------------------------------------------------------------------------
@cost_books_router.post("/{cost_book_id}/versions/{version_id}/assemblies", status_code=201)
def create_assembly(cost_book_id: UUID, version_id: UUID, body: AssemblyCreate):
    _require_version(cost_book_id, version_id)
    return _draft_guard(pricing_db.add_assembly, version_id, body.model_dump())


@cost_books_router.get("/{cost_book_id}/versions/{version_id}/assemblies")
def list_assemblies(cost_book_id: UUID, version_id: UUID):
    _require_version(cost_book_id, version_id)
    return {"items": pricing_db.list_assemblies(version_id)}


@cost_books_router.get("/{cost_book_id}/versions/{version_id}/assemblies/{assembly_id}")
def get_assembly(cost_book_id: UUID, version_id: UUID, assembly_id: str):
    asm = pricing_db.get_assembly(assembly_id)
    if asm is None or asm["version_id"] != str(version_id):
        raise HTTPException(status_code=404, detail="Assembly not found")
    return asm


@cost_books_router.post("/{cost_book_id}/versions/{version_id}/assemblies/{assembly_id}/validate")
def validate_assembly(cost_book_id: UUID, version_id: UUID, assembly_id: str):
    asm = pricing_db.get_assembly(assembly_id)
    if asm is None or asm["version_id"] != str(version_id):
        raise HTTPException(status_code=404, detail="Assembly not found")
    errors: list[str] = []
    if not asm.get("components"):
        errors.append("assembly has no components")
    seen = set()
    for comp in asm.get("components", []):
        key = (comp["component_type"], comp["cost_item_ref"], comp.get("sequence"))
        if key in seen:
            errors.append(f"duplicate component {key}")
        seen.add(key)
        if not comp.get("cost_item_ref"):
            errors.append("component missing cost_item_ref")
    return {"valid": not errors, "errors": errors}


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------
@cost_books_router.post("/{cost_book_id}/versions/{version_id}/imports/{kind}/preview")
async def csv_preview(cost_book_id: UUID, version_id: UUID, kind: str, request: Request):
    _require_version(cost_book_id, version_id)
    content = (await request.body()).decode("utf-8")
    try:
        return parse_csv(kind, content)
    except CsvImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@cost_books_router.post("/{cost_book_id}/versions/{version_id}/imports/{kind}/commit")
async def csv_commit(cost_book_id: UUID, version_id: UUID, kind: str, request: Request):
    _require_version(cost_book_id, version_id)
    content = (await request.body()).decode("utf-8")
    try:
        parsed = parse_csv(kind, content)
    except CsvImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not parsed["valid"]:
        raise HTTPException(status_code=422, detail={"errors": parsed["errors"]})
    try:
        inserted = pricing_db.commit_import(version_id, kind, parsed["rows"])
    except ImmutableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"imported": inserted, "kind": kind}


# ---------------------------------------------------------------------------
# Assembly mappings
# ---------------------------------------------------------------------------
@pricing_router.post("/{project_id}/scope-items/{scope_item_id}/assembly-mapping")
def set_mapping(
    project_id: UUID,
    scope_item_id: UUID,
    body: AssemblyMappingRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    if get_scope_item(project_id, scope_item_id) is None:
        raise HTTPException(status_code=404, detail="Scope item not found")
    return pricing_db.upsert_mapping(project_id, scope_item_id, {
        "assembly_code": body.assembly_code, "confirmed_by": body.reviewer_id})


@pricing_router.get("/{project_id}/scope-items/{scope_item_id}/assembly-mapping")
def get_mapping(
    project_id: UUID,
    scope_item_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    mapping = pricing_db.get_mapping(project_id, scope_item_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="No mapping for scope item")
    return mapping


# ---------------------------------------------------------------------------
# Pricing preview + estimates
# ---------------------------------------------------------------------------
@pricing_router.post("/{project_id}/pricing/preview")
def pricing_preview(
    project_id: UUID,
    body: dict[str, Any],
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    cbv = body.get("cost_book_version_id")
    if not cbv:
        raise HTTPException(status_code=422, detail="cost_book_version_id is required")
    selection = {"trade_code": body.get("trade_code"),
                 "scope_item_ids": body.get("scope_item_ids")}
    try:
        return service.preview(project_id, UUID(cbv), selection)
    except service.PricingError as exc:
        raise _pricing_http(exc)


@pricing_router.post("/{project_id}/estimates", status_code=201)
def create_estimate(
    project_id: UUID,
    body: EstimateCreate,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    cbv = pricing_db.get_version(body.cost_book_version_id)
    if cbv is None:
        raise HTTPException(status_code=404, detail="Cost-book version not found")
    if cbv["status"] != "published":
        raise HTTPException(status_code=409,
                            detail="Estimates require a published cost-book version")
    estimate = pricing_db.create_estimate(project_id, body.model_dump())
    version = pricing_db.create_estimate_version(UUID(estimate["id"]), project_id, {
        "version_number": 1, "cost_book_version_id": str(body.cost_book_version_id),
        "pricing_date": cbv["pricing_date"], "currency": body.currency,
        "markup_method": body.markup_method, "inclusions": body.inclusions,
        "exclusions": body.exclusions, "assumptions": body.assumptions,
        "clarifications": body.clarifications,
        "indirects": [i.model_dump() for i in body.indirects],
        "adjustments": [a.model_dump() for a in body.adjustments],
        "config": {"trade_code": (body.trade_codes or [None])[0] if body.trade_codes else None,
                   "scope_item_ids": [str(s) for s in body.scope_item_ids] if body.scope_item_ids else None,
                   "currency": body.currency},
    })
    return {"estimate": estimate, "version": version}


@pricing_router.get("/{project_id}/estimates")
def list_estimates(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    return {"items": pricing_db.list_estimates(project_id)}


@pricing_router.get("/{project_id}/estimates/{estimate_id}")
def get_estimate(
    project_id: UUID,
    estimate_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    estimate = pricing_db.get_estimate(project_id, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions")
def list_estimate_versions(
    project_id: UUID,
    estimate_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    if pricing_db.get_estimate(project_id, estimate_id) is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return {"items": pricing_db.list_estimate_versions(estimate_id)}


def _require_estimate_version(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    *,
    tenant_id: str | None,
    company_id: str | None,
) -> dict:
    _require_project(project_id, tenant_id=tenant_id, company_id=company_id)
    version = pricing_db.get_estimate_version(version_id)
    if (version is None or version["estimate_id"] != str(estimate_id)
            or version["project_id"] != str(project_id)):
        raise HTTPException(status_code=404, detail="Estimate version not found")
    return version


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}")
def get_estimate_version(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    return _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )


@pricing_router.post("/{project_id}/estimates/{estimate_id}/versions/{version_id}/price")
def price_estimate_version(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    try:
        return service.price_version(project_id, estimate_id, str(version_id))
    except service.PricingError as exc:
        raise _pricing_http(exc)


@pricing_router.post("/{project_id}/estimates/{estimate_id}/reprice")
def reprice_estimate(
    project_id: UUID,
    estimate_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_project(project_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id)
    if pricing_db.get_estimate(project_id, estimate_id) is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        return service.reprice(project_id, estimate_id)
    except service.PricingError as exc:
        raise _pricing_http(exc)


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/line-items")
def list_line_items(project_id: UUID, estimate_id: UUID, version_id: UUID,
                    limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0),
                    x_mobi_tenant_id: str | None = Header(default=None),
                    x_mobi_company_id: str | None = Header(default=None)):
    _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    lines = pricing_db.get_line_items(str(version_id))
    return {"items": lines[offset:offset + limit], "total": len(lines),
            "limit": limit, "offset": offset}


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/rollup")
def get_rollup(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    return service.compute_estimate_rollup(str(version_id))


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/exceptions")
def get_exceptions(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    version = _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    return {"exceptions": version.get("exceptions") or []}


def _enforce_pricing_export_delivery_lock(version: dict) -> None:
    """Fail closed before returning customer-facing estimate export files.

    Pricing JSON/CSV exports contain final-priced line items and rollups. They are
    therefore final-estimate exposure surfaces, not ordinary internal status APIs,
    and must stay locked until the same audit P0 requirements are satisfied:
    supported customer-delivery scope, complete evidence, required reviews,
    explicit owner approval, and real quantity/pricing lineage for every line.
    This P0 slice has no owner-approval persistence path, so exports remain
    intentionally closed by default.
    """
    lines = pricing_db.get_line_items(version["id"])
    scope_items = [
        {
            "id": line.get("scope_item_id"),
            "trade_code": line.get("trade_code"),
            "category_code": line.get("category_code"),
        }
        for line in lines
    ]
    supported_scope = classify_supported_scope(scope_items)
    delivery_sources: list[dict[str, Any]] = []
    for line in lines:
        for component in line.get("components") or []:
            if not isinstance(component, dict):
                delivery_sources.append({
                    "scope_item_id": line.get("scope_item_id"),
                    "kind": "estimate_line_component_source",
                    "source": None,
                })
                continue
            delivery_sources.append({
                "scope_item_id": line.get("scope_item_id"),
                "kind": "estimate_line_component_source",
                "source": component.get("source") or component.get("component_source"),
                "metadata": component.get("metadata"),
                "source_metadata": component.get("source_metadata"),
                "provenance_metadata": component.get("provenance_metadata"),
                "audit_metadata": component.get("audit_metadata"),
                **{key: component.get(key) for key in _TEST_ONLY_METADATA_KEYS},
            })
        if line.get("quantity") not in (None, ""):
            delivery_sources.append({
                "scope_item_id": line.get("scope_item_id"),
                "kind": "estimate_line_quantity_source",
                "source": line.get("quantity_source") or line.get("quantity_basis"),
                "metadata": line.get("metadata"),
                "source_metadata": line.get("source_metadata"),
                "provenance_metadata": line.get("provenance_metadata"),
                "audit_metadata": line.get("audit_metadata"),
                **{key: line.get(key) for key in _TEST_ONLY_METADATA_KEYS},
            })

    lock = evaluate_delivery_lock(
        evidence_complete=bool(lines) and all(bool(line.get("evidence")) for line in lines),
        required_reviews_complete=version.get("status") == "approved",
        owner_approval=None,
        delivery_sources=delivery_sources,
        supported_scope=supported_scope["supported_scope"],
        unsupported_scope=supported_scope,
        expected_scope_item_count=len(lines),
        expected_scope_item_ids=[line.get("scope_item_id") for line in lines],
    )
    if lock["delivery_unlocked"]:
        return
    reasons = "; ".join(lock.get("reasons") or ["Customer delivery lock is closed."])
    raise HTTPException(
        status_code=409,
        detail=f"Estimate export is locked by the final delivery gate: {reasons}",
    )


@pricing_router.post("/{project_id}/estimates/{estimate_id}/versions/{version_id}/approve")
def approve_version(project_id: UUID, estimate_id: UUID, version_id: UUID,
                    body: ApproveRequest | None = None,
                    x_mobi_tenant_id: str | None = Header(default=None),
                    x_mobi_company_id: str | None = Header(default=None)):
    _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    req = body or ApproveRequest()
    try:
        return service.approve_version(project_id, estimate_id, str(version_id),
                                       reviewer_id=req.reviewer_id, notes=req.notes)
    except service.PricingError as exc:
        raise _pricing_http(exc)


@pricing_router.post(
    "/{project_id}/estimates/{estimate_id}/versions/{version_id}/line-items/{line_item_id}/override")
def override_line(project_id: UUID, estimate_id: UUID, version_id: UUID,
                  line_item_id: UUID, body: LineItemOverride,
                  x_mobi_tenant_id: str | None = Header(default=None),
                  x_mobi_company_id: str | None = Header(default=None)):
    _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    try:
        return service.override_line_item(
            project_id, str(version_id), line_item_id, field=body.field,
            new_value=body.new_value, reason=body.reason, reviewer_id=body.reviewer_id)
    except service.PricingError as exc:
        raise _pricing_http(exc)


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/export.json")
def export_json(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    version = _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    _enforce_pricing_export_delivery_lock(version)
    lines = pricing_db.get_line_items(str(version_id))
    rollup = service.compute_estimate_rollup(str(version_id))
    return PlainTextResponse(
        estimate_json(version, lines, rollup, version.get("exceptions") or []),
        media_type="application/json")


@pricing_router.get("/{project_id}/estimates/{estimate_id}/versions/{version_id}/export.csv")
def export_csv(
    project_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
):
    version = _require_estimate_version(
        project_id, estimate_id, version_id, tenant_id=x_mobi_tenant_id, company_id=x_mobi_company_id
    )
    _enforce_pricing_export_delivery_lock(version)
    lines = pricing_db.get_line_items(str(version_id))
    return PlainTextResponse(estimate_csv(lines), media_type="text/csv")


def _pricing_http(exc: service.PricingError) -> HTTPException:
    code_map = {"not_found": 404, "unknown_version": 404, "no_version": 404,
                "immutable": 409, "version_not_published": 409,
                "blocking_exceptions": 409, "not_priced": 409, "invalid_field": 422}
    return HTTPException(status_code=code_map.get(exc.code, 400), detail=exc.message)
