"""Generic all-trade estimate draft bridge v1.

This module converts generic scope items with verified quantity/pricing basis
metadata into an internal draft estimate version and draft estimate line items.
It is intentionally not a final pricing engine, approval path, proposal issue
path, customer delivery path, or payment/billing action.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from app import pricing_db
from app.capability_registry import classify_delivery_sources, classify_supported_scope
from app.extraction_db import list_evidence, list_scope_items
from app.pricing.schemas import SourceType


class GenericEstimateBridgeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_decimal(value: Any, field_name: str) -> Decimal:
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GenericEstimateBridgeError("invalid_amount", f"{field_name} must be a valid number.") from exc
    if not dec.is_finite() or dec < 0:
        raise GenericEstimateBridgeError("invalid_amount", f"{field_name} must not be negative.")
    return dec


def _money(value: Decimal) -> str:
    try:
        return str(value.quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise GenericEstimateBridgeError(
            "invalid_amount",
            "amount is outside the supported money precision/range.",
        ) from exc


_DIRECT_BUCKETS = ("labor", "material", "equipment", "subcontract", "other_direct")
_INDIRECT_BUCKETS = ("overhead", "profit", "contingency", "markup")
_VALID_PRICING_METHODS: frozenset[str] = frozenset({"unit_rate_needed", "quote_based", "allowance"})


def _dict_or_empty(value: Any) -> dict[str, Any]:
    """Return mapping metadata only when it is actually an object.

    Delivery-lock metadata must fail closed on malformed containers. Coercing
    lists/strings into plausible dict-like values would either crash draft
    generation or make malformed evidence look absent-but-safe.
    """
    return value if isinstance(value, dict) else {}


def _zero_components(*, basis_type: Literal["unit_rate", "lump_sum", "allowance"], method: str) -> dict[str, Any]:
    return {
        "schema_version": "generic_cost_components_v1",
        "basis_type": basis_type,
        "pricing_method": method,
        "direct_costs": {bucket: "0.00" for bucket in _DIRECT_BUCKETS},
        "indirect_costs": {bucket: "0.00" for bucket in _INDIRECT_BUCKETS},
        "component_source": "default_generic_bucket",
        "customer_ready": False,
    }


def _normalise_components(basis: dict[str, Any], *, method: str, amount: Decimal) -> dict[str, Any]:
    basis_type: Literal["unit_rate", "lump_sum", "allowance"] = "unit_rate"
    if method == "quote_based":
        basis_type = "lump_sum"
    elif method == "allowance":
        basis_type = "allowance"
    default = _zero_components(basis_type=basis_type, method=method)
    supplied = basis.get("cost_components")
    if supplied is None:
        target_bucket = "subcontract" if method == "quote_based" else "other_direct"
        default["direct_costs"][target_bucket] = _money(amount)
        return default
    if not isinstance(supplied, dict):
        raise GenericEstimateBridgeError(
            "invalid_cost_components",
            "cost_components must be an object.",
        )

    direct: dict[str, str] = {}
    direct_total = Decimal("0")
    source_direct = supplied.get("direct_costs")
    if source_direct is not None and not isinstance(source_direct, dict):
        raise GenericEstimateBridgeError(
            "invalid_cost_components",
            "cost_components.direct_costs must be an object when supplied.",
        )
    if source_direct is None:
        source_direct = {}
    for bucket in _DIRECT_BUCKETS:
        value = _to_decimal(source_direct.get(bucket, "0"), f"direct_costs.{bucket}")
        direct[bucket] = _money(value)
        direct_total += value
    if direct_total != amount:
        raise GenericEstimateBridgeError(
            "cost_component_total_mismatch",
            "direct cost component total must equal pricing basis amount.",
        )
    indirect: dict[str, str] = {}
    source_indirect = supplied.get("indirect_costs")
    if source_indirect is not None and not isinstance(source_indirect, dict):
        raise GenericEstimateBridgeError(
            "invalid_cost_components",
            "cost_components.indirect_costs must be an object when supplied.",
        )
    if source_indirect is None:
        source_indirect = {}
    for bucket in _INDIRECT_BUCKETS:
        value = _to_decimal(source_indirect.get(bucket, "0"), f"indirect_costs.{bucket}")
        indirect[bucket] = _money(value)
    return {
        "schema_version": "generic_cost_components_v1",
        "basis_type": str(supplied.get("basis_type") or basis_type),
        "pricing_method": method,
        "direct_costs": direct,
        "indirect_costs": indirect,
        "component_source": str(supplied.get("component_source") or basis.get("source") or "verified_generic_input"),
        "customer_ready": False,
    }


def _multiplier_for_method(method: str, quantity: Decimal) -> Decimal:
    return quantity if method == "unit_rate_needed" else Decimal("1")


def _delivery_sources_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return quantity/pricing source records that would back an estimate line."""
    sources: list[dict[str, Any]] = []
    scope_item_id = item.get("id")
    trade_data = _dict_or_empty(item.get("trade_data"))
    raw_pricing_basis = trade_data.get("pricing_basis")
    pricing_basis = _dict_or_empty(raw_pricing_basis)
    if isinstance(raw_pricing_basis, dict):
        sources.append({
            "scope_item_id": scope_item_id,
            "kind": "pricing_basis",
            "source": pricing_basis.get("source"),
        })
        raw_cost_components = pricing_basis.get("cost_components")
        cost_components = _dict_or_empty(raw_cost_components)
        if isinstance(raw_cost_components, dict):
            sources.append({
                "scope_item_id": scope_item_id,
                "kind": "cost_component_source",
                "source": cost_components.get("component_source"),
            })
    raw_quantity_inputs = _dict_or_empty(item.get("raw_quantity_inputs"))
    verified_quantity = _dict_or_empty(raw_quantity_inputs.get("verified_quantity_input_v1"))
    if item.get("quantity") not in (None, ""):
        sources.append({
            "scope_item_id": scope_item_id,
            "kind": "quantity_input",
            "source": verified_quantity.get("source"),
        })
    return sources


