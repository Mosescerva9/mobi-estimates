# Mobi MVP Master Plan — OpenTakeoff Customer Launch

Updated: 2026-07-16T00:04:33Z

## Mission
Prepare Mobi for a controlled paid pilot: public website → pricing/checkout → account/onboarding → secure plan upload → OpenTakeoff-powered measurement → deterministic estimate assembly → human QA/approval → professional bid package → contractor revisions → structured learning.

## Current architecture
- Public/customer app: Next.js repo root (`package.json` scripts include `build`, `typecheck`, `lint`, checkout/project/upload/admin test harnesses).
- Estimating engine: `mobi-estimating-phase1/` Python service and test corpus.
- Production-ish engine process observed: `/opt/mobi-estimating-engine/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Deployment edge: Caddy active on host, ports 80/443 open.
- Existing Golden Set fixtures: `mobi-estimating-phase1/data/golden_set_v2/documents/` and `real_tests/batch-001/pdfs/`.

## Reusable systems
- Existing checkout/onboarding safety harnesses.
- Existing project upload helper tests.
- Existing EstimateJob/admin handoff flow and deliverable gate tests.
- Existing canonical evidence persistence merged in `origin/main` at `2269b8a`.
- Existing Golden Set / real-test reports and PDF fixtures.

## Missing capabilities
- Production-ready OpenTakeoff provider integration.
- Verified customer-facing end-to-end paid onboarding with upload and portal tracking.
- Fully verified estimator command center for exception-based review.
- Professional bid-package generation with final human approval gate.
- Contractor revision parser/preview/apply/version workflow.
- Structured learning store for verified corrections.
- Five-project shakeout evidence.

## Website completion plan
Audit current pages, align messaging to “AI-powered, human-reviewed construction estimating,” remove unsupported automation/accuracy claims, verify mobile/accessibility/SEO/error states, and add tests for pricing CTA routing without starting live checkout.

## Stripe and onboarding plan
Preserve owner-approved pricing. Verify existing Stripe env key names and IDs without printing secrets. Exercise offline/test harnesses first. Do not start live checkout or create/modify Stripe products without approval.

## Customer portal plan
Verify login, account linking, project creation, upload retry/recovery, status tracking, customer-safe revision history, deliverable download gates, and tenant isolation.

## OpenTakeoff integration
1. Isolated license/notice review.
2. Isolated MCP install and tool smoke tests.
3. Run Golden Set measurement(s), starting with one clean/vector PDF.
4. Normalize OpenTakeoff exports into canonical evidence records through a provider boundary.
5. Require scale confirmation and preserve geometry/sheet/scale provenance.

## AI automation flow
AI classifies sheets, reads title blocks/indexes/schedules/legends, identifies scope and probable measurement regions, proposes estimator questions, and suggests measurement inputs. Deterministic code/OpenTakeoff calculates quantities; deterministic estimate engine calculates pricing.

## Human estimator flow
Reviewer works from exceptions: scale warnings, failed traces, uncertain quantities, unmapped conditions, missing prices, scope gaps, addenda conflicts, and QA warnings. Every MVP estimate requires owner/human approval before delivery.

## Revision and learning flow
Customer natural-language change request → structured proposed changes → preview original/proposed totals and warnings → confirmation → deterministic recalculation → new version → audit/history → project/company/general-learning classification only after verification.

## Security requirements
Tenant-scoped DB/storage; expiring signed URLs; webhook verification; server-side secrets only; no Vite/client secret exposure; OpenTakeoff processing cannot leak customer documents; no raw sensitive document content in logs; backups verified; migration rollback notes.

## Testing plan
Focused tests first: type/syntax → affected unit → integration → checkout/upload/admin harnesses → Golden Set/OpenTakeoff → E2E visitor-to-revision → full regression before merge.

## Launch gate
Private pilot only when website/pricing/checkout/account/portal/upload/document processing/OpenTakeoff/human workflow/estimate/package/revision/tenant isolation/backups/five-project shakeout/manual recovery are verified. Initial capacity: 1–3 contractors, controlled simultaneous projects, 24–48h turnaround.

## Rollback plan
Keep changes branch-scoped; preserve existing `main`; reversible stashes for pre-existing local work; no production deploy or migration without explicit approval and rollback instructions.

## Exact implementation sequence
1. Regain control: pause/verify old loops, essential service/backups check, PR inventory.
2. Create branch/docs and audit current system.
3. OpenTakeoff license/MCP proof and one Golden Set measurement.
4. Provider-neutral takeoff interface and canonical evidence schema/migration/tests.
5. OpenTakeoff adapter service boundary and normalization tests.
6. Website/pricing/onboarding completion tests.
7. Upload/document/AI intake workflow.
8. Estimator command center and assembly/pricing engine.
9. Revision/learning/output package workflow.
10. Five-project shakeout and launch-gate recommendation.
