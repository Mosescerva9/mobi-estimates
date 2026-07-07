# Mobi Automation Progress

_Last updated: 2026-07-07_

## Mobi AutoResearch v1 scaffold (2026-07-07)

Built the first internal AutoResearch layer on top of Golden Set v2.

- Added `mobi-estimating-phase1/scripts/mobi_autoresearch.py` with four local/internal commands:
  - `score` computes a deterministic scalar score from a Golden Set report.
  - `baseline` runs Golden Set v2 eval with `--no-fail-on-accuracy` and scores the report.
  - `guard` rejects experiment diffs that edit locked evaluator/source paths or files outside the allowed mutable target.
  - `append-ledger` appends JSONL experiment records for baseline/accepted/rejected runs.
- Added `mobi-estimating-phase1/tests/test_mobi_autoresearch.py` for scoring, zero-denominator handling, guard failures, ledger append, and CLI output.
- Added `mobi-estimating-phase1/docs/golden-set-autoresearch.md` documenting the locked evaluator, mutable artifact model, score formula, guardrails, and first target: OCR/sheet extraction for image-heavy Golden Set v2 drawing PDFs.

**Interpretation:** this does not yet run infinite autonomous experiments. It is the safe v1 scaffold needed before an agent can mutate one artifact, re-score, keep improvements, and revert failures.

## Real Golden Set v2 drawing corpus and measured-quantity baseline (2026-07-07)

Created the first Golden Set v2 corpus using complete public drawing/plan PDFs as primary evaluated documents.

- Downloaded official public California DGS plan/spec packages into `mobi-estimating-phase1/data/golden_set_v2/documents/`:
  - `ca_dgs_22_130586_plans.pdf`, project manual, and `ca_dgs_22_130586_addendum_1.pdf` for San Gorgonio Pass Perimeter Fence.
  - `ca_dgs_24_253614_plans.pdf` and project manual for Lot 50 Accessibility Upgrades & EVCS.
  - `ca_dgs_25_275745_plans.pdf` and project manual for DSH Administration and Annex Building Roof Replacement Patton.
- Added `mobi-estimating-phase1/data/golden_set_v2/sources.v2.json` with public source URLs, robots/access metadata, byte counts, SHA256 hashes, local paths, and source notes.
- Added `mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json` with 9 hand-read source-backed quantities, including sheet/page references, evidence snippets, measurement methods, confidence levels, assumptions, and explicit `require_engine_quantity=false` baseline flags.
- Added `mobi-estimating-phase1/data/golden_set_v2/README.md` and generated `reports/golden_set_real_v2_report.json` + `reports/golden_set_real_v2_summary.md`.
- Enhanced `golden_set_extraction_eval.py` with v2 fields and scoring:
  - source document / sheet / page / evidence / method / confidence / assumptions on key quantities;
  - `evidence_verified` and evidence-snippet scoring;
  - document text extraction status via local `pdftotext`;
  - extraction-quality buckets for text extraction, sheet detection, scope detection, trade classification, quantity extraction, unit normalization, evidence quality, and hallucination/unsupported-trade guardrails;
  - false-positive trade separation into allowed-extra vs unexpected false positives;
  - optional `--fail-on-unexpected-false-positive-trade` CLI gate.
- Ran real v2 eval without `--allow-missing-documents`:
  ```bash
  /tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
    --manifest data/golden_set_v2/manifest.real-v2.json \
    --output data/golden_set_v2/reports/golden_set_real_v2_report.json \
    --workdir data/golden_set_v2/workdirs/real-v2-pass \
    --no-fail-on-accuracy
  ```
- Result: 3 projects evaluated, 0 skipped, 0 harness failures, 0 safety violations, document text extraction pass `3/3`, sheet detection pass `3/3`, key quantity evidence pass `9/9`, key quantity pass `9/9`, evaluation pass `1/3`, accuracy failure count `2`, trade recall micro `0.3333`, scope keyword coverage micro `0.3333`, unexpected false-positive trades `0`.

