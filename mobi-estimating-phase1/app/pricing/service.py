"""Pricing orchestration: mapping, snapshot building, pricing, versioning, review.

Only **approved** scope items with trusted evidence are priced. Repricing creates a
new immutable estimate version; historical versions reprice from their stored
snapshot independent of the live cost book. No AI is involved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app import pricing_db
from app.extraction_db import get_scope_item, list_evidence, list_scope_items
from app.pricing.adjustments import apply_adjustments, compute_indirects
from app.pricing.engine import (
    PRICING_ENGINE_VERSION,
    ROUNDING_POLICY,
    price_snapshot,
)
from app.pricing.rollups import build_rollup
from app.pricing.schemas import EstimateVersionStatus, ExceptionSeverity
from app.pricing.snapshots import snapshot_hash, snapshot_json
from app.trades.registry import trade_registry


class PricingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
def _candidate_assembly(scope: dict, cost_book_version_id: UUID) -> tuple[str | None, str]:
    """Deterministic mapping. Returns (assembly_code|None, status)."""
    code = scope["trade_code"]
    if not trade_registry.is_registered(code):
        return None, "unknown_trade"
    module = trade_registry.get(code)
    candidates = module.map_scope_to_assembly(
        scope["category_code"], scope.get("trade_data") or {})
    if not candidates:
        return None, "no_mapping"
    if len(candidates) > 1:
        return None, "ambiguous"
    assembly_code = candidates[0]
    if pricing_db.get_assembly_by_code(cost_book_version_id, assembly_code) is None:
        return None, "assembly_not_in_version"
    return assembly_code, "mapped"


def _approved_scope(project_id: UUID, selection: dict[str, Any]) -> list[dict]:
    filters = {"review_status": "approved"}
    if selection.get("trade_code"):
        filters["trade_code"] = selection["trade_code"]
    items, _ = list_scope_items(project_id, filters=filters, limit=100000, offset=0)
    selected_ids = selection.get("scope_item_ids")
    if selected_ids:
        ids = {str(s) for s in selected_ids}
        items = [i for i in items if i["id"] in ids]
    return items


def _scope_for_pricing(project_id: UUID, version_id: UUID,
                       selection: dict[str, Any], *, auto_map: bool) -> list[dict]:
    scope_rows: list[dict] = []
    for item in _approved_scope(project_id, selection):
        mapping = pricing_db.get_mapping(project_id, UUID(item["id"]))
        assembly_code = mapping["assembly_code"] if mapping else None
        if assembly_code is None and auto_map:
            candidate, status = _candidate_assembly(item, version_id)
            if candidate is not None:
                pricing_db.upsert_mapping(project_id, UUID(item["id"]), {
                    "assembly_code": candidate, "trade_code": item["trade_code"],
                    "scope_category": item["category_code"],
                    "trade_schema_version": item.get("trade_schema_version"),
                    "confirmed_by": "auto_deterministic"})
                assembly_code = candidate
        evidence = [
            {
                "verified_sheet_number": e["verified_sheet_number"],
                "pdf_page_number": e["pdf_page_number"],
                "evidence_type": e["evidence_type"],
                # Preserve provenance used by customer-delivery safety gates.
                # Without this, export/proposal locks only failed closed because
                # the evidence source key was missing; test-only artifact refs
                # must remain visible to the gate instead of being projected out.
                "source_artifact_ref": e.get("source_artifact_ref"),
                "requires_human_verification": e.get("requires_human_verification"),
                # Proposal/export delivery locks require every evidence row to
                # carry its own scope lineage. Preserve the row value instead of
                # fabricating it from the enclosing item so missing/mismatched
                # lineage fails closed downstream.
                "scope_item_id": e.get("scope_item_id"),
            }
            for e in list_evidence(project_id, UUID(item["id"]))
        ]
        scope_rows.append({
            "id": item["id"], "trade_code": item["trade_code"],
            "category_code": item["category_code"], "description": item["description"],
            "location": item.get("location"), "quantity": item.get("quantity"),
            "unit": item.get("unit"), "assembly_code": assembly_code,
            "trade_data": item.get("trade_data") or {}, "evidence": evidence,
        })
    return scope_rows


# ---------------------------------------------------------------------------
# Preview (no estimate version created)
# ---------------------------------------------------------------------------
def preview(project_id: UUID, cost_book_version_id: UUID,
            selection: dict[str, Any]) -> dict[str, Any]:
    version = pricing_db.get_version(cost_book_version_id)
    if version is None:
        raise PricingError("unknown_version", "Cost-book version not found")
    if version["status"] != "published":
        raise PricingError("version_not_published",
                           "Pricing requires a published cost-book version")
    considered, missing_mappings, ambiguous, proposed = [], [], [], []
    for item in _approved_scope(project_id, selection):
        considered.append(item["id"])
        existing = pricing_db.get_mapping(project_id, UUID(item["id"]))
        if existing:
            proposed.append({"scope_item_id": item["id"],
                             "assembly_code": existing["assembly_code"],
                             "source": existing.get("confirmed_by")})
            continue
        candidate, status = _candidate_assembly(item, cost_book_version_id)
        if status == "mapped":
            proposed.append({"scope_item_id": item["id"], "assembly_code": candidate,
                             "source": "deterministic"})
        elif status == "ambiguous":
            ambiguous.append(item["id"])
        else:
            missing_mappings.append({"scope_item_id": item["id"], "reason": status})

    # Dry-run pricing to surface missing/stale rates without persisting.
    scope = _scope_for_pricing(project_id, cost_book_version_id, selection, auto_map=False)
    rates = pricing_db.build_rate_tables(cost_book_version_id)
    snapshot = _assemble_snapshot(cost_book_version_id, version, scope, rates, [], [], {})
    result = price_snapshot(snapshot)
    exceptions = [e.as_dict() for e in result.all_exceptions()]
    return {
        "scope_items_considered": considered,
        "scope_items_excluded": [],  # only approved items are considered
        "proposed_mappings": proposed,
        "missing_mappings": missing_mappings,
        "ambiguous_mappings": ambiguous,
        "exceptions": exceptions,
        "blocking_exceptions": [e for e in exceptions
                                if e["severity"] == ExceptionSeverity.BLOCKING.value],
        "estimated_api_cost": "0.00",  # pricing is local Python
        "estimate_version_created": False,
    }


# ---------------------------------------------------------------------------
# Snapshot + pricing
# ---------------------------------------------------------------------------
def _assemble_snapshot(version_id: UUID, cbv: dict, scope: list[dict],
                       rates: dict, indirects: list, adjustments: list,
                       config: dict) -> dict[str, Any]:
    return {
        "cost_book_version_id": str(version_id),
        "currency": config.get("currency", "USD"),
        "pricing_date": cbv.get("pricing_date"),
        "stale_policy": config.get("stale_policy", "warn"),
        "unverified_policy": config.get("unverified_policy", "warn"),
        "pricing_engine_version": PRICING_ENGINE_VERSION,
        "rounding_policy": ROUNDING_POLICY,
        "scope_items": scope,
        "indirects": indirects,
        "adjustments": adjustments,
        **rates,
    }


def price_version(project_id: UUID, estimate_id: UUID, version_id: str) -> dict[str, Any]:
    version = pricing_db.get_estimate_version(version_id)
    if version is None or version["estimate_id"] != str(estimate_id):
        raise PricingError("not_found", "Estimate version not found")
    if version["status"] == EstimateVersionStatus.APPROVED.value:
        raise PricingError("immutable", "Approved estimate versions are immutable")

    cbv = pricing_db.get_version(UUID(version["cost_book_version_id"]))
    if cbv is None or cbv["status"] != "published":
        raise PricingError("version_not_published",
                           "Estimate must reference a published cost-book version")

    pricing_db.update_version(version_id, {"status": EstimateVersionStatus.PRICING.value})
    config = version.get("config") or {}
    selection = {"trade_code": config.get("trade_code"),
                 "scope_item_ids": config.get("scope_item_ids")}
    indirects = pricing_db.get_indirects(version_id)
    adjustments = pricing_db.get_adjustments(version_id)

    scope = _scope_for_pricing(project_id, UUID(version["cost_book_version_id"]),
                               selection, auto_map=True)
    rates = pricing_db.build_rate_tables(UUID(version["cost_book_version_id"]))
    snapshot = _assemble_snapshot(UUID(version["cost_book_version_id"]), cbv, scope,
                                  rates, indirects, adjustments, config)
    snap_json = snapshot_json(snapshot)
    snap_hash = snapshot_hash(snapshot)
    pricing_db.save_snapshot(version_id, snap_json, snap_hash)

    result = price_snapshot(snapshot)
    lines = [li.as_dict() for li in result.line_items]
    pricing_db.replace_line_items(version_id, project_id, lines)

    rollup, all_exceptions = _compute_rollup(lines, indirects, adjustments,
                                             [e.as_dict() for e in result.exceptions])
    blocking = any(e.get("severity") == ExceptionSeverity.BLOCKING.value
                   for e in all_exceptions)
    status = (EstimateVersionStatus.NEEDS_REVIEW.value if blocking
              else EstimateVersionStatus.PRICED.value)
    pricing_db.update_version(version_id, {
        "status": status, "snapshot_hash": snap_hash,
        "pricing_engine_version": PRICING_ENGINE_VERSION, "rounding_policy": ROUNDING_POLICY,
        "calculation_at": _now(), "exceptions": all_exceptions})
    return {"version": pricing_db.get_estimate_version(version_id), "rollup": rollup,
            "exceptions": all_exceptions}


def _compute_rollup(lines: list[dict], indirects: list, adjustments: list,
                    engine_exceptions: list[dict]) -> tuple[dict, list[dict]]:
    direct_by_category = {
        "labor": sum((Decimal(li["labor_cost"]) for li in lines), Decimal("0")),
        "material": sum((Decimal(li["material_cost"]) for li in lines), Decimal("0")),
        "equipment": sum((Decimal(li["equipment_cost"]) for li in lines), Decimal("0")),
        "subcontract": sum((Decimal(li["subcontract_cost"]) for li in lines), Decimal("0")),
        "other_direct": sum((Decimal(li["other_direct_cost"]) for li in lines), Decimal("0")),
    }
    ind_applied, ind_total, ind_exc = compute_indirects(indirects, direct_by_category)
    adj_applied, adj_totals, adj_exc = apply_adjustments(direct_by_category, ind_total, adjustments)
    all_exceptions = list(engine_exceptions) + ind_exc + adj_exc
    for li in lines:
        all_exceptions.extend(li.get("exceptions", []))
    rollup = build_rollup(lines, indirect_total=ind_total, indirects_applied=ind_applied,
                          adjustment_totals=adj_totals, adjustments_applied=adj_applied,
                          engine_exceptions=engine_exceptions)
    return rollup, all_exceptions


def compute_estimate_rollup(version_id: str) -> dict[str, Any]:
    lines = pricing_db.get_line_items(version_id)
    indirects = pricing_db.get_indirects(version_id)
    adjustments = pricing_db.get_adjustments(version_id)
    version = pricing_db.get_estimate_version(version_id)
    engine_exc = [e for e in (version.get("exceptions") or [])
                  if not e.get("scope_item_id")]  # version-level only
    rollup, _ = _compute_rollup(lines, indirects, adjustments, [])
    return rollup


# ---------------------------------------------------------------------------
# Reprice / approve / override
# ---------------------------------------------------------------------------
def reprice(project_id: UUID, estimate_id: UUID) -> dict[str, Any]:
    estimate = pricing_db.get_estimate(project_id, estimate_id)
    if estimate is None:
        raise PricingError("not_found", "Estimate not found")
    versions = pricing_db.list_estimate_versions(estimate_id)
    if not versions:
        raise PricingError("no_version", "Estimate has no version to reprice")
    latest = versions[-1]
    new_version = pricing_db.create_estimate_version(estimate_id, project_id, {
        "version_number": pricing_db.next_version_number(estimate_id),
        "cost_book_version_id": latest["cost_book_version_id"],
        "pricing_date": latest["pricing_date"], "currency": latest["currency"],
        "markup_method": latest["markup_method"],
        "inclusions": _loads(latest.get("inclusions")),
        "exclusions": _loads(latest.get("exclusions")),
        "assumptions": _loads(latest.get("assumptions")),
        "clarifications": _loads(latest.get("clarifications")),
        "config": _loads(latest.get("config")) or {},
        "indirects": pricing_db.get_indirects(latest["id"]),
        "adjustments": pricing_db.get_adjustments(latest["id"]),
    })
    priced = price_version(project_id, estimate_id, new_version["id"])
    # Supersede the previous version (it stays readable).
    if latest["status"] != EstimateVersionStatus.APPROVED.value:
        pricing_db.update_version(latest["id"], {
            "status": EstimateVersionStatus.SUPERSEDED.value, "superseded_at": _now()})
    return priced


def approve_version(project_id: UUID, estimate_id: UUID, version_id: str,
                    *, reviewer_id: str, notes: str) -> dict[str, Any]:
    version = pricing_db.get_estimate_version(version_id)
    if version is None or version["estimate_id"] != str(estimate_id):
        raise PricingError("not_found", "Estimate version not found")
    exceptions = version.get("exceptions") or []
    blocking = [e for e in exceptions if e.get("severity") == ExceptionSeverity.BLOCKING.value]
    # Also re-scan stored line items for blocking exceptions.
    for li in pricing_db.get_line_items(version_id):
        blocking.extend([e for e in li.get("exceptions", [])
                         if e.get("severity") == ExceptionSeverity.BLOCKING.value])
    if blocking:
        raise PricingError("blocking_exceptions",
                           f"Cannot approve: {len(blocking)} blocking exception(s) remain")
    if version["status"] not in (EstimateVersionStatus.PRICED.value,):
        raise PricingError("not_priced", "Only a fully priced version can be approved")
    pricing_db.update_version(version_id, {
        "status": EstimateVersionStatus.APPROVED.value, "approved_at": _now()})
    pricing_db.append_estimate_review(version_id, project_id, {
        "action": "approve", "previous_state": version["status"],
        "new_state": EstimateVersionStatus.APPROVED.value, "reviewer_id": reviewer_id,
        "notes": notes})
    return pricing_db.get_estimate_version(version_id)


def override_line_item(project_id: UUID, version_id: str, line_item_id: UUID,
                       *, field: str, new_value: Decimal, reason: str,
                       reviewer_id: str) -> dict[str, Any]:
    version = pricing_db.get_estimate_version(version_id)
    if version is None:
        raise PricingError("not_found", "Estimate version not found")
    if version["status"] == EstimateVersionStatus.APPROVED.value:
        raise PricingError("immutable", "Approved versions are immutable")
    line = pricing_db.get_line_item(version_id, line_item_id)
    if line is None:
        raise PricingError("not_found", "Line item not found")
    allowed = {"labor_cost", "material_cost", "equipment_cost", "subcontract_cost",
               "other_direct_cost"}
    if field not in allowed:
        raise PricingError("invalid_field", f"Field '{field}' cannot be overridden")
    original = line.get(field)
    overrides = line.get("overrides", [])
    overrides.append({"field": field, "original_value": original,
                      "new_value": str(new_value), "reason": reason,
                      "reviewer_id": reviewer_id, "at": _now()})
    buckets = {k: Decimal(line[k]) for k in allowed}
    buckets[field] = new_value
    direct_total = sum(buckets.values(), Decimal("0"))
    pricing_db.update_line_item(line_item_id, {
        field: str(new_value), "direct_cost_total": str(direct_total),
        "overrides": overrides})
    pricing_db.append_estimate_review(version_id, project_id, {
        "action": "override", "previous_state": str(original),
        "new_state": str(new_value), "reviewer_id": reviewer_id,
        "notes": f"{field}: {reason}"})
    return pricing_db.get_line_item(version_id, line_item_id)


def _loads(value: Any) -> Any:
    import json
    if value in (None, ""):
        return [] if value == "" else value
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value
