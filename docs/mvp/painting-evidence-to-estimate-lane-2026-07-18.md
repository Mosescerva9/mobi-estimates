# Painting Evidence-to-Estimate Lane — 2026-07-18

## Goal

Start the focused painting evidence-to-estimate lane after upload, payment, workbench, and backup blockers were known.

This lane must not produce or deliver a final customer estimate without explicit final-estimate approval.

## 2026-07-21 narrow real-PDF proof update

The tracked 622-page City of Norman Ruby Grant Park project manual now passes a deterministic internal proof for one explicitly bounded painting sub-scope:

- Verified pages `258`–`259` (`099000-1` and `099000-2`) supply exact evidence for a minimum `100 SF` paint-system mockup and a gypsum-board three-coat system.
- The quantity is source-backed and explicitly limited to the mockup; it is not total project painting quantity.
- The existing painting module maps the reviewed scope to `PT-INT-WALL`; an internal pricing preview uses only a clearly fictional/test-only cost book and creates no estimate version.
- The customer-safe preview withholds quantity/unit because painting is not accuracy-validated for customer delivery.
- The harness creates no customer delivery, final approval, message/send, proposal, or payment action; explicit API checks verify that estimate and proposal collections remain empty.
- Real report: `/tmp/mobi-painting-public-proof-report-v4.json` (`status=pass`, `622` sheets, registered source hash matched, one scope item considered, one proposed mapping, zero blocking pricing exceptions).

Classification: **working for this one mockup-only public-spec pattern; the broader painting lane remains partially working**. This does not prove full-project painting quantities, arbitrary plan extraction, market pricing, or final estimate readiness.

## Verified today

| Check | Status | Evidence |
|---|---|---|
| Painting trade registered in live local engine | working | `GET /api/v1/trades` returned `painting` / `Painting & Coatings`, enabled, module version `1.0.0`. |
| Painting supported categories loaded | working | Engine returned categories including interior walls, ceilings, doors, coatings, striping, preparation, masking, and unclassified painting. |
| C011 real project painting routing | working as safety block | `GET /trades/painting/eligible-sheets` returned 20 sheets, all `blocked_unverified` because the project's engine sheets have no verified sheet numbers. |
| C011 real project painting extraction | working as safety block | `POST /trades/painting/extractions` completed with provider `mock`, input sheet count 20, processed sheet count 0, blocked sheet count 20, candidate count 0. |
| C011 real project painting scope items | working as empty | `GET /scope-items?trade_code=painting` returned total 0/items `[]`. |
| C011 text paint-signal search | working as no-scope finding | Search of processed sheet text found no `paint`, `painting`, `coating`, `finish`, or `finishes` hits. |
| Focused painting/estimate tests | working | `pytest -q tests/test_trade_registry.py tests/test_extraction_lifecycle.py tests/test_review_workflow.py tests/test_pricing_e2e.py` passed: 43 tests. |

## Classification

Current painting lane status: **partially_working**.

- The painting module, routing, extraction lifecycle, review workflow, and pricing E2E tests are working.
- The live C011 proof project is not a painting project; it has no painting/finish/coating evidence and its sheets are unverified, so it correctly produces no painting scope.
- No final customer estimate was generated, approved, delivered, emailed, or exposed.

## What is needed to make the lane `working` on a real project

1. Use a real or sanitized project containing painting/finish/coating scope.
2. Verify relevant sheet numbers/titles through the sheet verification endpoint.
3. Run painting extraction against verified sheets.
4. Confirm every scope item has evidence and quantity basis.
5. Map approved/internal-reviewed painting scope to assemblies using a test or approved cost book.
6. Run pricing preview only; do not approve, publish, send, or deliver a final estimate without explicit final-estimate approval.

## Safety notes

- Painting routing is intentionally conservative: unverified sheets block extraction; OCR-required sheets block extraction; non-painting disciplines without paint signals are excluded.
- The reference pricing templates contain structure only, not production market pricing.
- Missing coats, substrate, prep, coverage, height/access, or quantity basis must block automatic mapping rather than invent defaults.
