"""Explicit, ordered adjustment engine (markup/margin, tax, overhead, profit,
contingency, discounts, escalation, bond, insurance).

Markup and margin are distinct: markup ⇒ amount = base × rate; margin ⇒
amount = base ÷ (1 − rate) − base. Every adjustment records its base, method, and
amount so the calculation order is fully auditable. Contingency stays a separate
line in rollups and is never used to hide missing scope.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.pricing.money import quantize_money, to_decimal
from app.pricing.schemas import (
    AdjustmentType,
    ExceptionCode,
    ExceptionSeverity,
    IndirectBasis,
    MarkupMethod,
)

DISCOUNT_TYPES = {AdjustmentType.DISCOUNT.value}
MARKUP_CAPABLE = {AdjustmentType.OVERHEAD.value, AdjustmentType.PROFIT.value}


def compute_indirects(
    indirects: list[dict[str, Any]], direct_by_category: dict[str, Decimal]
) -> tuple[list[dict[str, Any]], Decimal, list[dict[str, Any]]]:
    """Compute indirect costs. Returns (applied, total, exceptions)."""
    applied: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    total = Decimal("0")
    direct_subtotal = sum(direct_by_category.values(), Decimal("0"))
    for ind in indirects:
        basis = IndirectBasis(ind["basis"])
        amount = Decimal("0")
        if basis == IndirectBasis.FIXED or basis == IndirectBasis.MANUAL_ALLOWANCE:
            amount = to_decimal(ind.get("amount") or "0", field="amount")
        elif basis == IndirectBasis.QUANTITY_RATE:
            amount = (to_decimal(ind.get("quantity") or "0", field="quantity")
                      * to_decimal(ind.get("rate") or "0", field="rate"))
        elif basis == IndirectBasis.DURATION_RATE:
            duration = ind.get("duration")
            if duration in (None, ""):
                exceptions.append({"code": ExceptionCode.MISSING_INDIRECT_DURATION.value,
                                   "severity": ExceptionSeverity.BLOCKING.value,
                                   "message": f"Indirect '{ind.get('name')}' needs a duration"})
                continue
            amount = (to_decimal(duration, field="duration")
                      * to_decimal(ind.get("rate") or "0", field="rate"))
        elif basis == IndirectBasis.PERCENT:
            base = _sum_categories(ind.get("base_categories", []), direct_by_category,
                                   direct_subtotal)
            amount = base * to_decimal(ind.get("percent") or "0", field="percent")
        amount = quantize_money(amount)
        total += amount
        applied.append({"name": ind.get("name"), "basis": basis.value,
                        "amount": str(amount), "taxable": bool(ind.get("taxable"))})
    return applied, quantize_money(total), exceptions


def _sum_categories(categories: list[str], ledger: dict[str, Decimal],
                    running: Decimal) -> Decimal:
    if not categories:
        return running
    return sum((ledger.get(cat, Decimal("0")) for cat in categories), Decimal("0"))


def apply_adjustments(
    direct_by_category: dict[str, Decimal], indirect_total: Decimal,
    adjustments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Decimal], list[dict[str, Any]]]:
    """Apply ordered adjustments. Returns (applied, totals_by_type, exceptions)."""
    ledger: dict[str, Decimal] = dict(direct_by_category)
    direct_subtotal = sum(direct_by_category.values(), Decimal("0"))
    ledger["direct_subtotal"] = direct_subtotal
    ledger["indirect"] = indirect_total
    running = direct_subtotal + indirect_total
    ledger["running"] = running

    applied: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {}
    exceptions: list[dict[str, Any]] = []

    for adj in sorted(adjustments, key=lambda a: a.get("sequence", 0)):
        atype = adj["adjustment_type"]
        base = _sum_categories(adj.get("base_categories", []), ledger, running)
        percent = adj.get("percent")
        fixed = adj.get("fixed_amount")
        method = adj.get("method")

        if atype == AdjustmentType.SALES_TAX.value and not adj.get("base_categories"):
            exceptions.append({"code": ExceptionCode.MISSING_TAX_TREATMENT.value,
                               "severity": ExceptionSeverity.WARNING.value,
                               "message": "Sales tax has no explicit taxable base categories"})

        if percent not in (None, ""):
            rate_value = to_decimal(percent, field="percent", allow_negative=True)
            if atype in MARKUP_CAPABLE and method == MarkupMethod.MARGIN.value:
                if rate_value >= 1:
                    exceptions.append({"code": ExceptionCode.CALCULATION_FAILURE.value,
                                       "severity": ExceptionSeverity.BLOCKING.value,
                                       "message": f"Margin rate >= 100% for '{adj.get('name')}'"})
                    continue
                amount = base / (Decimal("1") - rate_value) - base
            else:
                amount = base * rate_value
        elif fixed not in (None, ""):
            amount = to_decimal(fixed, field="fixed_amount", allow_negative=True)
        else:
            amount = Decimal("0")

        if atype in DISCOUNT_TYPES:
            amount = -abs(amount)
        amount = quantize_money(amount)

        running += amount
        ledger["running"] = running
        ledger[atype] = ledger.get(atype, Decimal("0")) + amount
        totals[atype] = totals.get(atype, Decimal("0")) + amount
        applied.append({
            "adjustment_type": atype, "name": adj.get("name"),
            "method": method, "base": str(quantize_money(base)),
            "amount": str(amount), "sequence": adj.get("sequence", 0),
            "rationale": adj.get("rationale", ""),
        })

    totals["final_sell_price"] = quantize_money(running)
    return applied, totals, exceptions