**Interpretation:** this is a successful real v2 baseline/report, not a successful takeoff-accuracy result. It proves the harness can run drawing PDFs and report measured quantities with source evidence. It also exposes the next hard blocker: two image-heavy drawing sets produced zero scope items, so OCR/vision/sheet-table extraction must improve before Mobi can claim reliable drawing-set takeoff accuracy. Addenda completeness remains conservatively incomplete until Cal eProcure event packages are audited.

## Real Golden Set v1 public-PDF corpus and first accuracy report (2026-07-07)

Created the first real public/authorized bid-document Golden Set corpus and ran it through the harness without `--allow-missing-documents`.

- Downloaded 3 public PDFs from official public sources into `mobi-estimating-phase1/data/golden_set/documents/`:
  - University of South Carolina Longstreet Theatre Exterior Restoration project manual.
  - California DGS / CHP San Gorgonio Pass Perimeter Fence project manual.
  - City of Norman Ruby Grant Park sealed bid specifications / Amendment One.
- Added `mobi-estimating-phase1/data/golden_set/sources.json` with source URLs, robots checks, byte counts, content types, SHA256 values, and internal-testing-only/access metadata.
- Added `mobi-estimating-phase1/data/golden_set/manifest.real-v1.json` with hand-filled expected current-engine trade lanes (`architectural_general`, `concrete`, `finishes`), source notes, inclusions/exclusions, addenda-completeness status, and quantity limitations.
- Added `mobi-estimating-phase1/data/golden_set/README.md` and ignored generated `workdirs/` / `text_extracts/` artifacts.
- Ran:
  ```bash
  /tmp/mobi-estimating-venv/bin/python scripts/golden_set_extraction_eval.py \
    --manifest data/golden_set/manifest.real-v1.json \
    --output data/golden_set/reports/golden_set_real_v1_report.json \
    --workdir data/golden_set/workdirs/real-v1-pass
  ```
- Result: 3 projects evaluated, 0 skipped, 0 harness failures, 0 safety violations, 3/3 evaluation passes, trade recall micro `1.0`, scope keyword coverage micro `1.0`, key quantity total `0`, benchmark-ineligible count `3`, false-positive trade total `36`.
- Added `mobi-estimating-phase1/data/golden_set/reports/golden_set_real_v1_summary.md` documenting the real result, weaknesses, and next priorities.

**Interpretation:** this proves the local Golden Set harness can process real public PDFs and generate a real accuracy report safely. It does not yet prove final estimating/takeoff accuracy because the corpus is project-manual/specification-heavy, addenda completeness is not established, the current engine path is generic trade census/scope, and no source-backed measured quantity ground truth has been added yet.

## Golden Set v1 + extraction evaluation harness (2026-07-07)

Built the first extraction-evaluation harness so we can measure whether the local engine can *read* real bid packages before deeper bid-outcome calibration.

- Added `mobi-estimating-phase1/scripts/golden_set_extraction_eval.py`: loads/validates a golden-set manifest, runs each project's primary document through `real_document_harness.run_harness` in an isolated workdir, and scores extraction.
- Scoring per project: required-trade coverage (recall/precision, missed + false-positive trades), expected scope-keyword coverage, key-quantity tolerance checks (`pass`/`fail`/`unknown`, with unit-mismatch and missing-quantity surfaced honestly), addenda-completeness → `benchmark_ineligible` with warning, and safety-flag assertions.
- Manifest requires internal-testing/authorization metadata (`internal_testing_only`, `source_authorization` ∈ public/authorized/internal) and rejects missing document paths unless `--allow-missing-documents` is set for fixture/schema validation.
- CI semantics: exit `2` on manifest validation failure; exit `1` on any harness failure, any safety-lock violation, and any accuracy failure by default; `--no-fail-on-accuracy` is available for report-only mode. Missed required trades, missing expected keywords, and declared key quantities that fail/return `unknown` mark `evaluation_passed=false`.
- Added `mobi-estimating-phase1/data/golden_set/manifest.example.json` (placeholder example), `mobi-estimating-phase1/tests/test_golden_set_extraction_eval.py` (coverage for manifest validation, safety locks, accuracy gates, outcome-leakage rejection, tolerance validation, and CLI semantics), and `mobi-estimating-phase1/docs/golden-set-extraction-evaluation.md`, linked from the real bid-board shakeout guide.
- Hardened `real_document_harness.py` to page through all scope items beyond the API's 200-item cap, with a regression proving item 201 is included in reports/scoring.
- Verification: targeted Golden Set + real-document harness tests passed (`44 passed`), full `mobi-estimating-phase1` suite passed (`410 passed`), `npm run typecheck` passed, `py_compile` on the harness scripts passed, `git diff --check` passed, CLI dry-run with `--allow-missing-documents` produced a report with safety locks closed, and Codex rereview passed.

