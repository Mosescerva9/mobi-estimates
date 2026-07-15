# Mobi Estimates pilot master plan

Updated: 2026-07-15T02:13:33Z
Branch: `pilot-readiness-ai-assisted-mvp`

## Mission
Prepare Mobi Estimates to accept a small number of real contractors for AI-assisted, human-reviewed estimates with 24–48 hour turnaround, strong QA, and structured learning from every verified contractor correction.

Mobi must not be presented as fully autonomous during the pilot. The service experience should feel software-driven while preserving human approval before final estimate delivery.

## Current system inventory

### Customer-facing portal
- Next.js 15 App Router portal with Supabase Auth and RLS-backed project/company data.
- Customer project creation and direct private-storage uploads exist.
- Customer project detail has upload retry/add-files and a revision request surface.
- Pricing/checkout/onboarding flows exist but payment readiness remains gated by Stripe configuration and approval-sensitive billing checks.

### Internal estimator/admin workflow
- Admin project page includes EstimateJob panels, document-register visibility, workflow status actions, event timeline/filtering, and deliverable upload gates.
- EstimateJob RPC handoffs exist for document review, takeoff start, takeoff completion, pricing review, QA, and owner revision loops.
- Final delivery remains locked behind explicit owner/final-delivery gates.

### Estimating engine
- FastAPI backend in `mobi-estimating-phase1/app` with extraction, scope, quantity, pricing, proposal, review, customer revision, and capability registry modules.
- Trade modules exist for generic scope, painting, and demo concrete.
- Extraction providers include mock/OpenAI-provider scaffolding and caching.
- Pricing/assembly systems exist but are not yet pilot-grade across trades.

### Data and database
- Supabase migrations cover portal schema, RLS, project files, deliverables, checkout claims, EstimateJob status RPCs, final-delivery locks, and unsupported/test-only owner-ready guards.
- SQLite/local backend data models exist for estimating-engine tests and services.
- No single typed canonical evidence contract currently covers every provider/manual/human source.

### Benchmarks and test corpora
- Golden Set v1/v2 and real-test batch harnesses exist.
- Prior score target was release-gate and extraction safety; pilot target shifts to real estimating metrics: usable source-backed scope, quantity accuracy, processing time, human QA time, contractor correction rate, and package completeness.

## Reusable components
- Supabase Auth/RLS/company/project foundation.
- Private project file upload and retry flow.
- EstimateJob workflow and admin command center base.
- Existing extraction schemas, evidence references, and capability registry safety logic.
- Generic scope/estimate bridge, quantity requirements, pricing prep, proposals, customer revisions.
- Golden Set/real-test harnesses and PDF collector/batch runner.
- Existing final-delivery locks and tenant boundary guards.

## Missing pilot capabilities
1. Canonical, versioned evidence schema that all sources normalize into.
2. Provider-neutral `TakeoffProvider` interface and adapters.
3. Manual/human-verified takeoff import path.
4. AI project intake that classifies files, drawing index, addenda, trades, and questions.
5. Measured blueprint takeoff proof for count, area, linear, and schedule categories.
6. Assembly/pricing mapping from canonical quantities to estimate lines.
7. Estimator command center focused on exceptions and review state.
8. Contractor revision preview/recalculation/versioning flow.
9. Structured learning records separated into project-specific, contractor-specific, and general-learning candidates.
10. Professional bid package output with human approval and source references.
11. Five-project realistic shakeout with labor/time/cost/accuracy metrics.

## Customer journey
1. Contractor chooses service/plan or pilot intake lane.
2. Contractor creates account/company and starts project.
3. Contractor uploads plans/specs/addenda/bid forms.
4. Mobi classifies files and produces a takeoff work plan.
5. Mobi asks only necessary clarification questions.
6. AI/deterministic/human takeoff produces canonical evidence.
7. Estimate assembly/pricing creates internal draft.
8. Human reviewer works exceptions and approves.
9. Customer receives bid package.
10. Customer requests changes conversationally.
11. Mobi previews structured changes, recalculates, and records learning.
12. Human approval gates material/final delivery changes.

## Internal estimator workflow
- Work from a single command center.
- Prioritize exceptions: missing files, addenda conflicts, low confidence, unmapped takeoff rows, missing prices, source gaps, customer revisions.
- Approve only after source/evidence/pricing/review gates pass.
- Every manual quantity or correction must create canonical evidence or a learning record.

## AI automation workflow
- Tier 0 deterministic extraction/calculation first.
- Tier 1 low-cost metadata/sheet classification where reliable.
- Tier 2 strong vision/reasoning for ambiguous drawing regions.
- Tier 3 GPT-5.6 only for architecture, high-risk ambiguity, benchmark diagnosis, or complex cross-trade reasoning.
- Tier 4 human review when confidence/evidence is insufficient.

## Human QA workflow
- Every pilot estimate receives final human approval.
- QA validates critical omissions, major quantities, pricing basis, arithmetic, assumptions/exclusions, and bid package professionalism.
- Human review outcomes update evidence/revision/learning records.

