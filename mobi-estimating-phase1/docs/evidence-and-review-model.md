# Evidence & Human-Review Model

## Why AI output is untrusted

The provider (AI) may **identify, transcribe, classify, and organize** information.
It may **not** produce trusted derived quantities or any pricing. Its output is a
*candidate* that must pass shared validation, trade-module validation, deterministic
recomputation, and finally human review before it is trusted.

## The verified-sheet requirement

Every scope item must carry **at least one evidence reference**, and every trusted
evidence reference must point at a **verified** sheet:

- Phase 2 distinguishes a *detected* sheet number (a candidate) from a *verified*
  one (a human-confirmed value).
- During extraction, evidence is **rebuilt server-side** from the database sheet
  record. The provider's claimed sheet number is discarded; the verified number from
  the DB is used instead.
- Evidence whose page cannot be tied to a verified project sheet is dropped, and the
  item is blocked with `missing_verified_sheet`.
- `app.schemas.build_source_reference()` refuses to build a trusted source reference
  from an unverified sheet number.

## Evidence reference fields

`id, project_id, sheet_id, pdf_page_number, verified_sheet_number, evidence_type,
description, extracted_text_quote?, text_block_coords?, page_region_coords?,
source_artifact_ref (logical, never a filesystem path), provider_confidence?,
requires_human_verification, created_at, updated_at`.

Evidence types include schedule/finish/room-finish/door/equipment/fixture schedules,
general notes, keynotes, legends, drawing dimensions, explicit quantities, details,
sections, elevations, floor plans, reflected ceiling plans, specification notes,
addenda, reviewer entries, and other. A trade module may narrow or extend the set and
may require multiple references for certain approvals.

## Quantity basis

`QuantityBasis` records how a quantity was obtained. Providers may transcribe
`explicit_plan_quantity`, `schedule_*`, `drawing_count`, and quote quantities.
`dimension_inputs` and `deterministic_derivation` are **always recomputed in Python**.
`manual_reviewer_entry` is set when a human enters a value. If the basis is `unknown`
the quantity stays null. A scope item may exist with no resolved quantity, but that
blocks approval when the trade/category requires one.

## Review states & rules

States: `pending`, `approved`, `corrected`, `rejected`, `blocked`.

- Every AI item starts `pending` (or `blocked` if it has blocking issues).
- **No** AI item is auto-approved.
- Approval requires: trusted evidence on a verified sheet, a resolved quantity where
  the trade/category requires one, and **no** open blocking conflicts/issues.
- Corrections **preserve** the original provider candidate (stored separately) and
  rerun trade-module + shared validation.
- A reviewer-entered quantity is recorded as `manual_reviewer_entry`.
- Recalculation uses only registered formulas for the item's trade — never arbitrary
  client expressions.
- Rejection requires a reason.
- Review history is **append-only** (`review_events`).
- Approved records keep the exact schema and module versions used.

## Conflicts

Severities: `information`, `warning`, `blocking`. Shared codes cover schedule/plan,
spec/drawing, addenda, duplicates, missing quantity/unit/dimensions/verified-sheet,
OCR-required, unsupported unit/formula, missing evidence, non-reproducible quantity,
trade-validation failure, and uncertain classification. Trade modules may add codes.
Conflicts are **never auto-resolved**; blocking conflicts prevent approval and all
competing evidence is preserved.