**Safety:** local/internal testing only. No customer delivery/send/approval/payment/proposal-issue flags were unlocked (the harness asserts they stay closed), no external sources were contacted in tests, and no production/deploy/DNS/Stripe/legal/email changes were made.

## Public bid-board PDF discovery/import pipeline (2026-07-07)

Built a conservative public-source collector for creating Mobi's first real bid-board PDF test corpus from SAM.gov and allowlisted public agency pages.

- Added `mobi-estimating-phase1/scripts/public_bid_board_pdf_collector.py`.
- Supported SAM.gov Opportunities API-style responses, including live mode via `SAM_GOV_API_KEY` / `--sam-api-key` and offline fixture mode for tests.
- Supported public agency bid pages from an allowlisted config, relative PDF/ZIP link extraction, robots.txt checks by default, host allowlisting, dry-run manifests, and explicit `--download` imports.
- Added construction scoring for NAICS `236xxx`, `237xxx`, `238xxx`, bid/document keywords, and real plan/spec signals.
- Added all-trade/full-project and trade-category tagging for general, civil/site, earthwork/utilities, demolition, concrete, masonry, steel, carpentry, roofing, doors/windows, drywall/framing, finishes, flooring, painting, HVAC, plumbing, electrical, fire protection, low voltage, landscaping, and paving.
- Manifest records include source metadata, document URL, file type, access/robots fields, matched keywords/trades, construction score, rejection reasons, SHA256/download path when imported, and `internal_testing_only=true`.
- Added `mobi-estimating-phase1/tests/test_public_bid_board_pdf_collector.py` with offline tests for SAM fixtures, agency HTML extraction, robots disallow handling, trade classification, manifests, and mocked downloads.
- Added `mobi-estimating-phase1/docs/public-bid-board-pdf-collector.md` and linked it from the real bid-board shakeout guide.
- Verification so far: targeted collector tests passed (`10 passed`), full backend suite passed, dry-run CLI fixture accepted two all-trade/multi-trade documents, `npm run typecheck` passed, `py_compile` passed, and `git diff --check` passed.
- Claude Code was unavailable due session limit during this slice, so Hermes implemented the scoped script/tests/docs directly; initial Codex review found blockers around SAM host allowlisting, source-page robots checks, and default all-trade enforcement, which were fixed with regression tests. Codex rereview passed with no blockers.

**Safety:** no gated bid boards were scraped, no login/paywall/CAPTCHA bypass was attempted, no external forms/messages were sent, no checkout/payment action happened, and no real PDFs were downloaded during tests.

## Canonical domain / checkout URL correction (2026-07-07)

Corrected the public website origin to `https://mobiestimates.com` (no `www`) across
customer-facing marketing materials and checkout return URLs. No fake/staging/preview/
GitHub Pages/portal domains remain in customer-facing routes.

- `marketing-site/config.py`: `CANONICAL_BASE` is now `https://mobiestimates.com`;
  removed stale legacy-host constants. Added `CHECKOUT_BASE` and pointed every
  pricing plan CTA at `https://mobiestimates.com/start?plan=<id>`.
- `marketing-site/generate.py`: pricing-page one-time CTA now uses `CHECKOUT_BASE`
  instead of any hardcoded non-canonical host.
