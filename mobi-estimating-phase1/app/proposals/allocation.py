"""Deterministic proportional sell-price allocation (largest-remainder method).

A proposal shows client-facing **sell** prices per line or trade. Phase 4 applies
overhead/profit/tax at the estimate level, so we allocate the estimate's final sell
price across lines/trades in proportion to their direct cost. Allocation uses the
Hamilton (largest-remainder) method so the parts sum **exactly** to the total after
2-decimal rounding — no penny drift.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.pricing.money import MONEY_PRECISION, quantize_money

_CENT = MONEY_PRECISION  # Decimal("0.01")


def allocate_proportionally(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split ``total`` across ``weights`` so the parts sum exactly to ``total`` (2dp).

    Zero total → all zeros. All-zero weights → an even split (with the rounding
    remainder placed on the earliest parts).
    """
    n = len(weights)
    if n == 0:
        return []
    total_q = quantize_money(total)
    if total_q == 0:
        return [Decimal("0.00")] * n

    weight_sum = sum((w if w > 0 else Decimal("0") for w in weights), Decimal("0"))
    if weight_sum == 0:
        # No cost basis to weight by → even split.
        even = [total_q / n] * n
        floored = [e.quantize(_CENT, rounding=ROUND_DOWN) for e in even]
    else:
        raw = [total_q * (w if w > 0 else Decimal("0")) / weight_sum for w in weights]
        floored = [r.quantize(_CENT, rounding=ROUND_DOWN) for r in raw]

    allocated = sum(floored, Decimal("0"))
    remainder_cents = int(((total_q - allocated) / _CENT).to_integral_value())

    if remainder_cents > 0:
        # Distribute leftover cents to the largest fractional remainders (stable).
        if weight_sum == 0:
            order = list(range(n))
        else:
            fracs = [(total_q * (weights[i] if weights[i] > 0 else Decimal("0"))
                      / weight_sum) - floored[i] for i in range(n)]
            order = sorted(range(n), key=lambda i: (-fracs[i], i))
        for k in range(remainder_cents):
            floored[order[k % n]] += _CENT

    return floored
