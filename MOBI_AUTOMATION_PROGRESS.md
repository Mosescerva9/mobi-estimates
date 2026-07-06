# Mobi Automation Progress

_Last updated: 2026-07-06_

## Current system status

Mobi Estimates has a strong local estimating-engine spine and portal/admin scaffolding, but it is **not yet ready to claim full real-document bid-board testing readiness**. The engine can ingest PDFs locally, produce sheet/scope/readiness/BOE/clarification packages, and run machine-readable harnesses with an operator guide. Critical remaining work is to bridge generic scope readiness into deterministic estimate-version/proposal output, improve quantity/takeoff automation, add pricing readiness/output metrics, and test with actual bid-board documents.

## Completed in this continuous loop

- Inspected the active repo at `/home/hermes/work/mobi-estimates`.
- Confirmed current branch: `feature/customer-safe-revision-history-api-v1`.
- Confirmed latest local automation commits through `849246c Add full-path clarification safety regression` before this loop.
- Inspected current roadmap/TODO/README and estimating-engine docs/code/tests.
- Created `MOBI_AUTOMATION_PLAN.md` as the operating plan for completing the automation system.
- Created this `MOBI_AUTOMATION_PROGRESS.md` as the durable progress tracker requested by Moses.
- Identified and implemented deterministic clarification candidate grouping/prioritization for real bid-board harness/admin use.
- Added candidate `priority_score`, `priority_bucket`, and `priority_rank` to internal clarification candidates.
- Added deterministic groups by priority bucket, severity, trade, source code, and source.
- Added harness outputs for urgent/high candidate counts, top candidate ids, and top groups by trade/source code.
- Added batch aggregate urgent/high clarification counts.
- Added backend and harness regression tests.
- Improved clarification candidate ids to avoid upstream-order salt in the hash.
- Added `mobi-estimating-phase1/docs/real-bid-board-shakeout-guide.md` explaining single-PDF and batch real-document harness use, report fields, safety flags, fictional test inputs, and interpretation.
- Linked the real bid-board guide from `mobi-estimating-phase1/README.md`.
- Ran targeted backend tests, the full backend suite, frontend typecheck/build, and Codex review for the prioritization slice.

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

## Bugs fixed

- Added root-level automation plan/progress trackers to unify the estimating automation completion loop.
- Added deterministic clarification prioritization/grouping so real-document reports can surface the highest-impact blockers first.
- Removed entry-order salt from clarification candidate IDs so IDs are more stable for the same source entry.
- Added the real bid-board shakeout operator guide and README link.

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

- Targeted backend tests: `tests/test_clarification_package_api.py`, `tests/test_real_document_harness.py`, `tests/test_bid_board_batch_shakeout.py`, `tests/test_owner_review_package_api.py` — passed.
- Full backend suite: `/tmp/mobi-estimating-venv/bin/pytest -q` — passed.
- Frontend typecheck: `npm run typecheck` — passed.
- Frontend build: `npm run build` — passed.
- Codex review — PASS for clarification prioritization and docs safety.

## Next step

Add harness-level pricing readiness/output metrics:

1. Inspect current generic pricing prep/input data shapes.
2. Add harness summary fields for pricing-method readiness, missing pricing inputs, and priced-vs-unpriced scope counts.
3. Add batch aggregate pricing readiness blocker counts.
4. Add tests.
5. Update this progress file and commit.

## Ready for real document and bid-board scope testing?

**Not yet.**

The system now has local harnesses, safety gates, prioritized clarification reporting, and an operator guide, but it should not be marked ready until at minimum:

- pricing readiness/output metrics are included in harness reports,
- generic scope readiness can produce a deterministic priced estimate/proposal package or clearly state why not,
- real bid-board PDFs have been supplied and at least one full local shakeout has been run.
