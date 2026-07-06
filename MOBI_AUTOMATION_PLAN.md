# Mobi Estimates Automation Plan

_Last updated: 2026-07-06_

## Mission

Build Mobi Estimates into an automation-first, all-trade / whole-project estimating system that can ingest real contractor project files from bid boards, extract traceable scope, produce deterministic quantities/pricing packages, generate contractor-ready bid outputs, and route uncertainty into customer clarification/revision loops instead of hidden guesses.

## Non-negotiable safety gates

- No final construction estimate is delivered without explicit approval for that product behavior.
- No external customer messages, emails, payment/refund actions, pricing changes, production deployments, DNS changes, or destructive data/file operations without the required approval gate.
- Customer-facing surfaces must not expose raw engine payloads, internal notes, staff actors, raw blocker data, readiness internals, pricing/reprice wording, billing/delivery/approval controls, or unknown raw enums.
- Unknowns become assumptions, exclusions, clarification questions, or blockers — never hidden guesses.
- Long-term operating model: customer review/revision is the durable human feedback loop; internal owner review is Phase-0 safety scaffolding, not the target business model.

## Current implementation state

| Area | Status | Notes |
|---|---:|---|
| Portal upload/project intake | In progress | Customer project intake and file upload exist; production verification/migration status still separate from engine readiness. |
| PDF intake and sheet processing | Built locally | FastAPI engine ingests PDFs, splits sheets, stores text/images, supports sheet verification. OCR/vision accuracy on real bid-board PDFs is not yet proven. |
| Scope extraction spine | Built locally | Trade coverage, trade census, generic scope candidates, QA findings, and scope items exist. Real extraction quality still needs bid-board testing. |
| Quantity backbone | Built locally | Quantity requirements and explicit quantity input application exist. Automated takeoff/measurement from drawings is not yet proven. |
| Pricing spine | Partially built | Phase 4 deterministic pricing engine exists, plus generic pricing-prep/input readiness, explicit all-trade generic cost components, and a safe generic-scope → internal draft estimate-version bridge. Full final proposal/customer output bridge still needs completion. |
| BOE / assumptions / exclusions | Built locally | BOE and structured assumptions/exclusions/open-questions register exist and are readiness-gated. |
| Readiness gates | Built locally | Provenance/confidence/register/clarification blockers are included; customer delivery remains locked. |
| Clarification package | Built locally | Internal customer-safe question candidates, admin display, harness reporting, and full-path safety regressions exist. |
| Owner/admin review | Built locally | Internal owner-review package and admin visibility exist. This is temporary safety scaffolding. |
| Customer revision loop | Built locally | Customer-safe revision history/submission and internal rescope-version safety work exist locally. |
| Proposal/customer output | Partial | Engine has Phase 5 proposal generation for approved estimate versions, plus an internal customer-safe preview for generic draft estimates. The automation chain to approved contractor-ready priced proposals still needs final output hardening. |
| Real-document harness | Built locally | Single-PDF and batch bid-board harnesses exist with safety/reporting semantics. Need real PDFs and stronger output-readiness metrics. |
| Documentation/progress tracking | Active | This file plus `MOBI_AUTOMATION_PROGRESS.md` are the operating tracker for the continuous automation loop. |

## Completion standard for real bid-board testing

The system is ready for real document/full-scope testing only when all critical items below are complete and verified locally:

1. A contractor project file/bid-board PDF can be uploaded into the engine harness.
2. The system extracts sheets, trade coverage, scope candidates, evidence, and blockers.
3. Scope items include traceable source references or explicit blocker/clarification entries.
4. Quantities are either deterministic/traceable or explicitly blocked as missing/uncertain.
5. Pricing inputs/rates/allowances are traceable, deterministic, or explicitly blocked.
6. BOE, assumptions, exclusions, and open questions are produced in a structured form.
7. A contractor-ready estimate/proposal package can be generated from approved/priced scope without leaking internal cost/margin data.
8. All outputs are machine-checkable by harness summaries and fail nonzero when critical stages fail.
9. Admin/customer boundaries are protected by tests and static safety harnesses.
10. Usage documentation explains how to run single-PDF and batch bid-board tests.

## Critical work plan

### Phase A — Real-document readiness infrastructure

