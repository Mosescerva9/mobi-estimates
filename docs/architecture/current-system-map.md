# Current system map

Updated: 2026-07-15T02:13:33Z

## Frontend / portal
- `src/app/portal/projects/new/` — customer project creation and upload flow.
- `src/app/portal/projects/[id]/` — project detail, add-files retry, customer revision request, sanitized revision history.
- `src/app/admin/projects/[id]/` — estimator/admin command surface: EstimateJob, automation panel, deliverable upload gate, actions.
- `src/app/billing`, `src/app/checkout`, `src/app/onboarding` — payment/onboarding surfaces to revisit under customer portal/payment milestones.

## Backend / estimating engine
- `mobi-estimating-phase1/app/main.py` — FastAPI app.
- `app/extraction/*` — extraction provider registry, schemas, cache, mock/OpenAI providers.
- `app/generic_scope.py`, `app/generic_estimate_bridge.py` — generic scope/estimate bridge.
- `app/quantity_requirements.py`, `app/estimating/*` — quantity requirements and deterministic formulas/units.
- `app/pricing/*`, `app/generic_pricing*.py` — pricing engine, inputs, rollups, exports.
- `app/proposals/*`, `app/proposals_db.py` — proposal generation/storage.
- `app/customer_revisions.py` — customer revision parser and workflow scaffolding.
- `app/capability_registry.py`, `app/estimate_readiness.py` — delivery locks and source-readiness logic.
- `app/tenant_boundary.py`, `app/router_tenant_guard.py` — tenant/company/project isolation.

## Database / Supabase
- `supabase/migrations/0001_schema.sql` to `0023_block_owner_ready_for_unsupported_or_test_only_evidence.sql` cover portal schema, RLS, file storage, checkout claims, EstimateJob workflow RPCs, deliverable locks, and owner-ready guards.
- Production-applied state must be verified separately before launch-sensitive changes; repo migrations are intended state until catalog verification.

## Benchmarks and corpora
- `mobi-estimating-phase1/data/golden_set_v2/` — current public-document benchmark corpus.
- `mobi-estimating-phase1/real_tests/batch-001/` — manifest-driven real-test harness area.
- `mobi-estimating-phase1/scripts/golden_set_extraction_eval.py` and `real_document_harness.py` — benchmark/harness scripts.

## Automation/control
- Prior Hermes cron development loop is paused. Use this branch and milestone docs as source of truth.
- Required status files: `docs/pilot/pilot-status.json`, `docs/pilot/pilot-progress.md`, `docs/pilot/ai-usage-ledger.md`, `docs/pilot/ai-efficiency-log.md`.