def _missing_blockers(item: dict[str, Any]) -> list[dict[str, Any]]:
    trade_data = _dict_or_empty(item.get("trade_data"))
    method = str(trade_data.get("pricing_method") or "")
    blockers: list[dict[str, Any]] = []
    if item.get("quantity") in (None, ""):
        blockers.append({"code": "missing_quantity", "message": "Scope item has no verified quantity."})
    if not method:
        blockers.append({"code": "missing_pricing_method", "message": "Scope item has no pricing method assignment."})
    elif method not in _VALID_PRICING_METHODS:
        blockers.append({"code": "invalid_pricing_method", "message": "Scope item pricing method is not supported."})
    if trade_data.get("pricing_ready") is not True or not isinstance(trade_data.get("pricing_basis"), dict):
        code = {
            "quote_based": "missing_subcontract_quote",
            "allowance": "missing_allowance_basis",
        }.get(method, "missing_unit_rate")
        blockers.append({"code": code, "message": "Scope item has no verified pricing basis."})

    supported_scope = classify_supported_scope([item])
    if supported_scope["unsupported_scope_item_count"]:
        blockers.append({
            "code": "unsupported_customer_delivery_scope",
            "message": "Trade/project lane is not accuracy-validated for estimate-line generation.",
        })

    source_check = classify_delivery_sources(_delivery_sources_for_item(item))
    if source_check["test_only_source_count"]:
        blockers.append({
            "code": "test_only_delivery_sources",
            "message": "Quantity or pricing source is test-only or has unknown provenance.",
        })
    if source_check["unscoped_source_count"]:
        blockers.append({
            "code": "unscoped_delivery_sources",
            "message": "Quantity or pricing source cannot be tied to a durable scope item.",
        })
    if source_check["unsupported_source_kind_count"]:
        blockers.append({
            "code": "unsupported_delivery_source_kinds",
            "message": "Quantity or pricing source kind is not accepted as delivery evidence.",
        })
    return blockers


def _evidence(scope_item_id: str) -> list[dict[str, Any]]:
    return [
        {
            "verified_sheet_number": ev.get("verified_sheet_number"),
            "pdf_page_number": ev.get("pdf_page_number"),
            "evidence_type": ev.get("evidence_type"),
            "description": ev.get("description"),
        }
        for ev in list_evidence(UUID(scope_item_id))
    ]


def _line_from_item(item: dict[str, Any]) -> dict[str, Any]:
    trade_data = item.get("trade_data") or {}
    basis = trade_data.get("pricing_basis") or {}
    method = str(trade_data.get("pricing_method") or "")
    quantity = _to_decimal(item.get("quantity"), "quantity")
    amount = _to_decimal(basis.get("amount"), "pricing basis amount")
    if amount == 0:
        raise GenericEstimateBridgeError("invalid_amount", "pricing basis amount must be greater than zero.")

    cost_components = _normalise_components(basis, method=method, amount=amount)
    multiplier = _multiplier_for_method(method, quantity)
    labor = _to_decimal(cost_components["direct_costs"]["labor"], "direct_costs.labor") * multiplier
    material = _to_decimal(cost_components["direct_costs"]["material"], "direct_costs.material") * multiplier
    equipment = _to_decimal(cost_components["direct_costs"]["equipment"], "direct_costs.equipment") * multiplier
    subcontract = _to_decimal(cost_components["direct_costs"]["subcontract"], "direct_costs.subcontract") * multiplier
    other = _to_decimal(cost_components["direct_costs"]["other_direct"], "direct_costs.other_direct") * multiplier
    direct_total = labor + material + equipment + subcontract + other

    return {
        "trade_code": item.get("trade_code"),
        "category_code": item.get("category_code"),
        "scope_item_id": item.get("id"),
        "assembly_code": None,
        "description": item.get("description"),
        "location": item.get("location"),
        "quantity": str(quantity),
        "unit": item.get("unit"),
        "labor_hours": "0",
        "crew_hours": "0",
        "labor_cost": _money(labor),
        "material_cost": _money(material),
        "equipment_cost": _money(equipment),
        "subcontract_cost": _money(subcontract),
        "other_direct_cost": _money(other),
        "direct_cost_total": _money(direct_total),
        "status": "generic_pricing_basis",
        "components": [
            {
                "component_type": "generic_cost_components",
                "schema_version": cost_components["schema_version"],
                "pricing_method": method,
                "basis_type": cost_components["basis_type"],
                "amount": str(amount),
                "direct_costs": cost_components["direct_costs"],
                "indirect_costs": cost_components["indirect_costs"],
                "component_source": cost_components["component_source"],
                "customer_ready": False,
                "source": basis.get("source"),
                "applied_by": basis.get("applied_by"),
            }
        ],
        "exceptions": [],
        "evidence": _evidence(str(item["id"])),
        "overrides": [],
    }


