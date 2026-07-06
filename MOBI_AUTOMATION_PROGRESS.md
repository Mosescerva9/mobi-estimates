# Mobi Automation Progress

_Last updated: 2026-07-06_

## Current system status

Mobi Estimates has a strong local estimating-engine spine and portal/admin scaffolding, but it is **not yet ready to claim full real-document bid-board testing readiness**. The engine can ingest PDFs locally, produce sheet/scope/readiness/BOE/clarification packages, run machine-readable harnesses with an operator guide, and now report pricing readiness blockers. Critical remaining work is to bridge generic scope readiness into deterministic estimate-version/proposal output, improve quantity/takeoff automation, and test with actual bid-board documents.

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

## Bugs fixed

- Added root-level automation plan/progress trackers to unify the estimating automation completion loop.
- Added deterministic clarification prioritization/grouping so real-document reports can surface the highest-impact blockers first.
- Removed entry-order salt from clarification candidate IDs so IDs are more stable for the same source entry.
- Added the real bid-board shakeout operator guide and README link.
- Updated the real-document harness to refresh detailed scope item records after test inputs so pricing readiness summaries can see `trade_data.pricing_method`, `pricing_ready`, and `pricing_basis`.

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
- `mobi-estimating-phase1/scripts/real_document_harness.py`
- `mobi-estimating-phase1/scripts/bid_board_batch_shakeout.py`
- `mobi-estimating-phase1/tests/test_clarification_package_api.py`
- `mobi-estimating-phase1/tests/test_real_document_harness.py`
- `mobi-estimating-phase1/tests/test_bid_board_batch_shakeout.py`

## Verification completed

- Clarification prioritization targeted backend tests — passed.
- Full backend suite after clarification prioritization — passed.
- Frontend typecheck/build after clarification prioritization — passed.
- Codex review — PASS for clarification prioritization and docs safety.
- Pricing readiness targeted harness tests: `tests/test_real_document_harness.py` and `tests/test_bid_board_batch_shakeout.py` — passed.

## Next step

Bridge generic all-trade scope readiness into deterministic estimate-version creation:

1. Inspect existing estimate-version/proposal schemas and pricing services.
2. Define a safe draft mapping from generic scope items with verified quantities/pricing bases into deterministic estimate-version draft data.
3. Keep unready scope blocked with explicit missing quantity/rate/quote/allowance reasons.
4. Prove no customer delivery, approval, billing, messaging, or final estimate side effects.
5. Update this progress file and commit after verification.

## Ready for real document and bid-board scope testing?

**Not yet.**

The system now has local harnesses, safety gates, prioritized clarification reporting, an operator guide, and pricing readiness metrics, but it should not be marked ready until at minimum:

- generic scope readiness can produce a deterministic priced estimate/proposal package or clearly state why not,
- real bid-board PDFs have been supplied and at least one full local shakeout has been run,
- customer-facing estimate output contracts are proven safe and complete.
