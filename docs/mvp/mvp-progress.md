# MVP Progress

Updated: 2026-07-16T00:40Z

## Current milestone
Milestone 3 — Canonical evidence and provider architecture started.

## Completed in this cycle
- Verified repo remote: `https://github.com/Mosescerva9/mobi-estimates.git`.
- Stashed pre-existing local dirty work before creating MVP branch.
- Created branch `mvp-opentakeoff-customer-launch` from `origin/main` at `2269b8a`.
- Verified old autonomous Mobi loops are paused/enabled=false; documented in `docs/operations/paused-automation-inventory.md`.
- Verified no user crontab, no tmux/screen coding loops, no active Claude/Codex builder process.
- Verified essential host services `cron`, `ssh`, `caddy`, `docker`, and Mobi engine process are active.
- Inventoried open PRs in `docs/mvp/open-pr-inventory.md`.
- Created required MVP docs: master plan, progress, status JSON, decision log, launch checklist, current-state audit, AI usage ledger.
- Cloned OpenTakeoff to `/tmp/opentakeoff-eval` at `36a9aa7ebe0a6dde116c0a3d68a16fe39a0c94bf`.
- Reviewed OpenTakeoff license/NOTICE/dependencies in `docs/legal/opentakeoff-license-review.md`.
- Installed/tested OpenTakeoff MCP; MCP typecheck and tests passed 20/20.
- Verified `npx -y opentakeoff-mcp` through an MCP client and exercised all 10 required tools.
- Ran a real Golden Set OpenTakeoff attempt on Patton reroof G001; failed safely because MCP saw the sheet as raster/no vector linework and could not extract the verified `19,337 SF` roofing area.
- Probed Golden Set vector/raster status; two plan sets show vector linework, Patton reroof is raster-only for MCP.
- Began canonical provider implementation: added OpenTakeoff, CustomerSupplied, and FutureThirdParty provider lanes plus `condition` and `scale` canonical evidence fields.
- Ran focused Codex review on PR #95; Codex found two blockers (mutated applied migrations, and missing raw-vs-flattened fail-closed checks for `condition`/`scale`).
- Fixed those blockers with forward SQLite migration v38, Supabase migration `0025_canonical_takeoff_evidence_provider_fields.sql`, null-safe deserialization checks, and regression tests.
- Reran Codex focused review after fixes: `PASS - no blocking issues`; Codex also reran the focused Python tests in its snapshot.

## Verification run
- `npm run typecheck` → passed.
- `npm run lint` → passed.
- `npm run build` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_golden_set_extraction_eval.py tests/test_mobi_autoresearch.py tests/test_real_document_harness.py -q` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 108 passed.
- After Codex blocker fixes: `cd mobi-estimating-phase1 && python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 122 passed.
- `npm run test:checkout-flow` → 13/13 passed using in-memory fakes only.
- `npm run test:checkout-prefetch` → passed.
- `npm run test:checkout-readiness` → 6/6 passed.
- `npm run test:project-upload` → 14/14 passed.
- `npm run test:deliverable-gate` → 36/36 passed.
- `npm run test:deliverable-rls-gate` → 3/3 passed.
- `npm run test:engine-tenant-context` → passed.
- `npm run test:customer-revision-portal` → passed.
- `npm run test:admin-revision-workflow` → passed.
- `git diff --check` → passed before and after Codex blocker fixes.

## Blockers / risks
- Root filesystem is 95% full. Cleanup requires owner approval because deleting non-scratch files is approval-gated.
- OpenTakeoff MCP raster gap is real: Patton Golden Set scanned/raster plan failed to produce the verified schedule quantity.
- OpenTakeoff MCP `npm install` reported one moderate vulnerability; not remediated in this slice.
- App/DB backups beyond OS package backups are still not fully verified.
- Production/live checkout was not exercised; live payment side effects remain approval-gated.

## Next task
Build the first OpenTakeoff-to-Mobi adapter normalization tests using exported OpenTakeoff JSON → `OpenTakeoffProvider` → canonical evidence rows, then add a raster fallback plan.