- Regenerated all marketing HTML + `sitemap.xml` + `robots.txt` via
  `python3 marketing-site/generate.py`; canonical/OG/schema/sitemap/robots and CTAs now
  all use `https://mobiestimates.com`.
- Added `src/lib/site-url.ts` (`publicBaseUrl()`): defaults to
  `https://mobiestimates.com`, honors an explicit valid `NEXT_PUBLIC_SITE_URL` for
  local/dev, and rejects known fake/preview/portal hosts.
- Stripe checkout success/cancel URLs (`src/app/api/stripe/checkout/route.ts`,
  `src/app/start/route.ts`), billing portal return URL
  (`src/app/api/stripe/portal/route.ts`), and email claim links
  (`src/lib/email.ts` `SITE_URL`) now use `publicBaseUrl()` instead of the incoming
  request origin / portal default, so a customer who reaches a preview/fake host is
  still returned to the real site.
- Added `scripts/test-canonical-domain.ts` (`npm run test:canonical-domain`): a static
  regression guard that fails if marketing output or checkout/customer-facing code
  reintroduces known legacy, portal-subdomain, or Vercel-preview hosts.
- Verified: `npm run test:canonical-domain` (PASS, 102 files), `npm run typecheck` (clean),
  `npm run build` (success), repository search for stale customer-facing hosts (0 matches),
  and Codex domain/checkout URL review (PASS). No real Stripe Checkout session was started.

**No infrastructure actions were performed:** no DNS changes, no Vercel account/domain
settings, no Stripe dashboard/product/payment-link changes, no payments processed, no
checkout clicked, no emails sent, no files deleted.

## Current system status

Mobi Estimates has a strong local estimating-engine spine and portal/admin scaffolding, but it is **not yet ready to claim full real-document bid-board testing readiness**. The engine can ingest PDFs locally, produce sheet/scope/readiness/BOE/clarification packages, run machine-readable harnesses with an operator guide, report pricing readiness blockers, create safe internal draft estimate versions from generic all-trade scope items that have verified quantities/pricing bases, store explicit all-trade generic cost components on draft estimate line items, generate a read-only customer-safe preview from internal draft estimate versions, summarize sheet/source-type/extraction-confidence/trade-quality weak spots for first real-PDF triage, and separate quantity confidence into present/missing/traceable/test/unclear buckets, and report deterministic generic formula/check readiness that maps supported pricing methods to checks while keeping unknown/missing/unsupported cases blocked. Critical remaining work is to attach traceable takeoff-output placeholders for ready checks and test with actual bid-board documents.

## Completed in this continuous loop

