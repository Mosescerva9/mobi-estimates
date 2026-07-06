# Mobi Automation Progress

_Last updated: 2026-07-06_

## Current system status

Mobi Estimates has a strong local estimating-engine spine and portal/admin scaffolding, but it is **not yet ready to claim full real-document bid-board testing readiness**. The engine can ingest PDFs locally, produce sheet/scope/readiness/BOE/clarification packages, run machine-readable harnesses with an operator guide, report pricing readiness blockers, create safe internal draft estimate versions from generic all-trade scope items that have verified quantities/pricing bases, and store explicit all-trade generic cost components on draft estimate line items. Critical remaining work is to complete the final proposal/customer-safe output bridge, improve quantity/takeoff automation, and test with actual bid-board documents.

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

## Current blockers

- No real bid-board PDFs are currently available under `/home/hermes`; measured real-document accuracy is blocked until documents are supplied.
- PR #50 was previously blocked by external Vercel build-rate limits; downstream automation changes are being kept local/stacked until that clears.
- Final estimate delivery, production deployments, external messages/emails, pricing changes, billing/payment/refund actions, legal terms, DNS/domain changes, destructive data/file operations, and live checkout actions remain approval-gated.

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
- `mobi-estimating-phase1/scripts/real_document_harness.py`
- `mobi-estimating-phase1/scripts/bid_board_batch_shakeout.py`
- `mobi-estimating-phase1/tests/test_clarification_package_api.py`
- `mobi-estimating-phase1/tests/test_generic_estimate_bridge_api.py`
- `mobi-estimating-phase1/tests/test_real_document_harness.py`
- `mobi-estimating-phase1/tests/test_bid_board_batch_shakeout.py`

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

## Next step

Connect automation-ready draft estimate versions to safe proposal-package preview generation:

1. Define a customer-safe preview contract for internal draft estimate versions that includes scope notes, inclusions, exclusions, assumptions, and blockers/clarifications.
2. Keep cost/margin/rate/source/readiness/internal reviewer data out of customer-safe preview text.
3. Add tests proving preview generation does not approve, issue, deliver, send, bill, or unlock final estimate status.
4. Integrate preview status/summary into harness reporting only as internal/test output.
5. Update this progress file and commit after verification.

## Ready for real document and bid-board scope testing?

**Not yet.**

The system now has local harnesses, safety gates, prioritized clarification reporting, an operator guide, pricing readiness metrics, safe generic-scope-to-draft-estimate bridge, and explicit all-trade generic cost components, but it should not be marked ready until at minimum:

- the final proposal/customer-safe output bridge is complete and leak-tested,
- real bid-board PDFs have been supplied and at least one full local shakeout has been run,
- customer-facing estimate output contracts are proven safe and complete.
