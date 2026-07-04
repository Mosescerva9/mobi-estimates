# Pricing Calculation Order & Rounding Policy

## Rounding

- All math is `Decimal`. NaN/Infinity are rejected; floats are parsed via `str` so a
  documented JSON string (`"0.1"`) is exact.
- Internal/intermediate values keep 6 dp (`CALC_PRECISION`).
- **Line-level rounding is authoritative.** Each line item's cost buckets are
  quantized to currency (2 dp, half-up) at the line boundary. Project rollups sum the
  already-quantized line totals, so direct-cost rollups reconcile **exactly**.
- Estimate-level adjustments are each quantized to 2 dp as applied.

## Order of operations

1. Per line: component costs (material, labor, equipment, subcontract, other-direct)
   → quantized buckets → `direct_cost_total`.
2. Project direct subtotal = Σ line direct totals.
3. **Indirect costs** (fixed / quantity×rate / duration×rate / % of selected
   categories / manual). Duration-based indirects require an explicit duration.
4. **Ordered adjustments** by `sequence`, each on its declared base categories:
   discounts, escalation, sales tax (taxable categories only), bond, insurance,
   overhead, profit, contingency. Compounding is explicit via the running ledger.

## Markup vs margin

- Markup: `amount = base × rate`.
- Margin: `amount = base ÷ (1 − rate) − base` (rate ≥ 100% rejected).
- The user chooses per overhead/profit adjustment; the method and base are recorded.

## Completeness

`completeness_pct = fully-priced lines ÷ total approved lines × 100`. Incomplete and
unpriced lines remain visible; a "complete project price" is never shown while
blocking exceptions remain.