- Inspected the active repo at `/home/hermes/work/mobi-estimates`.
- Confirmed current branch: `feature/customer-safe-revision-history-api-v1`.
- Created `MOBI_AUTOMATION_PLAN.md` as the operating plan for completing the automation system.
- Created this `MOBI_AUTOMATION_PROGRESS.md` as the durable progress tracker requested by Moses.
- Identified and implemented deterministic clarification candidate grouping/prioritization for real bid-board harness/admin use.
- Added candidate `priority_score`, `priority_bucket`, and `priority_rank` to internal clarification candidates.
- Added deterministic groups by priority bucket, severity, trade, source code, and source.
- Added harness outputs for urgent/high candidate counts, top candidate ids, and top groups by trade/source code.
- Added batch aggregate urgent/high clarification counts.
- Improved clarification candidate ids to avoid upstream-order salt in the hash.
- Added `mobi-estimating-phase1/docs/real-bid-board-shakeout-guide.md` explaining single-PDF and batch real-document harness use, report fields, safety flags, fictional test inputs, and interpretation.
- Linked the real bid-board guide from `mobi-estimating-phase1/README.md`.
- Added harness-level pricing readiness metrics for generic pricing scope count, assigned/unassigned methods, ready/not-ready counts, priced/unpriced counts, method counts, and missing quantity/unit-rate/subcontract-quote/allowance blockers.
- Added batch aggregate pricing readiness metrics.
- Added regression tests for pricing readiness fields in the single-PDF and batch harnesses.
- Added `app/generic_estimate_bridge.py` to convert generic scope items with verified quantity/pricing basis into internal draft estimate versions and draft line items.
- Added `POST /api/v1/projects/{project_id}/estimates/generic-draft` as an internal bridge endpoint.
- Added harness stage `generic_estimate_draft_after_test_inputs` and summary outputs for ready/blocked draft estimate scope and line-item counts.
- Added batch aggregate metrics for generic draft estimate line items and locked-false safety flags.
- Added regression tests proving malformed ready pricing basis becomes a blocker instead of a server error/partial failed path.
- Fixed Codex blocker by using `TestClient(app, raise_server_exceptions=False)` in the real-document harness so server errors are reportable stage failures.
- Added explicit `generic_cost_components_v1` line-item component schema for generic draft estimates, with labor/material/equipment/subcontract/other direct buckets and overhead/profit/contingency/markup metadata.
- Added optional `cost_components` passthrough on generic pricing input API/application so verified generic pricing inputs can carry all-trade cost breakdowns.
- Added tests for default component bucketing, explicit all-trade buckets, direct-total mismatch blockers, and malformed non-object component blockers.
- Added `app/proposals/draft_preview.py` as a read-only customer-safe preview builder for internal generic draft estimate versions.
- Added `GET /api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/proposal-preview` for internal/local preview only.
- Added preview safety fields proving no customer delivery, final approval, external messages, payments, proposal creation, or proposal issue is unlocked.
- Integrated generic proposal preview metrics into the real-document harness and bid-board batch runner.
- Added preview leak tests covering forbidden internal cost/margin/rate/source/readiness/reviewer/path terms, including title, description, location, quantity, and unit sanitization.
- Added ownership/version tests for preview access.
- Expanded approved-proposal export smoke tests to include subcontract/other-direct cost terms, margin/markup/rate/source/pricing-basis/reviewer/readiness leak terms, while stripping only HTML `<style>` blocks to avoid CSS false positives.
- Added operator guide sections and metrics for internal generic draft previews, approved-proposal exports, and locked preview/export safety flags.
- Added harness-level document source-type, sheet processing status, OCR/review requirement, and sheet detection confidence metrics.
- Added trade-level quality summaries ranking extraction/source weak spots by missing trusted evidence, low confidence, unclear quantity basis, and open blocking issues.
- Added batch rollups for document source type counts, sheet confidence/OCR/review totals, and top trade quality blockers.
- Updated real bid-board operator docs so first real-PDF failures can be triaged as extraction/source/evidence/quantity/pricing issues.
- Added quantity-confidence summaries distinguishing present, missing, traceable non-test, unclear-basis, and fictional harness-test quantities.
- Added open/resolved quantity requirement counts to harness summaries.
- Added batch quantity rollups and top quantity-confidence weak spots by trade.
- Updated tests and operator docs so fictional `--apply-test-inputs` quantities are reported as smoke-test inputs, not real estimating readiness.
- **(Claude Code implementation)** Finished wiring deterministic generic formula/check readiness into the harness. `_generic_formula_check_for_item` / `_generic_formula_check_summary` map `unit_rate_needed → quantity_times_unit_rate_check`, `quote_based → lump_sum_or_scope_quantity_check`, and `allowance → allowance_basis_check`, while keeping unknown/unassigned/unsupported methods blocked (`unsupported_pricing_method`).
- **(Claude Code implementation)** Formula/check summaries distinguish ready vs blocked and surface `missing_quantity`, `unclear_quantity_basis`, and `test_quantity_only` blockers; aggregate by trade, method, and blocker; and never mark `harness_test_only_*` items as ready.
- **(Claude Code implementation)** Exposed formula/check fields in single-PDF `summary.outputs` (`formula_check_*`) and batch rollups (`total_formula_check_*`, `formula_check_method_counts`, `formula_check_blocker_counts`, `top_formula_check_by_trade`).
- **(Claude Code implementation)** Added harness/batch regression tests and updated `docs/real-bid-board-shakeout-guide.md`, documenting the method→check mapping and warning that a ready check is a readiness signal only — not a measurement, rate, price, approved estimate, or customer deliverable.

