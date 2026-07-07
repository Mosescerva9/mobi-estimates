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
| Real-document harness | Built locally | Single-PDF and batch bid-board harnesses exist with safety/reporting semantics. Public SAM.gov/agency bid-board PDF discovery/import pipeline exists for creating a compliant internal test corpus. Need real PDF runs and stronger output-readiness metrics. |
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
- [x] Add public SAM.gov + agency bid-page PDF discovery/import pipeline with robots/allowlist safeguards and all-trade construction filtering.

### Phase B — Extraction and scope reliability

- [x] Generic all-trade scope candidate lane.
- [x] Coverage matrix and trade census.
- [x] QA findings and readiness blockers.
- [x] Improve extraction/provider confidence reporting on real documents.
- [x] Add real-document golden fixtures once bid-board PDFs are supplied.
- [x] Add Golden Set v2 drawing corpus with complete plan PDFs and source-backed measured quantity baseline.
- [x] Add trade-by-trade extraction quality scoring from harness outputs.
- [x] Add sheet/spec/source-type summaries for specs and non-drawing documents.

### Phase C — Quantity/takeoff automation

- [x] Quantity requirement backbone.
- [x] Explicit quantity input application path.
- [x] Add automatic quantity derivation confidence summaries by trade/item.
- [x] Add formulas/checks for common generic scopes.
- [ ] Add takeoff-output placeholders only when traceable; otherwise block with customer-safe clarification.
- [x] Add real-PDF measurement/takeoff smoke tests once documents are available.
- [ ] Add OCR/vision-based sheet table and drawing text extraction so image-heavy plan PDFs produce scope items and measured quantities.
- [x] Add AutoResearch v1 scoring/guard/ledger scaffold so Golden Set v2 can become a locked evaluator for controlled experiments.
- [x] Add first controlled one-artifact experiment runner for OCR/sheet-text extraction against Golden Set v2.
- [x] Add approved agent proposal step so Claude/Codex can generate candidate patches through the runner.

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
- [x] Add export smoke tests that prove no internal cost/margin/rate details leak.
- [x] Add operator docs for previewing/exporting test bid packages.

### Phase F — Customer review/revision loop

- [x] Customer-safe revision history panel/API.
- [x] Customer-safe revision submission API/form.
- [x] Internal rescope/version safety tests.
- [x] Internal clarification candidate package.
- [ ] Add approved customer clarification communication workflow later, under explicit external-message approval gate.
- [ ] Add automated customer response ingestion into revision/clarification pipeline.

### Phase G — Portal/production integration

- [x] Re-trigger/recheck PR #50 Vercel contexts now that Vercel Pro is available; PR #50 was closed as superseded by PR #51.
- [x] Push stacked local automation/customer-revision branch after Claude/Codex review and local verification.
- [x] Run full portal typecheck/build and backend suite after rebase/push.
- [x] Verify production Vercel deployment status after merge.
- [ ] Run approved production E2E with temporary data only after required gates are satisfied.

## Current highest-impact next task

**Top priority (two parallel tracks):**

1. **Golden Set v1 + extraction-eval track.** v1 is now built and has run against 3 real public project-manual PDFs. Current result: `3/3` harness/evaluation passes for current generic trade-census expectations, safety locks closed, trade recall `1.0`, scope keyword coverage `1.0`, `36` false-positive trade detections, `0` key quantity checks, and all 3 projects benchmark-ineligible because addenda/drawing completeness and source-measured quantities are not established. Next step: upgrade the corpus with complete drawing sets and 3–5 hand-measured source-backed quantities per project, then tighten false-positive trade scoring.
2. **Source registry / collection track.** Run the public bid-board PDF collector against approved public sources, then feed accepted PDFs into the batch shakeout and into the golden-set manifest.

**Run the public bid-board PDF collector against approved public sources, then feed accepted PDFs into the batch shakeout.**

Why this is next: the collector can now discover/import SAM.gov resource links and allowlisted public agency bid-page PDFs with construction/all-trade filtering, source metadata, robots safeguards, and internal-testing-only manifests. The next step is to create a first real PDF corpus, run `bid_board_batch_shakeout.py`, and use the report to prioritize extraction/quantity/pricing fixes.

Acceptance criteria:

- Source config uses public/authorized SAM.gov or agency pages only.
- Accepted PDFs/ZIPs have source metadata, SHA256, construction score, matched trades, and `internal_testing_only=true`.
- Batch shakeout runs on the imported folder and produces a report with no delivery/approval/payment/message flags unlocked.

### Completed: Add formulas/checks for common generic scopes (Claude Code implementation)

Implemented by Claude Code, verified by Hermes:

- `_generic_formula_check_for_item` / `_generic_formula_check_summary` in `scripts/real_document_harness.py` map supported pricing methods to deterministic checks (`unit_rate_needed → quantity_times_unit_rate_check`, `quote_based → lump_sum_or_scope_quantity_check`, `allowance → allowance_basis_check`) and keep unknown/unassigned/unsupported methods blocked.
- Blockers distinguish `missing_quantity`, `unclear_quantity_basis`, `test_quantity_only`, and `unsupported_pricing_method`; summaries aggregate by trade, method, and blocker and separate ready vs blocked.
- Wired into single-PDF `summary.outputs` and batch rollups in `scripts/bid_board_batch_shakeout.py`.
- No measurements, rates, pricing, approvals, delivery, messages, or payments are produced; harness safety flags stay locked false and ready checks are documented as readiness signals only.

## Current blockers

- Real bid-board PDF inputs have not been provided/found under `/home/hermes`; measured real-document accuracy remains blocked until documents are available.
- Vercel/GitHub deployment audit (2026-07-07): Vercel CLI is not installed/authenticated as a local `vercel` binary; `npx --yes vercel@latest whoami` reports no existing credentials. GitHub CLI is authenticated (`gh auth status` → account `Mosescerva9`). PR #51 was pushed, Vercel preview checks passed, PR #51 merged, and production Vercel deployment statuses for `mobi-portal` and `mobi-marketing-site` completed successfully. Local browser verification loaded `mobi-portal` production deployment; `mobi-marketing-site` production deployment redirected to Vercel login/protection.
- PR #50 was closed as superseded by PR #51 after the Pro-plan Vercel checks passed on PR #51.
- Production deployment, payment actions, external messages, legal/pricing changes, and final estimate delivery remain approval-gated.