def _draft_cost_book_version(project_id: UUID) -> dict[str, Any]:
    today = date.today()
    book = pricing_db.create_cost_book({
        "name": f"Generic Estimate Draft Cost Book - {project_id}",
        "description": "Draft shell for generic estimate bridge; not customer-ready pricing.",
        "currency": "USD",
        "organization": "Mobi Estimates",
    })
    version = pricing_db.create_version(UUID(book["id"]), {
        "version_label": "generic-estimate-bridge-v1-draft",
        "description": "Draft version used to hold generic pricing-basis estimate lines.",
        "effective_date": today,
        "pricing_date": today,
        "source_notes": "Generated by generic_estimate_bridge_v1 from verified pricing_basis metadata.",
    })
    pricing_db.add_cost_source(UUID(version["id"]), {
        "source_type": SourceType.REVIEWER_ENTERED.value,
        "source_name": "Generic estimate bridge source shell",
        "effective_date": today,
        "expiration_date": None,
        "project_specific": True,
        "notes": "Shell only; line items carry pricing_basis source details.",
        "verified": False,
        "payload": {"project_id": str(project_id), "source": "generic_estimate_bridge_v1"},
    })
    return version


def build_generic_estimate_draft(project_id: UUID, *, name: str = "Generic All-Trade Draft Estimate") -> dict[str, Any]:
    """Create an internal draft estimate/version from generic priced scope.

    This creates internal draft records only. It does not price through the final
    cost-book engine, approve the estimate, create a proposal, issue a proposal,
    send messages, bill, or mark customer delivery ready.
    """
    items, _ = list_scope_items(project_id, filters={"category_code": "generic_scope"}, limit=100000, offset=0)
    ready: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in items:
        blockers = _missing_blockers(item)
        if not blockers:
            try:
                line = _line_from_item(item)
            except GenericEstimateBridgeError as exc:
                blockers.append({"code": exc.code, "message": exc.message})
            else:
                ready.append(item)
                lines.append(line)
        if blockers:
            blocked.append({
                "scope_item_id": item.get("id"),
                "trade_code": item.get("trade_code"),
                "description": item.get("description"),
                "blockers": blockers,
            })

    version = _draft_cost_book_version(project_id)
    estimate = pricing_db.create_estimate(project_id, {
        "name": name,
        "description": "Internal generic all-trade estimate draft. Not approved, issued, delivered, or customer-ready.",
        "currency": "USD",
    })
    estimate_version = pricing_db.create_estimate_version(UUID(estimate["id"]), project_id, {
        "version_number": 1,
        "cost_book_version_id": version["id"],
        "pricing_date": date.today(),
        "currency": "USD",
        "markup_method": "markup",
        "inclusions": ["Generic scope items with verified quantity and pricing basis."],
        "exclusions": ["Unready scope items remain excluded from this draft and listed as blockers."],
        "assumptions": ["Pricing-basis amounts are internal draft inputs and not final customer estimate pricing."],
        "clarifications": [],
        "config": {
            "source": "generic_estimate_bridge_v1",
            "customer_delivery_ready": False,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
            "ready_scope_item_count": len(ready),
            "blocked_scope_item_count": len(blocked),
        },
    })
    pricing_db.replace_line_items(estimate_version["id"], project_id, lines)
    pricing_db.append_estimate_review(estimate_version["id"], project_id, {
        "action": "generic_draft_created",
        "previous_state": None,
        "new_state": "draft",
        "reviewer_id": "system",
        "notes": f"Created internal generic draft with {len(lines)} line(s); {len(blocked)} blocked item(s).",
    })
    return {
        "project_id": str(project_id),
        "estimate": estimate,
        "version": pricing_db.get_estimate_version(estimate_version["id"]),
        "line_items": pricing_db.get_line_items(estimate_version["id"]),
        "summary": {
            "ready_scope_item_count": len(ready),
            "blocked_scope_item_count": len(blocked),
            "line_item_count": len(lines),
            "customer_delivery_ready": False,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
        },
        "blocked_scope_items": blocked,
    }