## Recently completed before this loop

- Register-backed readiness hardening.
- Internal clarification package API.
- Clarification package reporting in real-document and batch harnesses.
- Admin visibility for clarification candidates.
- Offline admin clarification workflow harness.
- Full-path backend → owner-review → admin-helper clarification safety regression.
- Codex reviews passed for recent clarification/admin safety slices.

## Bugs found

- Historical/active docs were fragmented across `ROADMAP.md`, `TODO.md`, engine docs, and local commits; there was no root `MOBI_AUTOMATION_PLAN.md` or `MOBI_AUTOMATION_PROGRESS.md` tracker.
- Existing roadmap is portal-launch oriented; it does not fully track the estimating automation completion standard for real bid-board testing.
- Clarification candidate IDs previously included entry index salt; this could churn if upstream register ordering changed.
- The engine had real-document harnesses but no dedicated operator guide explaining safe usage and report interpretation.
- Harness pricing metrics initially read the paginated scope list, which omits detailed `trade_data`; pricing method/ready counts appeared as zero even after pricing prep/test inputs.
- Codex found the harness could still raise unhandled server exceptions because `TestClient` used the default `raise_server_exceptions=True`.
- Codex found generic estimate bridge validation initially happened after draft cost-book/estimate records were created, so malformed ready pricing basis could leave partial records if it raised.
- Codex found malformed `pricing_basis.cost_components` arrays/strings could silently default into a priced draft line instead of becoming blockers.
- Codex found the initial draft preview sanitizer did not forbid the term `source` and copied quantity/unit directly into preview output.
- Quantity/source reporting regression expectation initially over-counted one trade quality blocker; the implementation correctly summed missing evidence + unclear quantity basis + open blocking issues.
- Claude Code branch review found the customer revision history panel contract was mismatched: engine `customer-history` returned `action/status/trade/sheet_refs/follow_up/latest_version_at`, while the portal expected `requested_action_label/status_label/trade_label/sheet_ref/follow_up_label/latest_version_created_at`, causing visible blank labels.

## Bugs fixed

- Added root-level automation plan/progress trackers to unify the estimating automation completion loop.
- Added deterministic clarification prioritization/grouping so real-document reports can surface the highest-impact blockers first.
- Removed entry-order salt from clarification candidate IDs so IDs are more stable for the same source entry.
- Added the real bid-board shakeout operator guide and README link.
- Updated the real-document harness to refresh detailed scope item records after test inputs so pricing readiness summaries can see `trade_data.pricing_method`, `pricing_ready`, and `pricing_basis`.
- Changed the real-document harness to use `TestClient(app, raise_server_exceptions=False)` so unexpected server errors become JSON/reportable failed stages instead of aborting report generation.
- Changed generic estimate bridge to validate/build draft line candidates before creating persistent draft records, and to classify malformed ready pricing basis as a blocked scope item.
- Fixed a duplicate batch summary key and restored `total_unpriced_scope_item_count` / `total_missing_unit_rate_pricing_blocker_count` in batch reporting.
- Added `invalid_cost_components` blocking so malformed non-object component payloads never become draft estimate line items.
- Added `cost_component_total_mismatch` blocking so explicit direct bucket totals must reconcile to the pricing-basis amount.
- Added `source` to draft-preview forbidden terms and sanitized quantity/unit before returning `customer_safe_preview`.
- Added regressions proving previews do not create proposal rows or unlock customer delivery, final approval, external messages, payments, proposal creation, or proposal issue.
- Fixed proposal export leak-test false positives by checking plain leak terms as whole words and stripping only non-visible HTML CSS before scanning.
- Fixed the trade-quality summary regression expectation so tests match the intended machine-readable quality blocker formula.
- Fixed the customer revision history field contract by adding a strict portal-side normalizer in `src/app/portal/projects/[id]/revisionHistory.ts`, remapping engine-shaped customer-history rows to the customer-safe `*_label` view model and collapsing `sheet_refs[]` to scalar `sheet_ref` without raw field passthrough.

## Current blockers

