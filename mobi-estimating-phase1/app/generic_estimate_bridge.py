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
from app.capability_registry import (
    build_delivery_source_row,
    classify_delivery_sources,
    classify_supported_scope,
    evaluate_delivery_lock,
    has_test_only_metadata,
    is_complete_delivery_evidence_row,
    is_test_only_source,
)
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


def _delivery_source_record(
    *,
    scope_item_id: Any,
    kind: str,
    source: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build a canonical delivery-source row and preserve test-only flags.

    A real-looking source name is not sufficient delivery evidence when the
    structured metadata marks the row as a fixture/synthetic/internal-test input.
    The final delivery lock understands these flags, so the generic draft bridge
    must forward them instead of dropping them while deciding whether to create
    internal estimate lines.
    """
    return build_delivery_source_row(
        scope_item_id=scope_item_id,
        kind=kind,
        source=source,
        metadata=metadata,
    )


def _delivery_sources_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return quantity/pricing source records that would back an estimate line.

    Malformed metadata containers are represented as missing source rows instead
    of being silently omitted. Otherwise an internal draft bridge could block on a
    generic missing-price message while the delivery-source safety check reports a
    clean/no-test-only source set for malformed pricing provenance.
    """
    sources: list[dict[str, Any]] = []
    scope_item_id = item.get("id")
    raw_trade_data = item.get("trade_data")
    trade_data = _dict_or_empty(raw_trade_data)
    if raw_trade_data is not None and not isinstance(raw_trade_data, dict):
        sources.append(_delivery_source_record(
            scope_item_id=scope_item_id,
            kind="pricing_basis",
            source=None,
            metadata={},
        ))
    raw_pricing_basis = trade_data.get("pricing_basis")
    pricing_basis = _dict_or_empty(raw_pricing_basis)
    if raw_pricing_basis is not None and not isinstance(raw_pricing_basis, dict):
        sources.append(_delivery_source_record(
            scope_item_id=scope_item_id,
            kind="pricing_basis",
            source=None,
            metadata={},
        ))
    elif isinstance(raw_pricing_basis, dict):
        sources.append(_delivery_source_record(
            scope_item_id=scope_item_id,
            kind="pricing_basis",
            source=pricing_basis.get("source"),
            metadata=pricing_basis,
        ))
        raw_cost_components = pricing_basis.get("cost_components")
        cost_components = _dict_or_empty(raw_cost_components)
        if raw_cost_components is not None and not isinstance(raw_cost_components, dict):
            sources.append(_delivery_source_record(
                scope_item_id=scope_item_id,
                kind="cost_component_source",
                source=None,
                metadata={},
            ))
        elif isinstance(raw_cost_components, dict):
            sources.append(_delivery_source_record(
                scope_item_id=scope_item_id,
                kind="cost_component_source",
                source=cost_components.get("component_source"),
                metadata=cost_components,
            ))
    raw_quantity_inputs_value = item.get("raw_quantity_inputs")
    raw_quantity_inputs = _dict_or_empty(raw_quantity_inputs_value)
    raw_verified_quantity = raw_quantity_inputs.get("verified_quantity_input_v1")
    verified_quantity = _dict_or_empty(raw_verified_quantity)
    if item.get("quantity") not in (None, ""):
        sources.append(_delivery_source_record(
            scope_item_id=scope_item_id,
            kind="quantity_input",
            source=verified_quantity.get("source") if isinstance(raw_quantity_inputs_value, dict) else None,
            metadata=verified_quantity,
        ))
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
    pricing_basis = trade_data.get("pricing_basis")
    if trade_data.get("pricing_ready") is not True or not isinstance(pricing_basis, dict):
        code = {
            "quote_based": "missing_subcontract_quote",
            "allowance": "missing_allowance_basis",
        }.get(method, "missing_unit_rate")
        blockers.append({"code": code, "message": "Scope item has no verified pricing basis."})
    elif pricing_basis.get("cost_components") is not None and not isinstance(pricing_basis.get("cost_components"), dict):
        blockers.append({"code": "invalid_cost_components", "message": "cost_components must be an object."})

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


def _evidence_row_is_complete(row: dict[str, Any]) -> bool:
    """Return true only for a concrete sheet/page evidence reference."""
    return is_complete_delivery_evidence_row(row)


def _evidence_row_is_test_only(row: dict[str, Any]) -> bool:
    """Return true when an evidence row is marked as fixture/test-only data.

    The generic bridge's draft-level delivery lock must not report
    ``evidence_complete`` from harness/benchmark/prototype rows just because they
    have a plausible sheet/page reference. Treat explicit nested test-only
    metadata and test-like artifact references as non-delivery evidence while not
    requiring legacy rows to have an artifact reference at all.
    """
    if has_test_only_metadata(row):
        return True
    source_artifact_ref = row.get("source_artifact_ref")
    if source_artifact_ref is None:
        return False
    return is_test_only_source(source_artifact_ref)


def _ready_items_have_complete_evidence(ready_items: list[dict[str, Any]]) -> bool:
    """Every draft-ready scope item must have at least one verified evidence row.

    The generic bridge is internal-only, but its stored lock metadata must not say
    ``evidence_complete`` merely because a scope item had quantity/pricing fields.
    A missing/malformed scope ID or empty evidence list is still incomplete final
    delivery evidence.
    """
    if not ready_items:
        return False
    for item in ready_items:
        try:
            scope_item_id = UUID(str(item.get("id") or ""))
        except (TypeError, ValueError):
            return False
        if not any(_evidence_row_is_complete(row) for row in list_evidence(scope_item_id)):
            return False
    return True


def _delivery_lock_for_ready_items(ready_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the canonical final-delivery lock for the complete draft line set.

    The generic bridge is an internal draft helper, not a customer-delivery path.
    Still, its payload must use the same lock authority as readiness/proposals so
    future approval wiring cannot accidentally rely on a weaker per-item clone.
    """
    delivery_sources = [
        source
        for item in ready_items
        for source in _delivery_sources_for_item(item)
    ]
    supported_scope = classify_supported_scope(ready_items)
    return evaluate_delivery_lock(
        evidence_complete=_ready_items_have_complete_evidence(ready_items),
        required_reviews_complete=False,
        owner_approval=None,
        delivery_sources=delivery_sources,
        unsupported_scope=supported_scope,
        expected_scope_item_count=len(ready_items),
        expected_scope_item_ids=[item.get("id") for item in ready_items],
    )


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

    delivery_lock = _delivery_lock_for_ready_items(ready)
    customer_delivery_ready = delivery_lock["delivery_unlocked"]

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
            "customer_delivery_ready": customer_delivery_ready,
            "customer_delivery_lock": delivery_lock,
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
            "customer_delivery_ready": customer_delivery_ready,
            "customer_delivery_lock": delivery_lock,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
        },
        "blocked_scope_items": blocked,
    }
