"""Generic lane quantity/pricing preparation v1.

This module does not create final prices. It classifies generic scope items into a
safe pricing method, creates draft-only cost provenance shells, and surfaces the
next missing inputs for automation or reviewer follow-up.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app import pricing_db
from app.extraction.schemas import ReviewStatus
from app.extraction_db import list_scope_items, update_scope_item
from app.pricing.schemas import SourceType

QUOTE_KEYWORDS = {
    "fire_alarm",
    "fire_protection",
    "technology",
    "low_voltage",
    "doors_hardware",
}
ALLOWANCE_KEYWORDS = {
    "landscape",
    "sitework",
    "civil_sitework",
}


def _method_for_scope(item: dict[str, Any]) -> str:
    trade = item.get("trade_code", "")
    category = item.get("category_code", "")
    if trade in QUOTE_KEYWORDS or category == "quote_based":
        return "quote_based"
    if trade in ALLOWANCE_KEYWORDS or category == "allowance":
        return "allowance"
    return "unit_rate_needed"


def _pricing_blockers(method: str) -> list[dict[str, str]]:
    blockers = [
        {"code": "missing_quantity", "message": "Generic scope candidate has no quantity yet."},
    ]
    if method == "quote_based":
        blockers.append({
            "code": "missing_subcontract_quote",
            "message": "Quote-based generic scope requires a verified subcontractor/supplier quote.",
        })
    elif method == "allowance":
        blockers.append({
            "code": "missing_allowance_basis",
            "message": "Allowance generic scope requires a documented allowance amount and basis.",
        })
    else:
        blockers.append({
            "code": "missing_unit_rate",
            "message": "Unit-rate generic scope requires verified labor/material/equipment/production rates.",
        })
    return blockers


def assign_generic_pricing_methods(project_id: UUID) -> dict[str, Any]:
    """Assign safe pricing-method metadata to active generic scope items."""
    items, _ = list_scope_items(
        project_id,
        filters={"category_code": "generic_scope"},
        limit=1000,
        offset=0,
    )
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in items:
        if item.get("review_status") == ReviewStatus.REJECTED.value:
            skipped.append({"scope_item_id": item["id"], "reason": "rejected"})
            continue
        method = _method_for_scope(item)
        trade_data = item.get("trade_data") or {}
        trade_data.update({
            "pricing_method": method,
            "quantity_method": "needs_takeoff_or_reviewer_input",
            "pricing_assignment_source": "generic_pricing_prep_v1",
            "delivery_ready": False,
        })
        assumptions = item.get("assumptions") or []
        assumption_text = f"Generic pricing method assigned as {method}; final pricing still requires verified inputs."
        if not any(a.get("text") == assumption_text for a in assumptions if isinstance(a, dict)):
            assumptions.append({"text": assumption_text})
        row = update_scope_item(
            UUID(item["id"]),
            trade_data=trade_data,
            blocking_issues=_pricing_blockers(method),
            assumptions=assumptions,
            review_status=ReviewStatus.BLOCKED.value,
            conflict_status="blocking",
            reviewer_notes="Generic pricing method assigned by deterministic v1 prep.",
        )
        assert row is not None
        updated.append(row)
    counts: dict[str, int] = {}
    for row in updated:
        method = (row.get("trade_data") or {}).get("pricing_method", "unknown")
        counts[method] = counts.get(method, 0) + 1
    return {
        "project_id": str(project_id),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "method_counts": counts,
        "items": updated,
        "skipped": skipped,
    }


def seed_generic_cost_provenance(project_id: UUID, *, effective_date: date, pricing_date: date) -> dict[str, Any]:
    """Create a draft cost-book shell and one internal provenance source.

    This intentionally does not publish rates and does not create priced estimates.
    It gives the next workflow a safe home for verified rates/quotes/allowances.
    """
    book = pricing_db.create_cost_book({
        "name": f"Generic Lane Draft Cost Book - {project_id}",
        "description": "Draft-only cost provenance shell for generic all-trade automation.",
        "currency": "USD",
        "organization": "Mobi Estimates",
    })
    version = pricing_db.create_version(UUID(book["id"]), {
        "version_label": "generic-lane-v1-draft",
        "description": "Draft shell for verified all-trade generic lane rates, quotes, and allowances.",
        "effective_date": effective_date,
        "pricing_date": pricing_date,
        "source_notes": "Seeded by Generic Lane Cost Provenance v1; rates still require verification.",
    })
    source = pricing_db.add_cost_source(UUID(version["id"]), {
        "source_type": SourceType.REVIEWER_ENTERED.value,
        "source_name": "Mobi internal generic lane seed source",
        "effective_date": effective_date,
        "expiration_date": None,
        "project_specific": True,
        "notes": "Placeholder provenance source only. Do not price from unverified placeholder data.",
        "verified": False,
        "payload": {"project_id": str(project_id), "source": "generic_cost_provenance_v1"},
    })
    return {
        "project_id": str(project_id),
        "cost_book": book,
        "version": version,
        "sources": [source],
        "published": False,
        "pricing_ready": False,
        "next_required_inputs": [
            "verified production/labor/material/equipment rates for unit-rate scopes",
            "verified subcontractor/supplier quotes for quote-based scopes",
            "documented allowance basis and approved amount for allowance scopes",
        ],
    }