- [x] Single-PDF real-document harness with nonzero failure semantics.
- [x] Batch bid-board runner with aggregate summaries.
- [x] Readiness reporting for provenance/confidence/register blockers.
- [x] Clarification package reporting in harness summaries.
- [x] Add clarification candidate grouping/prioritization for high-volume real PDFs.
- [x] Add harness output report section for top blocker groups and first questions to answer.
- [x] Add operator guide for running real bid-board PDFs and interpreting reports.

### Phase B — Extraction and scope reliability

- [x] Generic all-trade scope candidate lane.
- [x] Coverage matrix and trade census.
- [x] QA findings and readiness blockers.
- [ ] Improve extraction/provider confidence reporting on real documents.
- [ ] Add real-document golden fixtures once bid-board PDFs are supplied.
- [ ] Add trade-by-trade extraction quality scoring from harness outputs.
- [ ] Add sheet/spec/source-type summaries for specs and non-drawing documents.

### Phase C — Quantity/takeoff automation

- [x] Quantity requirement backbone.
- [x] Explicit quantity input application path.
- [ ] Add automatic quantity derivation confidence summaries by trade/item.
- [ ] Add formulas/checks for common generic scopes.
- [ ] Add takeoff-output placeholders only when traceable; otherwise block with customer-safe clarification.
- [ ] Add real-PDF measurement/takeoff smoke tests once documents are available.

### Phase D — Pricing and estimate generation

- [x] Deterministic Phase 4 pricing engine exists.
- [x] Generic pricing prep and input-readiness path exists.
- [x] Bridge generic all-trade scope readiness into deterministic estimate-version creation.
- [x] Add explicit all-trade cost component schema: labor/material/equipment/subcontract/other/overhead/profit/contingency/markup.
- [ ] Add missing-rate/allowance blockers that become BOE assumptions or clarification candidates.
- [x] Add harness-level pricing readiness/output metrics.

### Phase E — Contractor-ready outputs

- [x] Phase 5 proposal generator exists for approved estimate versions.
- [x] Connect automation-ready estimate versions to proposal-package preview generation.
- [x] Add customer-safe estimate output contract for inclusions/exclusions/assumptions/scope notes.
- [ ] Add export smoke tests that prove no internal cost/margin/rate details leak.
- [ ] Add operator docs for previewing/exporting test bid packages.

### Phase F — Customer review/revision loop

- [x] Customer-safe revision history panel/API.
- [x] Customer-safe revision submission API/form.
- [x] Internal rescope/version safety tests.
- [x] Internal clarification candidate package.
- [ ] Add approved customer clarification communication workflow later, under explicit external-message approval gate.
- [ ] Add automated customer response ingestion into revision/clarification pipeline.

### Phase G — Portal/production integration

- [ ] Recheck/merge blocked PR #50 once Vercel build-rate limit clears.
- [ ] Rebase and push stacked local automation/customer-revision branch after PR #50 clears.
- [ ] Run full portal typecheck/build and backend suite after rebase.
- [ ] Verify production migrations/env/config before any production merge/deploy.
- [ ] Run approved production E2E with temporary data only after required gates are satisfied.

## Current highest-impact next task

**Add export smoke tests and operator docs for safe test bid-package previews.**

Why this is next: the engine now has approved-estimate proposal exports and an internal customer-safe preview for generic draft estimates, but the operator guide does not yet explain how to preview/export test bid packages or how to distinguish an internal preview from a final deliverable. The next gap is documentation plus regression coverage that proves preview/export surfaces do not leak internal cost, margin, rate, source, readiness, reviewer, approval, billing, or delivery terms.

Acceptance criteria:

- Operator docs explain how to run the internal draft preview and approved-proposal exports in local/testing mode.
- Tests cover JSON-shaped preview output and existing exports for forbidden internal terms.
- Harness/batch reports keep preview/export indicators separate from final proposal delivery.
- Docs explicitly state previews are not final estimates and cannot be sent/delivered without approval.

## Current blockers

- Real bid-board PDF inputs have not been provided/found under `/home/hermes`; measured real-document accuracy remains blocked until documents are available.
- PR #50 remains externally blocked by Vercel build-rate limit, so downstream local commits should remain local/stacked unless the rate limit clears.
- Production deployment, payment actions, external messages, legal/pricing changes, and final estimate delivery remain approval-gated.
