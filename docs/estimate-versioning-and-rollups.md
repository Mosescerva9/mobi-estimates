# Estimate Versioning, Snapshots & Rollups

## Versions

An estimate owns immutable **versions** (`draft → pricing → needs_review → priced →
approved → superseded`). Repricing creates a **new** version and supersedes the
previous one (which stays readable). An approved version is immutable and cannot be
repriced. A version cannot be approved while blocking exceptions remain.

## Snapshots (reproducibility)

Each priced version stores a normalized JSON **snapshot** of every effective input
(scope quantities, evidence, assemblies + components, labor/crew/production/material/
equipment/subcontract/other-direct rates, sources, indirects, adjustments, formula +
engine versions, rounding policy) plus a deterministic SHA-256 hash. Re-pricing from
the snapshot is independent of the live cost book, so changing draft live data never
alters a historical version. Snapshots contain no secrets.

## Rollups

Deterministic rollups by project, trade, scope category, and cost type. Project
totals separately show labor/crew hours, each cost bucket, direct subtotal, indirect
costs, tax, bond, insurance, overhead, profit, contingency, discounts, other
adjustments, final sell price, unpriced/incomplete counts, blocking/warning counts,
and completeness %. Rollups reconcile to the sum of line direct totals.
