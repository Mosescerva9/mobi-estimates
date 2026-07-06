"""Generic all-trade estimate draft bridge v1.

This module converts generic scope items with verified quantity/pricing basis
metadata into an internal draft estimate version and draft estimate line items.
It is intentionally not a final pricing engine, approval path, proposal issue
path, customer delivery path, or payment/billing action.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app import pricing_db
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
    return str(value.quantize(Decimal("0.01")))


def _missing_blockers(item: dict[str, Any]) -> list[dict[str, Any]]:
    trade_data = item.get("trade_data") or {}
    method = str(trade_data.get("pricing_method") or "")
    blockers: list[dict[str, Any]] = []
    if item.get("quantity") in (None, ""):
        blockers.append({"code": "missing_quantity", "message": "Scope item has no verified quantity."})
    if not method:
        blockers.append({"code": "missing_pricing_method", "message": "Scope item has no pricing method assignment."})
    if trade_data.get("pricing_ready") is not True or not isinstance(trade_data.get("pricing_basis"), dict):
        code = {
            "quote_based": "missing_subcontract_quote",
            "allowance": "missing_allowance_basis",
        }.get(method, "missing_unit_rate")
        blockers.append({"code": code, "message": "Scope item has no verified pricing basis."})
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

    if method == "quote_based":
        direct_total = amount
        labor = material = equipment = other = Decimal("0")
        subcontract = direct_total
        component_type = "subcontract"
    elif method == "allowance":
        direct_total = amount
        labor = material = equipment = subcontract = Decimal("0")
        other = direct_total
        component_type = "allowance"
    else:
        direct_total = quantity * amount
        labor = material = equipment = subcontract = Decimal("0")
        other = direct_total
        component_type = "unit_rate"

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
                "component_type": component_type,
                "pricing_method": method,
                "amount": str(amount),
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
