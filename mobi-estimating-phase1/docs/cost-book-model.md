# Cost-Book Model

Cost books hold all priced inputs and are **versioned**. A cost-book version moves
through `draft → published → archived`.

- **Draft** versions are editable (add sources/rates/assemblies, CSV import).
- **Published** versions are **immutable**. To change prices, create a new draft
  version. Estimates reference a published version, so they stay reproducible.
- **Archived** versions remain readable. A version referenced by an estimate is
  never deleted.
- A version cannot be published while validation errors exist (e.g. an assembly
  with no components, a duplicate assembly code, or a component missing a
  `cost_item_ref`).

## Cost sources

Every rate references a **cost source** (`contractor_rate`, `supplier_quote`,
`vendor_catalog`, `historical_job_cost`, `subcontractor_quote`,
`equipment_rental_quote`, `internal_price_book`, `reviewer_entered`,
`licensed_database`, `other`) with an effective date, optional expiration, and a
`verified` flag. Expired sources raise a stale-price warning (or a blocker when
configured). Unverified sources never silently become trusted production rates.

**No real or copyrighted cost data is bundled.** Tests use clearly fictional values.

## Material / equipment / subcontract / other-direct rules

- Material waste, freight, and sales tax are **separate** unless the source
  explicitly includes them. Coverage conversions (e.g. SF → gallons) are
  deterministic and versioned; missing conversion data blocks pricing.
- Equipment never assumes duration, operator inclusion, delivery, fuel, or
  mobilization; minimum charges are explicit; operator double-counting is prevented.
- Subcontract quotes preserve the original amount; leveling adjustments are explicit
  and never overwrite the quote; unverified quotes warn.
- Other direct costs are itemized (no uncategorized hidden allowance).
