# Mobi Automation Progress

_Last updated: 2026-07-07_

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
- PR #50 still shows old Vercel build-rate-limit failure contexts; now that Vercel Pro is available, this is an integration item to re-trigger/recheck, not a reason to stop local work.
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
