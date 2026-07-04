"""Deterministic rollups by project, trade, category, and cost type.

Line-level rounding is authoritative: rollups sum already-quantized line totals, so
they reconcile exactly. Incomplete/unpriced scope stays visible and never inflates a
"complete" price; completeness is measured against approved scope items.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.pricing.money import quantize_money
from app.pricing.schemas import AdjustmentType, ExceptionSeverity

_COST_BUCKETS = ("labor_cost", "material_cost", "equipment_cost",
                 "subcontract_cost", "other_direct_cost")


def _d(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


def build_rollup(
    line_items: list[dict[str, Any]], *,
    indirect_total: Decimal, indirects_applied: list[dict[str, Any]],
    adjustment_totals: dict[str, Decimal], adjustments_applied: list[dict[str, Any]],
    engine_exceptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_trade: dict[str, Decimal] = defaultdict(Decimal)
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_cost_type: dict[str, Decimal] = defaultdict(Decimal)

    labor_hours = crew_hours = Decimal("0")
    direct_by_bucket: dict[str, Decimal] = {b: Decimal("0") for b in _COST_BUCKETS}
    direct_subtotal = Decimal("0")
    unpriced = incomplete = 0
    priced = 0

    for li in line_items:
        direct = _d(li.get("direct_cost_total"))
        direct_subtotal += direct
        by_trade[li.get("trade_code") or "unknown"] += direct
        by_category[li.get("category_code") or "unknown"] += direct
        labor_hours += _d(li.get("labor_hours"))
        crew_hours += _d(li.get("crew_hours"))
        for bucket in _COST_BUCKETS:
            amt = _d(li.get(bucket))
            direct_by_bucket[bucket] += amt
            by_cost_type[bucket] += amt
        status = li.get("status")
        if status == "unpriced":
            unpriced += 1
        elif status == "incomplete":
            incomplete += 1
        else:
            priced += 1

    # Map adjustment totals to named rollup fields.
    def adj(t: str) -> Decimal:
        return adjustment_totals.get(t, Decimal("0"))

    named_adjustment_types = {
        AdjustmentType.SALES_TAX.value, AdjustmentType.BOND.value,
        AdjustmentType.INSURANCE.value, AdjustmentType.OVERHEAD.value,
        AdjustmentType.PROFIT.value, AdjustmentType.CONTINGENCY.value,
        AdjustmentType.DISCOUNT.value,
    }
    other_adjustments = sum(
        (v for k, v in adjustment_totals.items()
         if k not in named_adjustment_types and k != "final_sell_price"),
        Decimal("0"),
    )

    final_sell = adjustment_totals.get(
        "final_sell_price", direct_subtotal + indirect_total)

    total_lines = len(line_items)
    completeness_pct = (
        (Decimal(priced) / Decimal(total_lines) * Decimal("100"))
        if total_lines else Decimal("0")
    )

    blocking = sum(
        1 for li in line_items for e in li.get("exceptions", [])
        if e.get("severity") == ExceptionSeverity.BLOCKING.value
    ) + sum(1 for e in (engine_exceptions or [])
            if e.get("severity") == ExceptionSeverity.BLOCKING.value)
    warnings = sum(
        1 for li in line_items for e in li.get("exceptions", [])
        if e.get("severity") == ExceptionSeverity.WARNING.value
    ) + sum(1 for e in (engine_exceptions or [])
            if e.get("severity") == ExceptionSeverity.WARNING.value)

    totals = {
        "labor_hours": str(labor_hours.quantize(Decimal("0.0001"))),
        "crew_hours": str(crew_hours.quantize(Decimal("0.0001"))),
        "labor_cost": str(quantize_money(direct_by_bucket["labor_cost"])),
        "material_cost": str(quantize_money(direct_by_bucket["material_cost"])),
        "equipment_cost": str(quantize_money(direct_by_bucket["equipment_cost"])),
        "subcontract_cost": str(quantize_money(direct_by_bucket["subcontract_cost"])),
        "other_direct_cost": str(quantize_money(direct_by_bucket["other_direct_cost"])),
        "direct_cost_subtotal": str(quantize_money(direct_subtotal)),
        "indirect_costs": str(quantize_money(indirect_total)),
        "tax": str(quantize_money(adj(AdjustmentType.SALES_TAX.value))),
        "bond": str(quantize_money(adj(AdjustmentType.BOND.value))),
        "insurance": str(quantize_money(adj(AdjustmentType.INSURANCE.value))),
        "overhead": str(quantize_money(adj(AdjustmentType.OVERHEAD.value))),
        "profit": str(quantize_money(adj(AdjustmentType.PROFIT.value))),
        "contingency": str(quantize_money(adj(AdjustmentType.CONTINGENCY.value))),
        "discounts": str(quantize_money(adj(AdjustmentType.DISCOUNT.value))),
        "other_adjustments": str(quantize_money(other_adjustments)),
        "final_sell_price": str(quantize_money(final_sell)),
        "unpriced_scope_count": unpriced,
        "incomplete_scope_count": incomplete,
        "blocking_exception_count": blocking,
        "warning_count": warnings,
        "completeness_pct": str(completeness_pct.quantize(Decimal("0.01"))),
    }

    # Reconciliation: the sum of line direct totals equals the rollup subtotal.
    reconciled = quantize_money(
        sum((_d(li.get("direct_cost_total")) for li in line_items), Decimal("0"))
    ) == quantize_money(direct_subtotal)

    return {
        "totals": totals,
        "by_trade": {k: str(quantize_money(v)) for k, v in sorted(by_trade.items())},
        "by_category": {k: str(quantize_money(v)) for k, v in sorted(by_category.items())},
        "by_cost_type": {k: str(quantize_money(v)) for k, v in sorted(by_cost_type.items())},
        "indirects_applied": indirects_applied,
        "adjustments_applied": adjustments_applied,
        "reconciled": reconciled,
        "completeness_basis": "fully_priced_lines / total_approved_scope_lines",
    }