- No real bid-board PDFs are currently available under `/home/hermes`; measured real-document accuracy is blocked until documents are supplied.
- PR #51 was pushed, Vercel preview checks passed, merged to `main`, and production Vercel deployment statuses for `mobi-portal` and `mobi-marketing-site` completed successfully. Browser verification loaded the production `mobi-portal` deployment; `mobi-marketing-site` production deployment redirected to Vercel login/protection.
- PR #50 was closed as superseded by PR #51.
- Local Vercel CLI access is not authenticated: `npx --yes vercel@latest whoami` reports no existing credentials. GitHub CLI is authenticated and can push/update PRs.
- Final estimate delivery, external messages/emails, pricing changes, billing/payment/refund actions, legal terms, DNS/domain changes, destructive data/file operations, and live checkout actions remain approval-gated.

## Files changed in this loop

- `MOBI_AUTOMATION_PLAN.md`
- `MOBI_AUTOMATION_PROGRESS.md`
- `mobi-estimating-phase1/README.md`
- `mobi-estimating-phase1/docs/real-bid-board-shakeout-guide.md`
- `mobi-estimating-phase1/app/clarification_package.py`
- `mobi-estimating-phase1/app/generic_estimate_bridge.py`
- `mobi-estimating-phase1/app/generic_pricing_inputs.py`
- `mobi-estimating-phase1/app/main.py`
- `mobi-estimating-phase1/app/routers_estimate_bridge.py`
- `mobi-estimating-phase1/app/routers_pricing_prep.py`
- `mobi-estimating-phase1/app/proposals/draft_preview.py`
- `mobi-estimating-phase1/scripts/real_document_harness.py`
- `mobi-estimating-phase1/scripts/bid_board_batch_shakeout.py`
- `mobi-estimating-phase1/tests/test_clarification_package_api.py`
- `mobi-estimating-phase1/tests/test_generic_estimate_bridge_api.py`
- `mobi-estimating-phase1/tests/test_real_document_harness.py`
- `mobi-estimating-phase1/tests/test_bid_board_batch_shakeout.py`
- `src/app/portal/projects/[id]/actions.ts`
- `src/app/portal/projects/[id]/revisionHistory.ts`
- `scripts/test-customer-revision-portal-safety.ts`
- `mobi-estimating-phase1/docs/real-bid-board-shakeout-guide.md`

## Verification completed