## Contractor revision workflow
- Accept natural-language revision requests.
- Parse into structured proposed changes.
- Show original/new values, affected scope, pricing/quantity deltas, assumptions, conflicts, and total impact.
- Require confirmation and human approval for material changes.
- Create a new estimate version and structured correction records.

## Training-data workflow
- Never train from unverified model output.
- Preferred ground truth: customer-authorized documents + initial Mobi prediction + human review + contractor correction + final accepted result.
- Keep levels separate:
  - Project-specific: only current estimate.
  - Contractor-specific: company preference/default after permission.
  - General learning candidate: only after verification, permission, and anonymization where required.

## Blueprint takeoff strategy
1. Classify PDF: vector/raster/text quality/page size/sheet/title/discipline/revision/scale/regions.
2. Extract native vector geometry where available.
3. Extract printed dimensions, schedules, legends, and specs.
4. Use AI vision only on focused sheets/regions requiring interpretation.
5. Use deterministic calculations for distances, areas, counts, conversions, labor, cost, markups.
6. Cross-check plan counts vs schedules vs specs vs printed dimensions; create exceptions on conflicts.

## Provider-neutral takeoff strategy
Use a common interface:
- `MobiNativeTakeoffProvider`
- `ManualTakeoffImportProvider`
- `HumanVerifiedTakeoffProvider`
- `AuthorizedThirdPartyProvider`
- `FutureCadBimProvider`

Every provider normalizes into one canonical evidence contract. Unknown payloads fail validation, quarantine, or require explicit mapping. Do not add synonym scanners for unknown payloads.

## Security and privacy requirements
- Tenant/company/project isolation on every project, artifact, evidence, estimate, revision, and learning record.
- Private document storage and no cross-company source leakage.
- No third-party use outside permitted terms.
- No final estimate delivery without human/owner approval.
- No external messages, payments, refunds, pricing/legal/DNS changes, purchases, or production data deletion without approval.

## Pilot limitations
- Private paid pilot only after launch gate.
- 1–3 contractors maximum initially.
- Human-reviewed delivery.
- Manual/third-party takeoff allowed only when authorized and recorded.
- Mobi is AI-assisted, not fully autonomous.
- Supported categories expand only after measured performance.

## Launch criteria
Mobi is ready for private paid pilot after five consecutive realistic projects meet:
- Completed within 48 hours.
- No critical trade omissions.
- All major quantities have canonical evidence or human verification.
- Arithmetic deterministic and correct.
- Human approval received.
- Contractor revisions can be processed.
- Final package is professional.
- Tenant data remains isolated.
- Failures have manual recovery.
- Labor cost/gross margin known.
- At least three testers indicate they would pay again.

## Operational metrics
- Turnaround time.
- Automated processing time.
- Human takeoff time.
- QA time.
- Quantity correction rate.
- Scope correction rate.
- Pricing correction rate.
- Contractor revision count.
- Source coverage.
- Critical omissions.
- Gross margin and labor cost per estimate.
- AI usage per estimate/correction/revision.

## Exact implementation sequence
1. Stop obsolete automation and establish control.
2. Canonical evidence schema and provider architecture.
3. AI project intake.
4. Blueprint takeoff proof.
5. Manual and third-party takeoff import.
6. Assembly and pricing engine.
7. Estimator command center.
8. Contractor revision system.
9. Customer delivery package.
10. Five-project shakeout.
11. Private pilot readiness.

## Dependencies
- Verified current repo/branch discipline.
- Supabase migrations and local/production migration path.
- Cached PDF/OCR/vector artifacts.
- Real public/authorized documents and later real tester projects.
- Human reviewer process and capacity assumptions.
- Stripe/payment settings only when payment milestone is active and approved.

## Risks
- Estimating accuracy may fail despite safety gates.
- Human QA may become bottleneck.
- PDF/vector/raster quality varies widely.
- Pricing data reliability and licensing constraints.
- Third-party takeoff terms may restrict use.
- AI cost may grow without caching/routing.
- Existing PRs may contain useful fixes but old-loop architecture.

## Recovery procedures
- Keep migrations reversible or additive where possible.
- Use branches/PRs per milestone, not micro-PR vocabulary chains.
- Preserve raw provider/source payloads separately from normalized evidence.
- Quarantine unknown payloads instead of silently accepting them.
- Maintain manual fallback for all pilot estimates.
- Track blockers in `docs/pilot/pilot-status.json` and `docs/pilot/pilot-progress.md`.

## Estimated customer capacity
Initial private pilot: 1–3 contractors with controlled simultaneous intake. Start with 1 active project at a time until five-project shakeout proves labor, turnaround, and quality.

## Immediate next implementation
Begin Milestone 2 by adding typed canonical evidence schema and provider-neutral takeoff interfaces, then tests proving unknown payloads fail validation and manual/human/Mobi-native provider outputs normalize into the same contract.