- Clarification prioritization targeted backend tests — passed.
- Full backend suite after clarification prioritization — passed.
- Frontend typecheck/build after clarification prioritization — passed.
- Codex review — PASS for clarification prioritization and docs safety.
- Pricing readiness targeted harness tests: `tests/test_real_document_harness.py` and `tests/test_bid_board_batch_shakeout.py` — passed.
- Generic estimate bridge targeted tests: `tests/test_generic_estimate_bridge_api.py`, `tests/test_real_document_harness.py`, `tests/test_bid_board_batch_shakeout.py`, `tests/test_generic_pricing_prep_api.py`, `tests/test_pricing_e2e.py`, `tests/test_proposals.py` — passed.
- Full backend suite: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification: `npm run typecheck && npm run build` — passed.
- Codex review after blocker fixes — PASS.
- Cost component schema targeted tests: `tests/test_generic_estimate_bridge_api.py` and `tests/test_generic_pricing_prep_api.py` — passed.
- Full backend suite after cost component schema: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after cost component schema: `npm run typecheck && npm run build` — passed.
- Codex cost component schema rereview — PASS.
- Safe draft proposal preview targeted tests: `tests/test_generic_estimate_bridge_api.py`, `tests/test_real_document_harness.py`, `tests/test_bid_board_batch_shakeout.py`, and `tests/test_proposals.py` — passed.
- Full backend suite after safe draft proposal preview: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after safe draft proposal preview: `npm run typecheck && npm run build` — passed.
- Codex safe draft proposal preview rereview — PASS.
- Safe preview/export docs targeted tests: `tests/test_proposals.py`, `tests/test_generic_estimate_bridge_api.py`, `tests/test_real_document_harness.py`, and `tests/test_bid_board_batch_shakeout.py` — passed.
- Full backend suite after safe preview/export docs: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after safe preview/export docs: `npm run typecheck && npm run build` — passed.
- Codex safe preview/export docs review — PASS.
- Confidence/source reporting targeted tests: `tests/test_real_document_harness.py` and `tests/test_bid_board_batch_shakeout.py` — passed.
- Full backend suite after confidence/source reporting: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after confidence/source reporting: `npm run typecheck && npm run build` — passed.
- Codex confidence/source reporting review — PASS.
- Quantity-confidence targeted tests: `tests/test_real_document_harness.py` and `tests/test_bid_board_batch_shakeout.py` — passed.
- Full backend suite after quantity-confidence reporting: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after quantity-confidence reporting: `npm run typecheck && npm run build` — passed.
- Codex quantity-confidence review — PASS.
- Generic formula/check targeted tests (Claude Code + Hermes verification): `/tmp/mobi-estimating-venv/bin/pytest -q tests/test_real_document_harness.py tests/test_bid_board_batch_shakeout.py` — 11 passed.
- Full backend suite after generic formula/check (Claude Code + Hermes verification): `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend verification after generic formula/check (Hermes): `npm run typecheck && npm run build` — passed.
- Vercel/GitHub deployment audit fact (2026-07-07): local `vercel` binary is absent and `npx --yes vercel@latest whoami` reports no existing credentials; GitHub CLI is authenticated (`gh auth status` → `Mosescerva9`) and GitHub/Vercel status contexts still exist; production deployment has **not** been completed.
- Codex review of generic formula/check — PASS.
- Claude Code branch quality review found one blocker before PR: customer revision history UI expected `*_label` fields while engine customer-history returned `action`, `status`, `trade`, `sheet_refs`, `follow_up`, and `latest_version_at`.
- Claude Code fixed the revision-history field contract by adding a whitelisted portal normalizer and regression coverage; Hermes verified `npm run test:customer-revision-portal`, `npm run test:deliverable-gate`, `npm run test:admin-revision-workflow`, `npm run test:admin-clarification-package`, `npm run typecheck`, and `npm run build`.
- Codex rereviewed the branch after the fix — PASS; no PR-readiness blockers found in the reviewed snapshot.
- Pushed `feature/customer-safe-revision-history-api-v1` and opened PR #51: "Complete customer-safe revision and bid-board automation readiness stack".
- Vercel preview checks for PR #51 passed for both `mobi-portal` and `mobi-marketing-site`; PR #51 was mergeable and merged to `main` at commit `270bf9ebf2823b16eebacba845168f154d1000f6`.
- Production deployment statuses completed successfully for the portal and marketing Vercel projects; browser verification loaded the portal deployment while the marketing preview deployment redirected to Vercel login/protection.
- Closed PR #50 as superseded by PR #51.

## Next step

Add takeoff-output placeholders only when traceable; otherwise block with customer-safe clarification:

1. Attach traceable takeoff-output placeholders only to formula/check-ready items with verified, non-test measurement support.
2. Keep unsupported/missing/test-only measurement cases blocked or clarification-ready.
3. Do not invent measurements, rates, prices, approvals, delivery, messages, or payments.
4. Add harness/batch/doc coverage and keep safety flags locked false.
5. Update this progress file after Hermes verification and Codex review.

## Ready for real document and bid-board scope testing?

**Not yet.**

The system now has local harnesses, safety gates, prioritized clarification reporting, an operator guide, pricing readiness metrics, safe generic-scope-to-draft-estimate bridge, explicit all-trade generic cost components, a read-only customer-safe preview for generic draft estimates, expanded preview/export safety docs/tests, extraction/source/trade-quality reporting, and quantity-confidence reporting, but it should not be marked ready until at minimum:

- common generic scope formula/check readiness can distinguish supported traceable checks from unsupported/missing measurement cases,
- real bid-board PDFs have been supplied and at least one full local shakeout has been run,
- customer-facing estimate output contracts are proven safe and complete.
